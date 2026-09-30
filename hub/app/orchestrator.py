"""Drives one remittance through the chaincode state machine.
Personal data (names, UPI addresses) stays here, off-ledger; only salted hashes go on-chain."""
import hashlib
import os
import time
import uuid

from . import fx, risk, upi
from .ledger import LedgerError, PAYOUT, REMITTER

SALT = os.environ.get("PII_SALT", "demo-salt-change-me")
TERMINAL = {"SETTLED", "REFUNDED"}
SCENARIOS = {"happy", "high_risk", "sanctions_hit", "payout_fail", "bad_beneficiary", "quote_expired"}


def h(value: str) -> str:
    return hashlib.sha256((SALT + value.strip().lower()).encode()).hexdigest()


class Orchestrator:
    def __init__(self, ledger):
        self.ledger = ledger
        self.meta = {}       # remittance id -> off-chain PII + scenario
        self.history = {}    # sender hash -> [{ts, amountMinor}]
        self.seen_ben = set()

    def create(self, p: dict) -> dict:
        scenario = p.get("scenario", "happy")
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario {scenario}")
        if p["corridor"] not in fx.CORRIDORS:
            raise ValueError("unknown corridor")
        rid = "R" + uuid.uuid4().hex[:10].upper()
        sender_h, ben_h = h(p["senderName"]), h(p["beneficiaryVpa"])
        self.meta[rid] = {**p, "scenario": scenario, "senderHash": sender_h,
                          "newBeneficiary": ben_h not in self.seen_ben}
        self.seen_ben.add(ben_h)
        self.ledger.CreateRemittance(REMITTER, rid, p["corridor"], sender_h, ben_h, p["purpose"])
        return self.ledger.GetRemittance(rid)

    def preview(self, corridor: str, amount_minor: int) -> dict:
        from .pricing import compute_quote
        s = fx.schedule(corridor)
        q = compute_quote(s["ccy"], amount_minor, s["mid"], s["spread"], s["flat"], s["bps"])
        q["benchmarkCostBps"] = fx.BENCHMARK_COST_BPS
        return q

    def step(self, rid: str) -> dict:
        r, m = self.ledger.GetRemittance(rid), self.meta[rid]
        st, sc = r["status"], m["scenario"]
        L = self.ledger
        if st == "CREATED":
            s = fx.schedule(m["corridor"])
            validity = 2 if sc == "quote_expired" else 300
            L.LockQuote(REMITTER, rid, s["ccy"], m["amountMinor"], s["mid"], s["spread"], s["flat"], s["bps"], validity)
        elif st == "QUOTED":
            hist = self.history.get(m["senderHash"], [])
            score, reasons = risk.score(m["amountMinor"], m["purpose"], hist, m["newBeneficiary"],
                                        force_high=(sc == "high_risk"))
            sanctions = sc == "sanctions_hit"
            L.RecordScreening(REMITTER, rid, score, sanctions, ",".join(reasons))
            self.history.setdefault(m["senderHash"], []).append({"ts": time.time(), "amountMinor": m["amountMinor"]})
        elif st == "HELD":
            return {**r, "needsReview": True}
        elif st == "SCREENED":
            registered = upi.resolve_vpa(m["beneficiaryVpa"], sc) or m["beneficiaryName"]
            L.VerifyBeneficiary(PAYOUT, rid, upi.name_match(m["beneficiaryName"], registered))
        elif st == "VERIFIED":
            if sc == "quote_expired":
                time.sleep(3)
            L.ConfirmFunding(REMITTER, rid, "FUND-" + rid)
        elif st == "FUNDED":
            L.SubmitPayout(PAYOUT, rid, upi.submit(rid))
        elif st == "PAYOUT_SUBMITTED":
            outcome, ref = upi.poll(rid, sc)
            (L.SettlePayout if outcome == "SUCCESS" else L.FailPayout)(PAYOUT, rid, ref)
        elif st in ("FAILED", "EXPIRED", "BLOCKED", "BENEFICIARY_REJECTED"):
            L.Refund(REMITTER, rid, "RFND-" + rid)
        return L.GetRemittance(rid)

    def run(self, rid: str, max_steps: int = 12) -> dict:
        for _ in range(max_steps):
            r = self.ledger.GetRemittance(rid)
            if r["status"] in TERMINAL or r["status"] == "HELD":
                return r
            self.step(rid)
        return self.ledger.GetRemittance(rid)

    def review(self, rid: str, approve: bool) -> dict:
        self.ledger.ReviewHold(REMITTER, rid, approve, "" if approve else "Rejected by compliance officer")
        return self.ledger.GetRemittance(rid)

    def stats(self) -> dict:
        rs = self.ledger.ListRemittances()
        settled = [r for r in rs if r["status"] == "SETTLED"]
        costs = [r["quote"]["costBps"] for r in settled if r.get("quote")]
        times = [r["updatedAt"] - r["createdAt"] for r in settled]
        return {
            "total": len(rs), "settled": len(settled),
            "refunded": sum(r["status"] == "REFUNDED" for r in rs),
            "held": sum(r["status"] == "HELD" for r in rs),
            "avgCostBps": round(sum(costs) / len(costs), 1) if costs else None,
            "avgSettleSeconds": round(sum(times) / len(times), 1) if times else None,
            "benchmarkCostBps": fx.BENCHMARK_COST_BPS,
        }
