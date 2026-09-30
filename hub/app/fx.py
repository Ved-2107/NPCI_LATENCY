"""Simulated FX + corridor fee schedule. Rates are INDICATIVE DEMO VALUES, not market data."""
import time

# corridor -> currency, base mid rate (INR per unit, micro), spread bps, flat fee (minor), fee bps
# decimals: number of minor-unit digits in the send currency (cents=2, fils=3, yen=0)
CORRIDORS = {
    "AE-IN": {"name": "UAE to India", "ccy": "AED", "mid": 23.95, "spread": 25, "flat": 100, "bps": 10, "decimals": 2, "flag": "🇦🇪"},
    "US-IN": {"name": "USA to India", "ccy": "USD", "mid": 88.00, "spread": 30, "flat": 100, "bps": 10, "decimals": 2, "flag": "🇺🇸"},
    "SG-IN": {"name": "Singapore to India", "ccy": "SGD", "mid": 68.50, "spread": 30, "flat": 100, "bps": 10, "decimals": 2, "flag": "🇸🇬"},
    "GB-IN": {"name": "UK to India", "ccy": "GBP", "mid": 118.50, "spread": 35, "flat": 100, "bps": 10, "decimals": 2, "flag": "🇬🇧"},
    "CA-IN": {"name": "Canada to India", "ccy": "CAD", "mid": 65.20, "spread": 30, "flat": 100, "bps": 10, "decimals": 2, "flag": "🇨🇦"},
    "AU-IN": {"name": "Australia to India", "ccy": "AUD", "mid": 58.40, "spread": 30, "flat": 100, "bps": 10, "decimals": 2, "flag": "🇦🇺"},
    "EU-IN": {"name": "Europe to India", "ccy": "EUR", "mid": 96.30, "spread": 28, "flat": 100, "bps": 10, "decimals": 2, "flag": "🇪🇺"},
    "JP-IN": {"name": "Japan to India", "ccy": "JPY", "mid": 0.587, "spread": 35, "flat": 500, "bps": 15, "decimals": 0, "flag": "🇯🇵"},
    "KR-IN": {"name": "South Korea to India", "ccy": "KRW", "mid": 0.0635, "spread": 40, "flat": 50000, "bps": 15, "decimals": 0, "flag": "🇰🇷"},
    "BH-IN": {"name": "Bahrain to India", "ccy": "BHD", "mid": 233.10, "spread": 20, "flat": 50, "bps": 8, "decimals": 3, "flag": "🇧🇭"},
    "KW-IN": {"name": "Kuwait to India", "ccy": "KWD", "mid": 286.50, "spread": 22, "flat": 30, "bps": 8, "decimals": 3, "flag": "🇰🇼"},
    "MY-IN": {"name": "Malaysia to India", "ccy": "MYR", "mid": 18.90, "spread": 30, "flat": 200, "bps": 12, "decimals": 2, "flag": "🇲🇾"},
}
# Traditional average all-in cost, used only as a comparison bar in the UI (verify before citing).
BENCHMARK_COST_BPS = 650

# Corridor-specific daily caps (paise), overrides the default in chaincode
CORRIDOR_DAILY_CAPS = {
    "JP-IN": 1_000_000_000,   # higher cap for yen corridor
    "KR-IN": 1_000_000_000,   # higher cap for won corridor
    "BH-IN": 200_000_000,     # tighter corridor
}


def mid_rate_micro(corridor: str) -> int:
    base = CORRIDORS[corridor]["mid"]
    # tiny deterministic drift per minute so quotes visibly change
    drift = ((int(time.time()) // 60) % 7 - 3) * 0.0005
    return int(round(base * (1 + drift) * 1_000_000))


def schedule(corridor: str) -> dict:
    c = CORRIDORS[corridor]
    return {"ccy": c["ccy"], "mid": mid_rate_micro(corridor), "spread": c["spread"], "flat": c["flat"], "bps": c["bps"]}


def corridor_info(corridor: str) -> dict:
    """Return full corridor metadata including decimals and flag."""
    c = CORRIDORS[corridor]
    return {
        "name": c["name"], "ccy": c["ccy"], "decimals": c.get("decimals", 2),
        "flag": c.get("flag", ""),
        "dailyCapPaise": CORRIDOR_DAILY_CAPS.get(corridor, 500_000_000),
    }
