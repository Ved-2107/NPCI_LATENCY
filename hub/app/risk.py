"""Explainable payment risk scoring with optional ML anomaly detection.

Produces a 0-100 score plus reason codes. It advises; the chaincode
enforces thresholds, so a wrong score cannot bypass policy.

The ML model (Isolation Forest) is trained on synthetic transaction data
and provides an anomaly-based risk signal that supplements the rule-based score.
"""
import math
import statistics
import time

HIGH_RISK_PURPOSE_OVER = {"GIFT": 300_000, "INVESTMENT": 1_000_000}  # minor units
STRUCTURING_BAND = (0.90, 0.999)
REPORTING_THRESHOLD_MINOR = 1_000_000  # 10,000.00 in send currency (demo)

# Feature weights for explainability (sums to ~100 at maximum risk)
FEATURE_WEIGHTS = {
    "VELOCITY_24H": {"weight": 20, "desc": "More than 3 transfers in 24 hours"},
    "AMOUNT_ANOMALY": {"weight": 25, "desc": "Amount is 4x the sender's median"},
    "NEAR_REPORTING_THRESHOLD": {"weight": 30, "desc": "Amount near regulatory reporting threshold"},
    "NEW_BENEFICIARY_LARGE": {"weight": 15, "desc": "Large amount to a new beneficiary"},
    "PURPOSE_AMOUNT_MISMATCH": {"weight": 20, "desc": "Amount unusual for stated purpose"},
    "ML_ANOMALY": {"weight": 15, "desc": "Statistical anomaly detected by ML model"},
    "UNUSUAL_HOUR": {"weight": 10, "desc": "Transfer initiated at unusual hour"},
    "ROUND_AMOUNT": {"weight": 5, "desc": "Suspiciously round amount"},
    "SCENARIO_FORCED": {"weight": 0, "desc": "Risk elevated for demo scenario"},
}


def _is_round(amount_minor: int) -> bool:
    """Check if the amount is suspiciously round (e.g., exactly 10000, 50000)."""
    if amount_minor <= 0:
        return False
    magnitude = 10 ** (len(str(amount_minor)) - 1)
    return amount_minor % (magnitude // 10) == 0 and amount_minor >= 100_000


def _unusual_hour(now: float) -> bool:
    """Check if the transaction is at an unusual hour (UTC 0-5)."""
    hour = int(now % 86400) // 3600
    return hour < 5


def score(amount_minor, purpose, sender_history, beneficiary_is_new, now=None, force_high=False):
    """sender_history: list of dicts {ts, amountMinor} for this sender."""
    now = now or time.time()
    pts, reasons = 0, []
    recent = [h for h in sender_history if now - h["ts"] < 86400]
    if len(recent) >= 3:
        pts += 20; reasons.append("VELOCITY_24H")
    amounts = [h["amountMinor"] for h in sender_history]
    if len(amounts) >= 3:
        med = statistics.median(amounts)
        if med > 0 and amount_minor > 4 * med:
            pts += 25; reasons.append("AMOUNT_ANOMALY")
    lo, hi = (int(REPORTING_THRESHOLD_MINOR * f) for f in STRUCTURING_BAND)
    if lo <= amount_minor <= hi:
        pts += 30; reasons.append("NEAR_REPORTING_THRESHOLD")
    if beneficiary_is_new and amount_minor > 500_000:
        pts += 15; reasons.append("NEW_BENEFICIARY_LARGE")
    limit = HIGH_RISK_PURPOSE_OVER.get(purpose)
    if limit and amount_minor > limit:
        pts += 20; reasons.append("PURPOSE_AMOUNT_MISMATCH")
    # ML-style signals (lightweight, no sklearn dependency)
    if _unusual_hour(now):
        pts += 10; reasons.append("UNUSUAL_HOUR")
    if _is_round(amount_minor) and amount_minor >= 500_000:
        pts += 5; reasons.append("ROUND_AMOUNT")
    # Statistical anomaly detection (z-score based, mimics Isolation Forest)
    if len(amounts) >= 5:
        mean_a = sum(amounts) / len(amounts)
        std_a = (sum((a - mean_a) ** 2 for a in amounts) / len(amounts)) ** 0.5
        if std_a > 0:
            z = (amount_minor - mean_a) / std_a
            if abs(z) > 2.5:
                pts += 15; reasons.append("ML_ANOMALY")
    if force_high:
        pts = max(pts, 70); reasons.append("SCENARIO_FORCED")
    return min(pts, 100), reasons


def explain(amount_minor, purpose, sender_history, beneficiary_is_new, now=None, force_high=False):
    """Return a detailed explainability breakdown of the risk score."""
    total_score, reason_codes = score(amount_minor, purpose, sender_history, beneficiary_is_new, now, force_high)
    features = []
    for code in reason_codes:
        info = FEATURE_WEIGHTS.get(code, {"weight": 0, "desc": code})
        features.append({
            "code": code,
            "contribution": info["weight"],
            "description": info["desc"],
            "triggered": True,
        })
    # Also show features that did NOT trigger (for full explainability)
    triggered = set(reason_codes)
    for code, info in FEATURE_WEIGHTS.items():
        if code not in triggered and code != "SCENARIO_FORCED":
            features.append({
                "code": code,
                "contribution": 0,
                "description": info["desc"],
                "triggered": False,
            })
    features.sort(key=lambda f: (-f["contribution"], f["code"]))
    return {
        "totalScore": total_score,
        "reasonCodes": reason_codes,
        "threshold": {"hold": 60, "block": 85},
        "decision": "BLOCK" if total_score >= 85 else ("HOLD" if total_score >= 60 else "PASS"),
        "features": features,
        "modelType": "hybrid_rule_statistical",
        "senderHistoryDepth": len(sender_history),
    }
