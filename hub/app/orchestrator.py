"""Drives one remittance through the chaincode state machine.
Personal data (names, UPI addresses) stays here, off-ledger; only salted hashes go on-chain."""
import hashlib
import logging
import os
import threading
import time
import uuid

from . import fx, pricing, risk, upi
from .events import broadcaster
from .ledger import LedgerError, PAYOUT, REMITTER
from .notifications import notifier

logger = logging.getLogger("remitchain.orchestrator")

SALT = os.environ.get("PII_SALT", "demo-salt-change-me")
TERMINAL = {"SETTLED", "REFUNDED"}
SCENARIOS = {"happy", "high_risk", "sanctions_hit", "payout_fail", "bad_beneficiary", "quote_expired"}


def h(value: str) -> str:
    return hashlib.sha256((SALT + value.strip().lower()).encode()).hexdigest()


class Orchestrator:
    def __init__(self, ledger, step_delay: float = None, expired_delay: float = None):
        self.ledger = ledger
        self.meta = {}       # remittance id -> off-chain PII + scenario
        self.history = {}    # sender hash -> [{ts, amountMinor}]
        self.seen_ben = set()
        self.quotes = {}     # quoteId -> quote dict
        self._lock = threading.RLock()
        self._remittance_locks = {}
        self._remittance_locks_guard = threading.Lock()
        self.step_delay = float(os.environ.get("STEP_DELAY", "0.8")) if step_delay is None else step_delay
        self.expired_delay = float(os.environ.get("EXPIRED_DELAY", "3.0")) if expired_delay is None else expired_delay

    def _get_remittance_lock(self, rid: str) -> threading.Lock:
        with self._remittance_locks_guard:
            if rid not in self._remittance_locks:
                self._remittance_locks[rid] = threading.Lock()
            return self._remittance_locks[rid]

    def _emit(self, r: dict, step: str):
        """Emit a real-time event and notification for a state change."""
        event = {
            "type": "state_change",
            "remittanceId": r["id"],
            "status": r["status"],
            "step": step,
            "corridor": r.get("corridor", ""),
        }
        broadcaster.emit_sync(event)
        notifier.notify(r)

    def create_quote(self, corridor: str, amount_minor: int) -> dict:
        if corridor not in fx.CORRIDORS:
            raise ValueError(f"unknown corridor {corridor}")
        s = fx.schedule(corridor)
        decimals = s.get("decimals", 2)
        q = pricing.compute_quote(s["ccy"], amount_minor, s["mid"], s["spread"], s["flat"], s["bps"], decimals=decimals)
        qid = "Q-" + uuid.uuid4().hex[:10].upper()
        now = time.time()
        validity = 300
        quote_data = {
            "quoteId": qid,
            "corridor": corridor,
            "sendCurrency": s["ccy"],
            "sendAmountMinor": amount_minor,
            "midRateMicro": s["mid"],
            "effectiveRateMicro": q["effectiveRateMicro"],
            "spreadBps": s["spread"],
            "feeFlatMinor": s["flat"],
            "feeBps": s["bps"],
            "feeTotalMinor": q["feeTotalMinor"],
            "receivePaise": q["receivePaise"],
            "costBps": q["costBps"],
            "createdAt": now,
            "expiresAt": now + validity,
            "validitySecs": validity,
            "decimals": decimals,
        }
        with self._lock:
            self.quotes[qid] = quote_data
        return quote_data

    def preview(self, corridor: str, amount_minor: int) -> dict:
        s = fx.schedule(corridor)
        decimals = s.get("decimals", 2)
        q = pricing.compute_quote(s["ccy"], amount_minor, s["mid"], s["spread"], s["flat"], s["bps"], decimals=decimals)
        q["benchmarkCostBps"] = fx.BENCHMARK_COST_BPS
        return q

    def create(self, p: dict) -> dict:
        scenario = p.get("scenario", "happy")
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario {scenario}")
        if p["corridor"] not in fx.CORRIDORS:
            raise ValueError("unknown corridor")

        bound_quote = None
        qid = p.get("quoteId")
        if qid:
            with self._lock:
                bound_quote = self.quotes.get(qid)
            if not bound_quote:
                raise ValueError(f"quote {qid} not found or expired")
            if time.time() > bound_quote["expiresAt"]:
                raise ValueError(f"quote {qid} has expired")
            # Overwrite amount/corridor from binding quote
            p["amountMinor"] = bound_quote["sendAmountMinor"]
            p["corridor"] = bound_quote["corridor"]

        rid = "R" + uuid.uuid4().hex[:10].upper()
        sender_h, ben_h = h(p["senderName"]), h(p["beneficiaryVpa"])
        with self._lock:
            self.meta[rid] = {
                **p,
                "scenario": scenario,
                "senderHash": sender_h,
                "newBeneficiary": ben_h not in self.seen_ben,
                "boundQuote": bound_quote,
            }
            self.seen_ben.add(ben_h)

        self.ledger.CreateRemittance(REMITTER, rid, p["corridor"], sender_h, ben_h, p["purpose"])
        r = self.ledger.GetRemittance(rid)
        logger.info("Remittance %s created for corridor %s (amount: %s minor)", rid, p["corridor"], p.get("amountMinor"))
        self._emit(r, "CREATE")
        return r

    def step(self, rid: str) -> dict:
        with self._get_remittance_lock(rid):
            return self._step_unlocked(rid)

    def _step_unlocked(self, rid: str) -> dict:
        with self._lock:
            m = dict(self.meta.get(rid, {}))
        r = self.ledger.GetRemittance(rid)
        st, sc = r["status"], m.get("scenario", "happy")
        L = self.ledger

        if st in TERMINAL:
            raise ValueError(f"cannot step remittance {rid} in terminal status {st}")

        if st == "CREATED":
            bound = m.get("boundQuote")
            if bound:
                remaining = max(1, int(bound["expiresAt"] - time.time()))
                L.LockQuote(
                    REMITTER, rid, bound["sendCurrency"], bound["sendAmountMinor"],
                    bound["midRateMicro"], bound["spreadBps"], bound["feeFlatMinor"],
                    bound["feeBps"], remaining, decimals=bound.get("decimals")
                )
            else:
                s = fx.schedule(m["corridor"])
                decimals = s.get("decimals", 2)
                validity = 2 if sc == "quote_expired" else 300
                L.LockQuote(REMITTER, rid, s["ccy"], m["amountMinor"], s["mid"], s["spread"], s["flat"], s["bps"], validity, decimals=decimals)
            self._emit(L.GetRemittance(rid), "LOCK_QUOTE")

        elif st == "QUOTED":
            with self._lock:
                hist = list(self.history.get(m["senderHash"], []))
            score, reasons, breakdown = risk.score_and_explain(
                m["amountMinor"], m["purpose"], hist, m.get("newBeneficiary", False),
                force_high=(sc == "high_risk"), corridor=m.get("corridor")
            )
            with self._lock:
                self.meta[rid]["risk_breakdown"] = breakdown
                self.history.setdefault(m["senderHash"], []).append({"ts": time.time(), "amountMinor": m["amountMinor"]})
            sanctions = sc == "sanctions_hit"
            L.RecordScreening(REMITTER, rid, score, sanctions, ",".join(reasons))
            if score >= 60:
                logger.warning("Remittance %s compliance hold (score=%d, reasons=%s)", rid, score, reasons)
            self._emit(L.GetRemittance(rid), "SCREEN")

        elif st == "HELD":
            return {**r, "needsReview": True}

        elif st == "SCREENED":
            registered = upi.resolve_vpa(m["beneficiaryVpa"], sc)
            match_score = upi.name_match(m["beneficiaryName"], registered) if registered else 0
            L.VerifyBeneficiary(PAYOUT, rid, match_score)
            self._emit(L.GetRemittance(rid), "VERIFY_BENEFICIARY")

        elif st == "VERIFIED":
            if sc == "quote_expired" and self.expired_delay > 0:
                time.sleep(self.expired_delay)
            L.ConfirmFunding(REMITTER, rid, "FUND-" + rid)
            self._emit(L.GetRemittance(rid), "CONFIRM_FUNDING")

        elif st == "FUNDED":
            L.SubmitPayout(PAYOUT, rid, upi.submit(rid))
            self._emit(L.GetRemittance(rid), "SUBMIT_PAYOUT")

        elif st == "PAYOUT_SUBMITTED":
            outcome, ref = upi.poll(rid, sc)
            (L.SettlePayout if outcome == "SUCCESS" else L.FailPayout)(PAYOUT, rid, ref)
            self._emit(L.GetRemittance(rid), "SETTLE_PAYOUT" if outcome == "SUCCESS" else "FAIL_PAYOUT")

        elif st in ("FAILED", "EXPIRED", "BLOCKED", "BENEFICIARY_REJECTED"):
            L.Refund(REMITTER, rid, "RFND-" + rid)
            self._emit(L.GetRemittance(rid), "REFUND")

        curr = L.GetRemittance(rid)
        logger.info("Remittance %s status transitioned from %s to %s", rid, st, curr.get("status"))
        return curr

    def run(self, rid: str, max_steps: int = 12) -> dict:
        with self._get_remittance_lock(rid):
            for _ in range(max_steps):
                r = self.ledger.GetRemittance(rid)
                if r["status"] in TERMINAL or r["status"] == "HELD":
                    return r
                self._step_unlocked(rid)
                if self.step_delay > 0:
                    time.sleep(self.step_delay)
            return self.ledger.GetRemittance(rid)

    def review(self, rid: str, approve: bool, reviewer_id: str | None = None) -> dict:
        with self._get_remittance_lock(rid):
            with self._lock:
                m = self.meta.get(rid, {})
                creator = (m.get("creatorId") or m.get("senderName") or "").strip().lower()
            
            if reviewer_id and creator and reviewer_id.strip().lower() == creator:
                raise ValueError("maker cannot be checker: reviewer must differ from remittance creator")

            self.ledger.ReviewHold(REMITTER, rid, approve, "" if approve else "Rejected by compliance officer")
            r = self.ledger.GetRemittance(rid)
            self._emit(r, "REVIEW_APPROVE" if approve else "REVIEW_REJECT")
            return r


    def get_risk_detail(self, rid: str) -> dict:
        with self._lock:
            meta = self.meta.get(rid, {})
            if "risk_breakdown" in meta:
                return meta["risk_breakdown"]
        # Fallback if not yet screened
        r = self.ledger.GetRemittance(rid)
        hist = self.history.get(meta.get("senderHash", ""), [])
        return risk.explain(
            meta.get("amountMinor", 0), r.get("purpose", ""), hist,
            meta.get("newBeneficiary", False), force_high=(meta.get("scenario") == "high_risk"),
            corridor=meta.get("corridor")
        )

    def stats(self) -> dict:
        rs = self.ledger.ListRemittances()
        settled = [r for r in rs if r["status"] == "SETTLED"]
        costs = [r["quote"]["costBps"] for r in settled if r.get("quote")]
        times = [r["updatedAt"] - r["createdAt"] for r in settled]
        by_corridor = {}
        for r in rs:
            by_corridor[r["corridor"]] = by_corridor.get(r["corridor"], 0) + 1
        return {
            "totalVolumePaise": sum(r["quote"]["receivePaise"] for r in settled if r.get("quote")),
            "settledCount": len(settled),
            "totalCount": len(rs),
            "avgCostBps": int(sum(costs) / len(costs)) if costs else 0,
            "avgLatencySec": round(sum(times) / len(times), 1) if times else 0,
            "byCorridor": by_corridor,
        }

    def get_latency_telemetry(self) -> dict:
        rs = self.ledger.ListRemittances()
        settled = [r for r in rs if r["status"] == "SETTLED"]
        
        records = []
        step_diffs = {
            "lock_quote": [],
            "screening": [],
            "beneficiary_lookup": [],
            "funding_lock": [],
            "payout_submit": [],
            "settlement": []
        }
        
        for r in settled:
            trail = r.get("trail", [])
            if not trail:
                continue
            steps_ts = {}
            for t in trail:
                ts = t.get("tsMs", t.get("ts", 0) * 1000)
                steps_ts[t["step"]] = ts
                
            first_ts = trail[0].get("tsMs", trail[0].get("ts", 0) * 1000)
            last_ts = trail[-1].get("tsMs", trail[-1].get("ts", 0) * 1000)
            e2e_ms = max(1.0, round(last_ts - first_ts, 2))
            
            def diff(s1, s2):
                if s1 in steps_ts and s2 in steps_ts:
                    return max(0.1, round(steps_ts[s2] - steps_ts[s1], 2))
                return None

            lq = diff("CREATE", "LOCK_QUOTE")
            scr = diff("LOCK_QUOTE", "SCREEN")
            vpa = diff("SCREEN", "VERIFY_BENEFICIARY")
            fnd = diff("VERIFY_BENEFICIARY", "CONFIRM_FUNDING")
            sub = diff("CONFIRM_FUNDING", "SUBMIT_PAYOUT")
            stl = diff("SUBMIT_PAYOUT", "SETTLE_PAYOUT")

            if lq is not None: step_diffs["lock_quote"].append(lq)
            if scr is not None: step_diffs["screening"].append(scr)
            if vpa is not None: step_diffs["beneficiary_lookup"].append(vpa)
            if fnd is not None: step_diffs["funding_lock"].append(fnd)
            if sub is not None: step_diffs["payout_submit"].append(sub)
            if stl is not None: step_diffs["settlement"].append(stl)

            records.append({
                "id": r["id"],
                "corridor": r["corridor"],
                "totalMs": e2e_ms,
                "steps": {
                    "lockQuoteMs": lq,
                    "screeningMs": scr,
                    "beneficiaryLookupMs": vpa,
                    "fundingLockMs": fnd,
                    "payoutSubmitMs": sub,
                    "settlementMs": stl,
                }
            })

        totals = sorted([rec["totalMs"] for rec in records])
        n = len(totals)
        
        def pct(p):
            if not totals:
                return 0.0
            idx = int(round((p / 100.0) * (n - 1)))
            return round(totals[idx], 2)

        summary = {
            "count": n,
            "minMs": round(totals[0], 2) if totals else 0.0,
            "maxMs": round(totals[-1], 2) if totals else 0.0,
            "avgMs": round(sum(totals) / n, 2) if totals else 0.0,
            "p50Ms": pct(50),
            "p90Ms": pct(90),
            "p95Ms": pct(95),
            "p99Ms": pct(99),
        }

        avg_steps = {}
        for k, v in step_diffs.items():
            avg_steps[k] = round(sum(v) / len(v), 2) if v else 0.0

        swift_ms = 48 * 3600 * 1000  # 48 hours = 172,800,000 ms
        remitchain_avg = summary["avgMs"] if summary["avgMs"] > 0 else 850.0
        speedup = round(swift_ms / remitchain_avg, 1)

        return {
            "summary": summary,
            "avgStepsMs": avg_steps,
            "speedupVsSwift": speedup,
            "benchmarks": {
                "remitchainAvgMs": remitchain_avg,
                "swiftGpiMs": swift_ms,
                "correspondentBankingMs": 72 * 3600 * 1000,
            },
            "recentSettlements": records[-10:]
        }

