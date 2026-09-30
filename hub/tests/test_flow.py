import json
import pathlib
import pytest
from fastapi.testclient import TestClient

from app.ledger import LedgerError, MemoryLedger, PAYOUT, REMITTER
from app.pricing import compute_quote

ROOT = pathlib.Path(__file__).resolve().parents[2]


def body(**kw):
    b = {"corridor": "US-IN", "senderName": "Asha Rao", "beneficiaryName": "Meera Rao",
         "beneficiaryVpa": "meera@okbank", "purpose": "FAMILY_MAINTENANCE", "amountMinor": 100000}
    b.update(kw)
    return b


@pytest.fixture()
def client():
    import app.main as m
    m.ledger = MemoryLedger()
    m.orch.__init__(m.ledger)
    return TestClient(m.app)


def run(client, **kw):
    rid = client.post("/api/remittances", json=body(**kw)).json()["id"]
    return client.post(f"/api/remittances/{rid}/run").json()


def test_shared_quote_vectors():
    for v in json.loads((ROOT / "testvectors/quote_vectors.json").read_text()):
        i = v["input"]
        q = compute_quote(v["ccy"], i["sendMinor"], i["midMicro"], i["spreadBps"], i["feeFlat"], i["feeBps"])
        for k, want in v["expect"].items():
            assert q[k] == want, (v["name"], k)


def test_happy_path_settles(client):
    r = run(client)
    assert r["status"] == "SETTLED" and r["upiRef"]
    assert [t["org"] for t in r["trail"]][0] == REMITTER and r["trail"][-1]["org"] == PAYOUT
    assert r["quote"]["costBps"] < 650


def test_sanctions_blocks_then_refunds(client):
    assert run(client, scenario="sanctions_hit")["status"] == "REFUNDED"


def test_high_risk_holds_then_approve_settles(client):
    r = run(client, scenario="high_risk")
    assert r["status"] == "HELD"
    client.post(f"/api/remittances/{r['id']}/review", json={"approve": True})
    assert client.post(f"/api/remittances/{r['id']}/run").json()["status"] == "SETTLED"


def test_payout_failure_refunds(client):
    r = run(client, scenario="payout_fail")
    assert r["status"] == "REFUNDED" and r["failReason"]


def test_bad_beneficiary_refunds(client):
    assert run(client, scenario="bad_beneficiary")["status"] == "REFUNDED"


def test_org_roles_enforced():
    L = MemoryLedger()
    with pytest.raises(LedgerError):
        L.CreateRemittance(PAYOUT, "X1", "AE-IN", "s", "b", "GIFT")


def test_payout_ref_cannot_be_reused():
    L = MemoryLedger()
    for rid in ("A", "B"):
        L.CreateRemittance(REMITTER, rid, "US-IN", "s", "b" + rid, "GIFT")
        L.LockQuote(REMITTER, rid, "USD", 100000, 88000000, 30, 100, 10, 300)
        L.RecordScreening(REMITTER, rid, 5, False, "")
        L.VerifyBeneficiary(PAYOUT, rid, 100)
        L.ConfirmFunding(REMITTER, rid, "F" + rid)
    L.SubmitPayout(PAYOUT, "A", "PAY1")
    L.SubmitPayout(PAYOUT, "A", "PAY1")  # idempotent
    with pytest.raises(LedgerError):
        L.SubmitPayout(PAYOUT, "B", "PAY1")


def test_cannot_skip_states():
    L = MemoryLedger()
    L.CreateRemittance(REMITTER, "S1", "US-IN", "s", "b", "GIFT")
    with pytest.raises(LedgerError):
        L.ConfirmFunding(REMITTER, "S1", "F")


def test_expired_quote_moves_to_expired(client):
    assert run(client, scenario="quote_expired")["status"] == "REFUNDED"
