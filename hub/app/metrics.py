"""Prometheus text-format metrics exporter for RemitChain hub.

Exposes standard Prometheus metrics covering transaction throughput, settlement
latencies, corridor distribution, volume, and active real-time connections.
"""


def render_prometheus_metrics(ledger, orch, broadcaster) -> str:
    rs = ledger.ListRemittances()
    ws_count = broadcaster.connection_count

    # Counts by corridor and status
    counts = {}
    held_count = 0
    total_volume_paise = 0

    for r in rs:
        st = r.get("status", "UNKNOWN")
        c = r.get("corridor", "UNKNOWN")
        key = (c, st)
        counts[key] = counts.get(key, 0) + 1
        if st == "HELD":
            held_count += 1
        if st == "SETTLED" and r.get("quote"):
            total_volume_paise += r["quote"].get("receivePaise", 0)

    total_volume_inr = round(total_volume_paise / 100.0, 2)

    lines = [
        "# HELP remitchain_transfers_total Total number of remittances by corridor and status.",
        "# TYPE remitchain_transfers_total counter",
    ]
    for (corridor, status), cnt in sorted(counts.items()):
        lines.append(f'remitchain_transfers_total{{corridor="{corridor}",status="{status}"}} {cnt}')

    lines.extend([
        "# HELP remitchain_transfers_held_current Current number of remittances held for compliance review.",
        "# TYPE remitchain_transfers_held_current gauge",
        f"remitchain_transfers_held_current {held_count}",
        "# HELP remitchain_active_websockets Number of currently connected WebSocket clients.",
        "# TYPE remitchain_active_websockets gauge",
        f"remitchain_active_websockets {ws_count}",
        "# HELP remitchain_settled_volume_inr_total Cumulative total volume settled in INR.",
        "# TYPE remitchain_settled_volume_inr_total counter",
        f"remitchain_settled_volume_inr_total {total_volume_inr}",
    ])

    # Telemetry speedup and avg latency
    telemetry = orch.get_latency_telemetry()
    avg_sec = round((telemetry.get("summary", {}).get("avgMs", 0) or 0) / 1000.0, 4)
    speedup = telemetry.get("speedupVsSwift", 0) or 0

    lines.extend([
        "# HELP remitchain_settlement_duration_seconds Average end-to-end settlement duration in seconds.",
        "# TYPE remitchain_settlement_duration_seconds gauge",
        f"remitchain_settlement_duration_seconds {avg_sec}",
        "# HELP remitchain_speedup_vs_swift Factor by which RemitChain settlement is faster than SWIFT GPI (48 hours).",
        "# TYPE remitchain_speedup_vs_swift gauge",
        f"remitchain_speedup_vs_swift {speedup}",
    ])

    return "\n".join(lines) + "\n"
