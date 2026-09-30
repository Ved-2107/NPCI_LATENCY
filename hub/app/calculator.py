"""Comparative cost calculator.

Compares RemitChain's all-in cost against traditional providers (demo data).
Generates annual savings projections and provider comparison tables.
"""
from . import fx
from .pricing import compute_quote

# Benchmark costs by provider (basis points, all-in including FX margin + fees).
# These are approximate industry averages for a USD 1,000 equivalent transfer.
PROVIDERS = {
    "remitchain": {"name": "RemitChain", "type": "blockchain", "costBps": None},  # computed live
    "bank_wire": {"name": "Traditional bank wire", "type": "traditional", "costBps": 650},
    "western_union": {"name": "Western Union", "type": "mto", "costBps": 580},
    "wise": {"name": "Wise (TransferWise)", "type": "fintech", "costBps": 120},
    "paypal": {"name": "PayPal / Xoom", "type": "fintech", "costBps": 350},
    "remitly": {"name": "Remitly", "type": "fintech", "costBps": 200},
    "instarem": {"name": "InstaRem", "type": "fintech", "costBps": 150},
}


def compare(corridor: str, amount_minor: int) -> dict:
    """Compare RemitChain cost against all providers for a given corridor and amount."""
    s = fx.schedule(corridor)
    q = compute_quote(s["ccy"], amount_minor, s["mid"], s["spread"], s["flat"], s["bps"])
    rc_cost_bps = q["costBps"]
    rc_receive = q["receivePaise"]
    mid_receive = amount_minor * s["mid"] // 1_000_000  # what you'd get at mid-market

    comparisons = []
    for pid, p in PROVIDERS.items():
        cost_bps = rc_cost_bps if pid == "remitchain" else p["costBps"]
        # estimate receive amount: mid_receive * (1 - costBps/10000)
        est_receive = mid_receive * (10000 - cost_bps) // 10000 if pid != "remitchain" else rc_receive
        saving_paise = est_receive - rc_receive if pid != "remitchain" else 0
        comparisons.append({
            "provider": p["name"],
            "type": p["type"],
            "costBps": cost_bps,
            "costPercent": round(cost_bps / 100, 2),
            "estimatedReceivePaise": est_receive if pid != "remitchain" else rc_receive,
            "savingVsRemitChain": saving_paise,
        })

    comparisons.sort(key=lambda c: c["costBps"])

    # Annual savings projection (assuming monthly transfers)
    bank_cost = PROVIDERS["bank_wire"]["costBps"]
    monthly_saving_paise = mid_receive * (bank_cost - rc_cost_bps) // 10000
    annual_saving_paise = monthly_saving_paise * 12

    return {
        "corridor": corridor,
        "sendCurrency": s["ccy"],
        "sendAmountMinor": amount_minor,
        "remitChainCostBps": rc_cost_bps,
        "remitChainReceivePaise": rc_receive,
        "providers": comparisons,
        "savingsVsBankWire": {
            "perTransferPaise": mid_receive * (bank_cost - rc_cost_bps) // 10000,
            "monthlyPaise": monthly_saving_paise,
            "annualPaise": annual_saving_paise,
            "annualRupees": round(annual_saving_paise / 100, 2),
        },
        "benchmarkCostBps": fx.BENCHMARK_COST_BPS,
    }
