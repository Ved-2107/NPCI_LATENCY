"""Explainable payment risk scoring with statistical anomaly detection.

Produces a 0-100 score plus reason codes. It advises; the chaincode
enforces thresholds, so an off-chain score cannot bypass on-chain policy.

Uses multi-factor risk rules combined with statistical anomaly detection
(z-score variance and velocity windows) normalized to USD-equivalent values.
"""
import math
import statistics
import time

from . import fx

# USD-equivalent thresholds (in cents: 100 cents = $1.00 USD)
REPORTING_THRESHOLD_USD_CENTS = 1_000_000  # $10,000.00 USD
STRUCTURING_BAND = (0.90, 0.999)           # $9,000 - $9,990 USD
NEW_BENEFICIARY_LARGE_USD = 500_000       # $5,000.00 USD
HIGH_RISK_PURPOSE_OVER_USD = {"GIFT": 300_000, "INVESTMENT": 1_000_000}  # $3,000 / $10,000 USD

# Feature weights for explainability
FEATURE_WEIGHTS = {
    "VELOCITY_24H": {"weight": 20, "desc": "More than 3 transfers in 24 hours"},
    "AMOUNT_ANOMALY": {"weight": 25, "desc": "Amount is 4x the sender's historical median"},
    "NEAR_REPORTING_THRESHOLD": {"weight": 30, "desc": "Amount near $10,000 regulatory reporting threshold"},
    "NEW_BENEFICIARY_LARGE": {"weight": 15, "desc": "Transfer > $5,000 USD equivalent to a new beneficiary"},
    "PURPOSE_AMOUNT_MISMATCH": {"weight": 20, "desc": "Amount unusually high for stated purpose"},
    "STATISTICAL_ANOMALY": {"weight": 15, "desc": "Statistical anomaly: amount > 2.5 std devs from sender mean"},
    "UNUSUAL_HOUR": {"weight": 10, "desc": "Transfer initiated during off-peak hours (UTC 00:00-05:00)"},
    "ROUND_AMOUNT": {"weight": 5, "desc": "Suspiciously round large transfer amount"},
    "SCENARIO_FORCED": {"weight": 0, "desc": "Risk elevated for simulated demo scenario"},
}


def to_usd_cents(amount_minor: int, corridor: str = None) -> int:
    """Normalize local minor currency amount to USD cents equivalent using mid-market rate."""
    if not corridor or corridor == "US-IN":
        return amount_minor
    info = fx.CORRIDORS.get(corridor)
    if not info:
        return amount_minor
    decimals = info.get("decimals", 2)
    mid_inr = info.get("mid", 88.0)
    usd_mid_inr = fx.CORRIDORS.get("US-IN", {}).get("mid", 88.0)
    major_units = amount_minor / (10 ** decimals)
    usd_major = (major_units * mid_inr) / usd_mid_inr
    return int(round(usd_major * 100))


def _is_round(amount_minor: int, usd_cents: int) -> bool:
    """Check if the amount is suspiciously round for large transfers."""
    if amount_minor <= 0 or usd_cents < 100_000:
        return False
    magnitude = 10 ** (len(str(amount_minor)) - 1)
    return amount_minor % (magnitude // 10) == 0


def _unusual_hour(now: float) -> bool:
    """Check if the transaction is at an unusual hour (UTC 0-5)."""
    hour = int(now % 86400) // 3600
    return hour < 5


def score(amount_minor, purpose, sender_history, beneficiary_is_new, now=None, force_high=False, corridor=None):
    """Calculate 0-100 risk score and list of triggered reason codes."""
    now = now or time.time()
    pts, reasons = 0, []
    usd_cents = to_usd_cents(amount_minor, corridor)

    recent = [h for h in sender_history if now - h["ts"] < 86400]
    if len(recent) >= 3:
        pts += 20
        reasons.append("VELOCITY_24H")

    amounts = [h["amountMinor"] for h in sender_history]
    if len(amounts) >= 3:
        med = statistics.median(amounts)
        if med > 0 and amount_minor > 4 * med:
            pts += 25
            reasons.append("AMOUNT_ANOMALY")

    lo, hi = (int(REPORTING_THRESHOLD_USD_CENTS * f) for f in STRUCTURING_BAND)
    if lo <= usd_cents <= hi:
        pts += 30
        reasons.append("NEAR_REPORTING_THRESHOLD")

    if beneficiary_is_new and usd_cents > NEW_BENEFICIARY_LARGE_USD:
        pts += 15
        reasons.append("NEW_BENEFICIARY_LARGE")

    limit = HIGH_RISK_PURPOSE_OVER_USD.get(purpose)
    if limit and usd_cents > limit:
        pts += 20
        reasons.append("PURPOSE_AMOUNT_MISMATCH")

    if _unusual_hour(now):
        pts += 10
        reasons.append("UNUSUAL_HOUR")

    if _is_round(amount_minor, usd_cents):
        pts += 5
        reasons.append("ROUND_AMOUNT")

    # Statistical anomaly detection (z-score on historical amounts)
    if len(amounts) >= 5:
        mean_a = sum(amounts) / len(amounts)
        std_a = (sum((a - mean_a) ** 2 for a in amounts) / len(amounts)) ** 0.5
        if std_a > 0:
            z = (amount_minor - mean_a) / std_a
            if abs(z) > 2.5:
                pts += 15
                reasons.append("STATISTICAL_ANOMALY")

    if force_high:
        pts = max(pts, 75)
        reasons.append("SCENARIO_FORCED")

    return min(pts, 100), reasons


def explain(amount_minor, purpose, sender_history, beneficiary_is_new, now=None, force_high=False, corridor=None):
    """Return an explainability breakdown of the risk score."""
    total_score, reason_codes = score(amount_minor, purpose, sender_history, beneficiary_is_new, now, force_high, corridor)
    features = []
    for code in reason_codes:
        info = FEATURE_WEIGHTS.get(code, {"weight": 0, "desc": code})
        features.append({
            "code": code,
            "contribution": info["weight"],
            "description": info["desc"],
            "triggered": True,
        })
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
        "modelType": "hybrid_statistical_rules",
        "senderHistoryDepth": len(sender_history),
        "usdEquivalentCents": to_usd_cents(amount_minor, corridor),
    }


def score_and_explain(amount_minor, purpose, sender_history, beneficiary_is_new, now=None, force_high=False, corridor=None):
    """Convenience helper to compute both score and explanation in a single pass."""
    breakdown = explain(amount_minor, purpose, sender_history, beneficiary_is_new, now, force_high, corridor)
    return breakdown["totalScore"], breakdown["reasonCodes"], breakdown
