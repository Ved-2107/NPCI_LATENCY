"""Simulated FX + corridor fee schedule. Rates are INDICATIVE DEMO VALUES, not market data."""
import time

# corridor -> currency, base mid rate (INR per unit, micro), spread bps, flat fee (minor), fee bps
CORRIDORS = {
    "AE-IN": {"name": "UAE to India", "ccy": "AED", "mid": 23.95, "spread": 25, "flat": 100, "bps": 10},
    "US-IN": {"name": "USA to India", "ccy": "USD", "mid": 88.00, "spread": 30, "flat": 100, "bps": 10},
    "SG-IN": {"name": "Singapore to India", "ccy": "SGD", "mid": 68.50, "spread": 30, "flat": 100, "bps": 10},
    "GB-IN": {"name": "UK to India", "ccy": "GBP", "mid": 118.50, "spread": 35, "flat": 100, "bps": 10},
}
# Traditional average all-in cost, used only as a comparison bar in the UI (verify before citing).
BENCHMARK_COST_BPS = 650


def mid_rate_micro(corridor: str) -> int:
    base = CORRIDORS[corridor]["mid"]
    # tiny deterministic drift per minute so quotes visibly change
    drift = ((int(time.time()) // 60) % 7 - 3) * 0.0005
    return int(round(base * (1 + drift) * 1_000_000))


def schedule(corridor: str) -> dict:
    c = CORRIDORS[corridor]
    return {"ccy": c["ccy"], "mid": mid_rate_micro(corridor), "spread": c["spread"], "flat": c["flat"], "bps": c["bps"]}
