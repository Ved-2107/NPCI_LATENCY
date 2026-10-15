import asyncio
import json
import logging
import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("remitchain.api")

from contextlib import asynccontextmanager

from . import auth, fx, upi
from .pii_vault import vault as pii_vault, PiiShreddedError
from .audit import filter_trail, to_csv, compliance_summary
from .calculator import compare
from .events import broadcaster
from .ledger import LedgerError, make_ledger
from .notifications import notifier
from .orchestrator import Orchestrator
from .risk import explain as risk_explain


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        loop = asyncio.get_running_loop()
        broadcaster.set_loop(loop)
        logger.info("Main asyncio loop captured for EventBroadcaster")
    except Exception as e:
        logger.warning("Could not set broadcaster loop on startup: %s", e)
    yield


app = FastAPI(title="RemitChain Hub", version="0.3.0", lifespan=lifespan)

# Configurable CORS
cors_origins_env = os.environ.get("CORS_ORIGINS", "*")
cors_origins = [o.strip() for o in cors_origins_env.split(",")] if cors_origins_env != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ledger = make_ledger()
orch = Orchestrator(ledger)
UI_DIR = Path(__file__).resolve().parents[2] / "ui"
idempotency_store: dict[str, dict] = {}


class AuthTokenRequest(BaseModel):
    userId: str
    role: str = "sender"


class QuoteRequest(BaseModel):
    corridor: str
    amountMinor: int = Field(gt=0, le=1_000_000_000)



class UpiLookupRequest(BaseModel):
    vpa: str
    declaredName: str = ""
    scenario: str = "happy"


class NewRemittance(BaseModel):
    corridor: str
    senderName: str = Field(min_length=2)
    beneficiaryName: str = Field(min_length=2)
    beneficiaryVpa: str = Field(pattern=r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$")
    purpose: str = Field(min_length=2)
    amountMinor: int = Field(gt=0, le=1_000_000_000)
    scenario: str = "happy"
    quoteId: str | None = None
    creatorId: str | None = None


class Review(BaseModel):
    approve: bool
    reviewerId: str | None = None


def guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except (LedgerError, ValueError, KeyError) as e:
        msg = str(e)
        msg_lower = msg.lower()
        if "maker cannot be checker" in msg_lower:
            raise HTTPException(status_code=403, detail={"code": "ERR_MAKER_CHECKER", "message": msg})
        if "not found" in msg_lower:
            raise HTTPException(status_code=404, detail={"code": "ERR_NOT_FOUND", "message": msg})
        if (
            "expected one of" in msg_lower or
            "already" in msg_lower or
            "not permitted" in msg_lower or
            "cannot step" in msg_lower or
            "terminal status" in msg_lower or
            "conflict" in msg_lower
        ):
            raise HTTPException(status_code=409, detail={"code": "ERR_STATE_CONFLICT", "message": msg})
        raise HTTPException(status_code=400, detail={"code": "ERR_BAD_REQUEST", "message": msg})


# ── Health & Metadata ────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"ok": True, "ledgerMode": ledger.mode, "wsConnections": broadcaster.connection_count}


@app.get("/api/corridors")
def corridors():
    return {k: fx.corridor_info(k) for k in fx.CORRIDORS}


# ── Auth & RBAC ──────────────────────────────────────────────────

@app.post("/api/auth/token")
def auth_token(body: AuthTokenRequest):
    """Issue a signed JWT access token with role claims."""
    token = auth.create_access_token(body.userId, body.role)
    return {
        "accessToken": token,
        "tokenType": "bearer",
        "userId": body.userId,
        "role": body.role,
    }


@app.get("/api/auth/me")
def auth_me(user: dict = Depends(auth.get_current_user)):
    """Return identity and roles of current authenticated user."""
    return user


# ── Quote & Pricing ─────────────────────────────────────────────

@app.post("/api/quotes")
def create_binding_quote(body: QuoteRequest):
    """Generate a binding quote with a live lock window (e.g. 5 minutes)."""
    return guard(orch.create_quote, body.corridor, body.amountMinor)


@app.get("/api/quote")
def quote(
    corridor: str = Query(..., description="Corridor code e.g. US-IN"),
    amountMinor: int = Query(..., gt=0, le=1_000_000_000, description="Amount in minor currency units"),
):
    if corridor not in fx.CORRIDORS:
        raise HTTPException(status_code=400, detail={"code": "ERR_UNSUPPORTED_CORRIDOR", "message": f"Unsupported corridor: {corridor}"})
    return guard(orch.preview, corridor, amountMinor)


@app.get("/api/compare")
def cost_compare(
    corridor: str = Query(..., description="Corridor code e.g. US-IN"),
    amountMinor: int = Query(..., gt=0, le=1_000_000_000, description="Amount in minor currency units"),
):
    if corridor not in fx.CORRIDORS:
        raise HTTPException(status_code=400, detail={"code": "ERR_UNSUPPORTED_CORRIDOR", "message": f"Unsupported corridor: {corridor}"})
    return guard(compare, corridor, amountMinor)


# ── UPI Verification ─────────────────────────────────────────────

@app.post("/api/upi/lookup")
def upi_lookup(body: UpiLookupRequest):
    """Pre-send verification of beneficiary UPI ID."""
    return upi.lookup_vpa(body.vpa, body.declaredName, scenario=body.scenario)


# ── Remittance CRUD ──────────────────────────────────────────────

@app.post("/api/remittances")
def create(body: NewRemittance, idempotency_key: str | None = Header(None, alias="Idempotency-Key")):
    if idempotency_key and idempotency_key in idempotency_store:
        logger.info("Idempotent hit for key %s", idempotency_key)
        return idempotency_store[idempotency_key]
    res = guard(orch.create, body.model_dump())
    if idempotency_key:
        idempotency_store[idempotency_key] = res
    return res


@app.get("/api/remittances")
def list_all(
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(50, ge=1, le=200, description="Page limit"),
):
    all_items = list(reversed(ledger.ListRemittances()))
    return all_items[offset:offset + limit]


@app.get("/api/remittances/{rid}")
def get_one(rid: str):
    return guard(ledger.GetRemittance, rid)


@app.get("/api/remittances/{rid}/history")
def history(rid: str):
    return guard(ledger.GetRemittanceHistory, rid)


# ── Off-Ledger Encrypted PII & GDPR ──────────────────────────────

@app.get("/api/pii/{rid}")
def get_remittance_pii(rid: str, user: dict = Depends(auth.require_role("sender", "compliance_officer", "admin"))):
    """Retrieve off-ledger decrypted PII. Returns 410 Gone if cryptographically shredded."""
    try:
        data = pii_vault.retrieve(rid)
        return {"remittanceId": rid, "status": "ACTIVE", "pii": data}
    except PiiShreddedError as e:
        raise HTTPException(status_code=410, detail={"code": "ERR_PII_SHREDDED", "message": str(e)})
    except KeyError as e:
        raise HTTPException(status_code=404, detail={"code": "ERR_NOT_FOUND", "message": str(e)})


@app.delete("/api/pii/{rid}")
def shred_remittance_pii(rid: str, user: dict = Depends(auth.require_role("sender", "compliance_officer", "admin"))):
    """GDPR Article 17 Right-to-be-Forgotten: permanently shred off-ledger PII while preserving on-chain hashes and audit proof."""
    try:
        res = pii_vault.shred(rid)
        logger.info("PII for remittance %s cryptographically shredded by user %s", rid, user.get("userId"))
        return res
    except KeyError as e:
        raise HTTPException(status_code=404, detail={"code": "ERR_NOT_FOUND", "message": str(e)})


@app.get("/api/pii/{rid}/status")
def get_remittance_pii_status(rid: str):
    """Check PII vault retention status without exposing plaintext."""
    return pii_vault.status(rid)


@app.post("/api/remittances/{rid}/step")
async def step(rid: str):
    return await run_in_threadpool(guard, orch.step, rid)


@app.post("/api/remittances/{rid}/run")
async def run(rid: str):
    return await run_in_threadpool(guard, orch.run, rid)


@app.post("/api/remittances/{rid}/review")
async def review(
    rid: str,
    body: Review,
    user: dict = Depends(auth.require_role("compliance_officer", "admin")),
    x_reviewer_id: str | None = Header(None, alias="X-Reviewer-Id")
):
    reviewer = body.reviewerId or x_reviewer_id or user.get("userId") or "compliance_officer_default"
    return await run_in_threadpool(guard, orch.review, rid, body.approve, reviewer_id=reviewer)


@app.get("/api/compliance/pending")
def compliance_pending():
    """List pending HELD remittances with elapsed SLA timers and risk breakdown."""
    import time
    rs = ledger.ListRemittances()
    held = [r for r in rs if r["status"] == "HELD"]
    now = time.time()
    results = []
    for r in held:
        trail = r.get("trail", [])
        hold_trail = next((t for t in reversed(trail) if t["step"] in ("SCREEN", "HELD")), None)
        hold_ts = hold_trail.get("ts", r.get("updatedAt", now)) if hold_trail else r.get("updatedAt", now)
        elapsed_sec = int(now - hold_ts)
        meta = orch.meta.get(r["id"], {})
        results.append({
            **r,
            "creatorId": meta.get("creatorId", meta.get("senderName", "remitter")),
            "holdTimestamp": hold_ts,
            "elapsedSeconds": elapsed_sec,
            "slaBreached": elapsed_sec > 900,
            "riskBreakdown": meta.get("risk_breakdown", {}),
        })
    return results



# ── Risk Explainability ─────────────────────────────────────────

@app.get("/api/remittances/{rid}/risk")
def risk_detail(rid: str):
    """Return persisted explainability breakdown for a remittance."""
    return guard(orch.get_risk_detail, rid)


# ── Stats ────────────────────────────────────────────────────────

@app.get("/api/stats")
def stats():
    return orch.stats()


@app.get("/api/latency")
def latency_telemetry():
    """Retrieve detailed per-step latency metrics, percentiles (p50/p90/p95/p99) and benchmarks."""
    return orch.get_latency_telemetry()



# ── Audit & Compliance ──────────────────────────────────────────

@app.get("/api/audit")
def audit(
    status: str = None, corridor: str = None,
    from_ts: int = None, to_ts: int = None,
    min_risk: int = None, search: str = None,
    user: dict = Depends(auth.require_role("auditor", "compliance_officer", "admin")),
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
            await ws.send_text(json.dumps(event))
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
