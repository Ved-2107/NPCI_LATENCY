"""Audit trail filtering, search, and export for compliance reporting.

Provides filterable access to the remittance audit trail with CSV export
for regulatory compliance. All data comes from the ledger's trail entries.
"""
import csv
import io
import time
from datetime import datetime, timezone


def filter_trail(remittances: list, filters: dict) -> list:
    """Filter remittances by status, corridor, date range, risk level, and search text.

    filters:
        status: str or list of status values
        corridor: str
        from_ts: int (unix timestamp)
        to_ts: int (unix timestamp)
        min_risk: int
        search: str (matches against ID, corridor, purpose)
    """
    results = list(remittances)

    if filters.get("status"):
        statuses = filters["status"] if isinstance(filters["status"], list) else [filters["status"]]
        results = [r for r in results if r["status"] in statuses]

    if filters.get("corridor"):
        results = [r for r in results if r.get("corridor") == filters["corridor"]]

    if filters.get("from_ts"):
        results = [r for r in results if r.get("createdAt", 0) >= filters["from_ts"]]

    if filters.get("to_ts"):
        results = [r for r in results if r.get("createdAt", 0) <= filters["to_ts"]]

    if filters.get("min_risk") is not None:
        results = [r for r in results if r.get("riskScore", 0) >= filters["min_risk"]]

    if filters.get("search"):
        q = filters["search"].lower()
        results = [r for r in results if q in r.get("id", "").lower()
                   or q in r.get("corridor", "").lower()
                   or q in r.get("purpose", "").lower()
                   or q in r.get("status", "").lower()]

    return results


def to_csv(remittances: list) -> str:
    """Export remittances to CSV format for compliance reporting."""
    output = io.StringIO()
    fields = [
        "id", "corridor", "status", "purpose", "riskScore",
        "sendCurrency", "sendAmount", "receivePaise", "costBps",
        "fundingRef", "payoutRef", "upiRef", "refundRef",
        "failReason", "nameMatchScore", "funded",
        "createdAt", "updatedAt", "trailSteps",
    ]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for r in remittances:
        q = r.get("quote") or {}
        row = {
            "id": r.get("id", ""),
            "corridor": r.get("corridor", ""),
            "status": r.get("status", ""),
            "purpose": r.get("purpose", ""),
            "riskScore": r.get("riskScore", 0),
            "sendCurrency": q.get("sendCurrency", ""),
            "sendAmount": q.get("sendAmountMinor", 0),
            "receivePaise": q.get("receivePaise", 0),
            "costBps": q.get("costBps", 0),
            "fundingRef": r.get("fundingRef", ""),
            "payoutRef": r.get("payoutRef", ""),
            "upiRef": r.get("upiRef", ""),
            "refundRef": r.get("refundRef", ""),
            "failReason": r.get("failReason", ""),
            "nameMatchScore": r.get("nameMatchScore", 0),
            "funded": r.get("funded", False),
            "createdAt": _ts(r.get("createdAt", 0)),
            "updatedAt": _ts(r.get("updatedAt", 0)),
            "trailSteps": " → ".join(t["step"] for t in r.get("trail", [])),
        }
        writer.writerow(row)
    return output.getvalue()


def compliance_summary(remittances: list) -> dict:
    """Generate an aggregate compliance summary."""
    total = len(remittances)
    by_status = {}
    by_corridor = {}
    high_risk = []
    total_volume_paise = 0
    total_fees_minor = 0

    for r in remittances:
        st = r.get("status", "UNKNOWN")
        by_status[st] = by_status.get(st, 0) + 1
        cor = r.get("corridor", "UNKNOWN")
        by_corridor[cor] = by_corridor.get(cor, 0) + 1
        if r.get("riskScore", 0) >= 60:
            high_risk.append({"id": r["id"], "riskScore": r["riskScore"],
                              "status": r["status"], "reasonCodes": r.get("reasonCodes", [])})
        q = r.get("quote")
        if q:
            total_volume_paise += q.get("receivePaise", 0)
            total_fees_minor += q.get("feeTotalMinor", 0)

    return {
        "generatedAt": _ts(time.time()),
        "totalTransfers": total,
        "byStatus": by_status,
        "byCorridor": by_corridor,
        "highRiskTransfers": high_risk,
        "holdRate": round(by_status.get("HELD", 0) / total * 100, 1) if total else 0,
        "blockRate": round(by_status.get("BLOCKED", 0) / total * 100, 1) if total else 0,
        "refundRate": round(by_status.get("REFUNDED", 0) / total * 100, 1) if total else 0,
        "totalVolumePaise": total_volume_paise,
        "totalFeesMinor": total_fees_minor,
    }


def _ts(unix: float) -> str:
    if not unix:
        return ""
    return datetime.fromtimestamp(unix, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
