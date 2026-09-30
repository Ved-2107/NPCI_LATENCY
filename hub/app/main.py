import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import fx
from .ledger import LedgerError, make_ledger
from .orchestrator import Orchestrator

app = FastAPI(title="RemitChain Hub", version="0.1.0")
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


@app.get("/api/health")
def health():
    return {"ok": True, "ledgerMode": ledger.mode}


@app.get("/api/corridors")
def corridors():
    return {k: {"name": v["name"], "ccy": v["ccy"]} for k, v in fx.CORRIDORS.items()}


@app.get("/api/quote")
def quote(corridor: str, amountMinor: int):
    return guard(orch.preview, corridor, amountMinor)


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


@app.get("/api/stats")
def stats():
    return orch.stats()


@app.get("/")
def index():
    return FileResponse(UI_DIR / "index.html")


if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=UI_DIR), name="static")
