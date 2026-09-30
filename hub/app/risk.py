"""Explainable payment risk scoring. Produces a 0-100 score plus reason codes.
It advises; the chaincode enforces thresholds, so a wrong score cannot bypass policy.
Upgrade path: swap `score` for an Isolation Forest / GNN model with the same signature."""
import statistics
import time

HIGH_RISK_PURPOSE_OVER = {"GIFT": 300_000, "INVESTMENT": 1_000_000}  # minor units
STRUCTURING_BAND = (0.90, 0.999)
REPORTING_THRESHOLD_MINOR = 1_000_000  # 10,000.00 in send currency (demo)


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
    if force_high:
        pts = max(pts, 70); reasons.append("SCENARIO_FORCED")
    return min(pts, 100), reasons
