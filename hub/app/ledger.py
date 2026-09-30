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


class DrunixLedger:
    """Calls the deployed `remit` chaincode through the peer CLI.
    Per-org env files (KEY=VALUE lines) live in DRUNIX_ORG_ENV_DIR as org1.env / org2.env and must set
    CORE_PEER_LOCALMSPID, CORE_PEER_ADDRESS, CORE_PEER_MSPCONFIGPATH, CORE_PEER_TLS_ROOTCERT_FILE, CORE_PEER_TLS_ENABLED.
    Also set DRUNIX_CHANNEL, DRUNIX_CC_NAME, DRUNIX_ORDERER, DRUNIX_ORDERER_CA and DRUNIX_PEER_BIN (optional)."""
    mode = "drunix"

    def __init__(self):
        self.channel = os.environ.get("DRUNIX_CHANNEL", "mychannel")
        self.cc = os.environ.get("DRUNIX_CC_NAME", "remit")
        self.orderer = os.environ.get("DRUNIX_ORDERER", "localhost:7050")
        self.orderer_ca = os.environ.get("DRUNIX_ORDERER_CA", "")
        self.peer = os.environ.get("DRUNIX_PEER_BIN", "peer")
        self.env_dir = os.environ["DRUNIX_ORG_ENV_DIR"]

    def _env(self, org):
        env = dict(os.environ)
        with open(os.path.join(self.env_dir, "org1.env" if org == REMITTER else "org2.env")) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k] = v
        return env

    def _run(self, cmd, env):
        p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            raise LedgerError((p.stderr or p.stdout).strip()[-500:])
        return p

    def _invoke(self, org, fn, *args):
        env = self._env(org)
        payload = json.dumps({"function": fn, "Args": [str(a).lower() if isinstance(a, bool) else str(a) for a in args]})
        cmd = [self.peer, "chaincode", "invoke", "-o", self.orderer, "-C", self.channel, "-n", self.cc,
               "-c", payload, "--waitForEvent"]
        if self.orderer_ca:
            cmd += ["--tls", "--cafile", self.orderer_ca]
        peer_addrs = os.environ.get("DRUNIX_ENDORSE_PEERS", "")  # "addr1|tlsca1,addr2|tlsca2"
        for pair in filter(None, peer_addrs.split(",")):
            addr, ca = pair.split("|")
            cmd += ["--peerAddresses", addr, "--tlsRootCertFiles", ca]
        self._run(cmd, env)

    def _query(self, fn, *args):
        env = self._env(REMITTER)
        payload = json.dumps({"function": fn, "Args": [str(a) for a in args]})
        p = self._run([self.peer, "chaincode", "query", "-C", self.channel, "-n", self.cc, "-c", payload], env)
        return json.loads(p.stdout)

    def GetRemittance(self, rid): return self._query("GetRemittance", rid)
    def ListRemittances(self): return self._query("ListRemittances") or []
    def GetRemittanceHistory(self, rid): return self._query("GetRemittanceHistory", rid) or []


def _make_invoker(name):
    def f(self, org, *args):
        return self._invoke(org, name, *args)
    return f


for _fn in ["CreateRemittance", "LockQuote", "RecordScreening", "ReviewHold", "VerifyBeneficiary",
            "ConfirmFunding", "SubmitPayout", "SettlePayout", "FailPayout", "Refund"]:
    setattr(DrunixLedger, _fn, _make_invoker(_fn))


def make_ledger():
    return DrunixLedger() if os.environ.get("LEDGER_MODE", "memory") == "drunix" else MemoryLedger()
