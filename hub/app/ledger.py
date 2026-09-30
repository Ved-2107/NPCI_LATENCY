"""Ledger clients. Both expose the chaincode's function names 1:1.

MemoryLedger  - in-process port of chaincode/remit/remit.go so the demo runs with no network.
                It enforces the same org roles, state machine and policy constants.
DrunixLedger  - real calls to the `remit` chaincode on a Drunix network via the `peer` CLI.
Select with LEDGER_MODE=memory|drunix.
"""
import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone

from .pricing import compute_quote

REMITTER, PAYOUT = "Org1MSP", "Org2MSP"
RISK_HOLD, RISK_BLOCK, MIN_NAME_MATCH = 60, 85, 70
DAILY_CAP_PAISE = 500_000_000
ALLOWED_PURPOSES = {"FAMILY_MAINTENANCE", "EDUCATION", "MEDICAL", "GIFT", "INVESTMENT", "TRAVEL"}


class LedgerError(Exception):
    pass


class MemoryLedger:
    mode = "memory"

    def __init__(self):
        self.state, self.vel, self.payout_refs = {}, {}, {}
        self.history = {}

    # -- helpers --
    def _now(self):
        return int(time.time())

    def _need(self, org, want):
        if org != want:
            raise LedgerError(f"caller org {org} not permitted; {want} required")

    def _get(self, rid):
        if rid not in self.state:
            raise LedgerError(f"remittance {rid} not found")
        return json.loads(json.dumps(self.state[rid]))

    def _status(self, r, *allowed):
        if r["status"] not in allowed:
            raise LedgerError(f"remittance {r['id']} is {r['status']}; expected one of {list(allowed)}")

    def _save(self, org, r, step, status):
        now = self._now()
        r["status"], r["updatedAt"] = status, now
        r["trail"].append({"step": step, "status": status, "org": org, "txId": uuid.uuid4().hex, "ts": now})
        self.state[r["id"]] = r
        self.history.setdefault(r["id"], []).append({
            "txId": r["trail"][-1]["txId"],
            "timestamp": datetime.fromtimestamp(now, timezone.utc).isoformat(),
            "isDelete": False, "value": json.dumps(r)})

    def _vk(self, ben, now):
        return f"{ben}_{datetime.fromtimestamp(now, timezone.utc):%Y%m%d}"

    # -- transactions (mirror remit.go) --
    def CreateRemittance(self, org, rid, corridor, sender_hash, ben_hash, purpose):
        self._need(org, REMITTER)
        if not all([rid, corridor, sender_hash, ben_hash]):
            raise LedgerError("id, corridor, senderHash and beneficiaryHash are required")
        if purpose not in ALLOWED_PURPOSES:
            raise LedgerError(f"purpose {purpose!r} not allowed")
        if rid in self.state:
            raise LedgerError(f"remittance {rid} already exists")
        r = {"docType": "remittance", "id": rid, "corridor": corridor, "senderHash": sender_hash,
             "beneficiaryHash": ben_hash, "purpose": purpose, "reasonCodes": [], "riskScore": 0,
             "nameMatchScore": 0, "funded": False, "createdAt": self._now(), "trail": []}
        self._save(org, r, "CREATE", "CREATED")

    def LockQuote(self, org, rid, ccy, send_minor, mid, spread, flat, bps, validity):
        self._need(org, REMITTER)
        r = self._get(rid); self._status(r, "CREATED")
        if not 0 < validity <= 900:
            raise LedgerError("validity must be 1..900 seconds")
        try:
            r["quote"] = compute_quote(ccy, send_minor, mid, spread, flat, bps, self._now() + validity)
        except ValueError as e:
            raise LedgerError(str(e))
        self._save(org, r, "LOCK_QUOTE", "QUOTED")

    def RecordScreening(self, org, rid, risk, sanctions_hit, reason_codes):
        self._need(org, REMITTER)
        r = self._get(rid); self._status(r, "QUOTED")
        if not 0 <= risk <= 100:
            raise LedgerError("riskScore must be 0..100")
        r["riskScore"] = risk
        r["reasonCodes"] = [c for c in reason_codes.split(",") if c]
        if sanctions_hit or risk >= RISK_BLOCK:
            if sanctions_hit:
                r["reasonCodes"].append("SANCTIONS_HIT")
            return self._save(org, r, "SCREEN", "BLOCKED")
        used = self.vel.get(self._vk(r["beneficiaryHash"], self._now()), 0)
        if used + r["quote"]["receivePaise"] > DAILY_CAP_PAISE:
            r["reasonCodes"].append("DAILY_CAP_EXCEEDED")
            return self._save(org, r, "SCREEN", "HELD")
        self._save(org, r, "SCREEN", "HELD" if risk >= RISK_HOLD else "SCREENED")

    def ReviewHold(self, org, rid, approve, note=""):
        self._need(org, REMITTER)
        r = self._get(rid); self._status(r, "HELD")
        if approve:
            return self._save(org, r, "REVIEW_APPROVE", "SCREENED")
        r["failReason"] = note
        self._save(org, r, "REVIEW_REJECT", "BLOCKED")

    def VerifyBeneficiary(self, org, rid, match):
        self._need(org, PAYOUT)
        r = self._get(rid); self._status(r, "SCREENED")
        r["nameMatchScore"] = match
        self._save(org, r, "VERIFY_BENEFICIARY", "VERIFIED" if match >= MIN_NAME_MATCH else "BENEFICIARY_REJECTED")

    def ConfirmFunding(self, org, rid, funding_ref):
        self._need(org, REMITTER)
        r = self._get(rid); self._status(r, "VERIFIED")
        if not funding_ref:
            raise LedgerError("fundingRef required")
        now = self._now()
        if now > r["quote"]["expiresAtUnix"]:
            return self._save(org, r, "FUNDING_QUOTE_EXPIRED", "EXPIRED")
        vk = self._vk(r["beneficiaryHash"], now)
        used = self.vel.get(vk, 0)
        if used + r["quote"]["receivePaise"] > DAILY_CAP_PAISE:
            raise LedgerError("daily beneficiary cap exceeded")
        self.vel[vk] = used + r["quote"]["receivePaise"]
        r["fundingRef"], r["funded"] = funding_ref, True
        self._save(org, r, "CONFIRM_FUNDING", "FUNDED")

    def SubmitPayout(self, org, rid, payout_ref):
        self._need(org, PAYOUT)
        r = self._get(rid)
        if r["status"] == "PAYOUT_SUBMITTED" and r.get("payoutRef") == payout_ref:
            return
        self._status(r, "FUNDED")
        if not payout_ref:
            raise LedgerError("payoutRef required")
        if payout_ref in self.payout_refs:
            raise LedgerError(f"payoutRef {payout_ref} already used")
        self.payout_refs[payout_ref] = rid
        r["payoutRef"] = payout_ref
        self._save(org, r, "SUBMIT_PAYOUT", "PAYOUT_SUBMITTED")

    def SettlePayout(self, org, rid, upi_ref):
        self._need(org, PAYOUT)
        r = self._get(rid)
        if r["status"] == "SETTLED" and r.get("upiRef") == upi_ref:
            return
        self._status(r, "PAYOUT_SUBMITTED")
        if not upi_ref:
            raise LedgerError("upiRef required")
        r["upiRef"] = upi_ref
        self._save(org, r, "SETTLE_PAYOUT", "SETTLED")

    def FailPayout(self, org, rid, reason):
        self._need(org, PAYOUT)
        r = self._get(rid); self._status(r, "PAYOUT_SUBMITTED")
        r["failReason"] = reason
        self._save(org, r, "FAIL_PAYOUT", "FAILED")

    def Refund(self, org, rid, refund_ref):
        self._need(org, REMITTER)
        r = self._get(rid); self._status(r, "FAILED", "EXPIRED", "BLOCKED", "BENEFICIARY_REJECTED")
        if not refund_ref:
            raise LedgerError("refundRef required")
        if r["funded"]:
            vk = self._vk(r["beneficiaryHash"], self._now())
            self.vel[vk] = max(0, self.vel.get(vk, 0) - r["quote"]["receivePaise"])
        r["refundRef"] = refund_ref
        self._save(org, r, "REFUND", "REFUNDED")

    # -- queries --
    def GetRemittance(self, rid):
        return self._get(rid)

    def ListRemittances(self):
        return sorted((json.loads(json.dumps(v)) for v in self.state.values()), key=lambda r: r["createdAt"])

    def GetRemittanceHistory(self, rid):
        return self.history.get(rid, [])

