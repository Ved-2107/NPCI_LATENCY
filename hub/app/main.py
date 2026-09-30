import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import fx
from .audit import filter_trail, to_csv, compliance_summary
from .calculator import compare
from .events import broadcaster
from .ledger import LedgerError, make_ledger
from .notifications import notifier
from .orchestrator import Orchestrator
from .risk import explain as risk_explain

app = FastAPI(title="RemitChain Hub", version="0.2.0")
ledger = make_ledger()
orch = Orchestrator(ledger)
UI_DIR = Path(__file__).resolve().parents[2] / "ui"


class NewRemittance(BaseModel):
    corridor: str
    senderName: str = Field(min_length=2)
    beneficiaryName: str = Field(min_length=2)
    beneficiaryVpa: str
    purpose: str
    amountMinor: int = Field(gt=0)
    scenario: str = "happy"


class Review(BaseModel):
    approve: bool


def guard(fn, *a):
    try:
        return fn(*a)
    except (LedgerError, ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.on_event("startup")
async def on_startup():
    import asyncio
    try:
        broadcaster._loop = asyncio.get_running_loop()
    except RuntimeError:
        pass


# ── Health & Metadata ────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"ok": True, "ledgerMode": ledger.mode, "wsConnections": broadcaster.connection_count}


@app.get("/api/corridors")
def corridors():
    return {k: fx.corridor_info(k) for k in fx.CORRIDORS}


# ── Quote & Pricing ─────────────────────────────────────────────

@app.get("/api/quote")
def quote(corridor: str, amountMinor: int):
    return guard(orch.preview, corridor, amountMinor)


@app.get("/api/compare")
def cost_compare(corridor: str, amountMinor: int):
    return guard(compare, corridor, amountMinor)


# ── Remittance CRUD ──────────────────────────────────────────────

@app.post("/api/remittances")
def create(body: NewRemittance):
    return guard(orch.create, body.model_dump())


@app.get("/api/remittances")
def list_all():
    return list(reversed(ledger.ListRemittances()))


@app.get("/api/remittances/{rid}")
def get_one(rid: str):
    return guard(ledger.GetRemittance, rid)


@app.get("/api/remittances/{rid}/history")
def history(rid: str):
    return guard(ledger.GetRemittanceHistory, rid)


@app.post("/api/remittances/{rid}/step")
def step(rid: str):
    return guard(orch.step, rid)


@app.post("/api/remittances/{rid}/run")
def run(rid: str):
    return guard(orch.run, rid)


@app.post("/api/remittances/{rid}/review")
def review(rid: str, body: Review):
    return guard(orch.review, rid, body.approve)


# ── Risk Explainability ─────────────────────────────────────────

@app.get("/api/remittances/{rid}/risk")
def risk_detail(rid: str):
    """Return SHAP-style risk explainability for a remittance."""
    r = guard(ledger.GetRemittance, rid)
    meta = orch.meta.get(rid, {})
    hist = orch.history.get(meta.get("senderHash", ""), [])
    return risk_explain(
        meta.get("amountMinor", 0),
        r.get("purpose", ""),
        hist,
        meta.get("newBeneficiary", False),
    )


# ── Stats ────────────────────────────────────────────────────────

@app.get("/api/stats")
def stats():
    return orch.stats()


# ── Audit & Compliance ──────────────────────────────────────────

@app.get("/api/audit")
def audit(
    status: str = None, corridor: str = None,
    from_ts: int = None, to_ts: int = None,
    min_risk: int = None, search: str = None,
):
    rs = ledger.ListRemittances()
    filters = {k: v for k, v in {
        "status": status, "corridor": corridor,
        "from_ts": from_ts, "to_ts": to_ts,
        "min_risk": min_risk, "search": search,
    }.items() if v is not None}
    return filter_trail(rs, filters)


@app.get("/api/audit/export")
def audit_export():
    rs = ledger.ListRemittances()
    csv_data = to_csv(rs)
    return Response(content=csv_data, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=remitchain_audit.csv"})


@app.get("/api/audit/summary")
def audit_summary():
    return compliance_summary(ledger.ListRemittances())


# ── Notifications ────────────────────────────────────────────────

@app.get("/api/notifications")
def get_notifications(limit: int = 50):
    return {"notifications": notifier.get_all(limit), "unread": notifier.unread_count()}


@app.get("/api/notifications/{rid}")
def get_remittance_notifications(rid: str):
    return notifier.get_for_remittance(rid)


@app.post("/api/notifications/{rid}/read")
def mark_notifications_read(rid: str):
    notifier.mark_read(rid)
    return {"ok": True}


# ── Beneficiary Tracking ────────────────────────────────────────

@app.get("/api/track/{rid}")
def track_transfer(rid: str):
    """Public-facing transfer tracking (beneficiary can check status)."""
    r = guard(ledger.GetRemittance, rid)
    q = r.get("quote") or {}
    return {
        "id": r["id"],
        "status": r["status"],
        "receivePaise": q.get("receivePaise"),
        "sendCurrency": q.get("sendCurrency"),
        "steps": [{"step": t["step"], "status": t["status"],
                    "signedBy": "Remitting bank" if t["org"] == "Org1MSP" else "Payout rail"}
                   for t in r.get("trail", [])],
        "notifications": notifier.get_for_remittance(rid),
    }


# ── WebSocket ────────────────────────────────────────────────────

@app.websocket("/ws/events")
async def ws_events(ws: WebSocket):
    await broadcaster.connect(ws)
    try:
        # Send recent events on connect
        for event in broadcaster.recent_events[-20:]:
            await ws.send_text(__import__("json").dumps(event))
        while True:
            await ws.receive_text()  # keep connection alive
    except WebSocketDisconnect:
        broadcaster.disconnect(ws)


@app.get("/api/events")
def recent_events(limit: int = 50):
    return broadcaster.recent_events[-limit:]


# ── UI Serving ───────────────────────────────────────────────────

@app.get("/")
def index():
    return FileResponse(UI_DIR / "index.html")


if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=UI_DIR), name="static")
