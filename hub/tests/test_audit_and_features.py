import json
import pytest
from fastapi.testclient import TestClient

from app.ledger import MemoryLedger


def create_body(**kw):
    b = {
        "corridor": "US-IN",
        "senderName": "Asha Rao",
        "beneficiaryName": "Meera Rao",
        "beneficiaryVpa": "meera@okbank",
        "purpose": "FAMILY_MAINTENANCE",
        "amountMinor": 100000,
        "scenario": "happy",
    }
    b.update(kw)
    return b


@pytest.fixture()
def client():
    import app.main as m
    m.ledger = MemoryLedger()
    m.orch.__init__(m.ledger, step_delay=0, expired_delay=0)
    with TestClient(m.app) as c:
        yield c


def test_audit_trail_filtering_and_export(client):
    # Create two remittances
    r1 = client.post("/api/remittances", json=create_body(senderName="Sender One")).json()
    client.post(f"/api/remittances/{r1['id']}/run")

    r2 = client.post("/api/remittances", json=create_body(corridor="AE-IN", senderName="Sender Two")).json()
    client.post(f"/api/remittances/{r2['id']}/run")

    # Audit list with corridor filter
    resp = client.get("/api/audit?corridor=US-IN")
    assert resp.status_code == 200
    items = resp.json()
    assert all(item["corridor"] == "US-IN" for item in items)

    # Audit summary
    summary_resp = client.get("/api/audit/summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["totalTransfers"] >= 2
    assert summary["byStatus"]["SETTLED"] >= 2

    # CSV Export
    csv_resp = client.get("/api/audit/export")
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    csv_text = csv_resp.text
    assert "id,corridor" in csv_text
    assert r1["id"] in csv_text


def test_notifications_lifecycle(client):
    r = client.post("/api/remittances", json=create_body()).json()
    rid = r["id"]
    client.post(f"/api/remittances/{rid}/run")

    # Fetch notifications for this remittance
    notes_resp = client.get(f"/api/notifications/{rid}")
    assert notes_resp.status_code == 200
    notes = notes_resp.json()
    assert len(notes) > 0

    # Fetch all notifications and unread count
    all_resp = client.get("/api/notifications")
    assert all_resp.status_code == 200
    data = all_resp.json()
    assert "notifications" in data
    assert "unread" in data

    # Mark as read
    read_resp = client.post(f"/api/notifications/{rid}/read")
    assert read_resp.status_code == 200
    assert read_resp.json()["ok"] is True


def test_risk_explainability(client):
    r = client.post("/api/remittances", json=create_body(scenario="high_risk")).json()
    rid = r["id"]

    risk_resp = client.get(f"/api/remittances/{rid}/risk")
    assert risk_resp.status_code == 200
    data = risk_resp.json()
    assert data["totalScore"] >= 70
    assert data["decision"] in ("HOLD", "BLOCK")
    assert "features" in data
    assert "reasonCodes" in data


def test_input_validation_and_error_handling(client):
    # Invalid corridor on /api/quote
    resp = client.get("/api/quote?corridor=XX-YY&amountMinor=1000")
    assert resp.status_code == 400
    assert "Unsupported corridor" in str(resp.json()["detail"])

    # Negative amountMinor (violates gt=0)
    resp = client.get("/api/quote?corridor=US-IN&amountMinor=-500")
    assert resp.status_code == 422

    # Non-existent remittance lookup returns 404
    resp = client.get("/api/remittances/NONEXISTENT123")
    assert resp.status_code == 404
    assert "not found" in str(resp.json()["detail"]).lower()


def test_remittance_pagination(client):
    for i in range(3):
        client.post("/api/remittances", json=create_body(senderName=f"User {i}")).json()

    # Page 1 (limit 2)
    p1 = client.get("/api/remittances?offset=0&limit=2").json()
    assert len(p1) == 2

    # Page 2 (offset 2, limit 2)
    p2 = client.get("/api/remittances?offset=2&limit=2").json()
    assert len(p2) >= 1


def test_public_track_endpoint(client):
    r = client.post("/api/remittances", json=create_body()).json()
    rid = r["id"]
    client.post(f"/api/remittances/{rid}/run")

    track_resp = client.get(f"/api/track/{rid}")
    assert track_resp.status_code == 200
    track_data = track_resp.json()
    assert track_data["id"] == rid
    assert track_data["status"] == "SETTLED"
    assert "steps" in track_data


def test_upi_vpa_format_validation(client):
    # Format without '@' must fail with 422
    resp = client.post("/api/remittances", json=create_body(beneficiaryVpa="invalid_vpa_no_at"))
    assert resp.status_code == 422


def test_binding_quotes_flow(client):
    # Request a binding quote
    q_resp = client.post("/api/quotes", json={"corridor": "US-IN", "amountMinor": 100000})
    assert q_resp.status_code == 200
    q_data = q_resp.json()
    assert "quoteId" in q_data
    assert q_data["receivePaise"] > 0
    qid = q_data["quoteId"]

    # Create remittance with binding quote
    r_resp = client.post("/api/remittances", json=create_body(quoteId=qid))
    assert r_resp.status_code == 200
    r_data = r_resp.json()

    # Run the remittance and verify settled
    settled = client.post(f"/api/remittances/{r_data['id']}/run").json()
    assert settled["status"] == "SETTLED"
    assert settled["quote"]["receivePaise"] == q_data["receivePaise"]


def test_idempotency_key(client):
    headers = {"Idempotency-Key": "test-key-uuid-1234"}
    b = create_body()
    r1 = client.post("/api/remittances", json=b, headers=headers).json()
    r2 = client.post("/api/remittances", json=b, headers=headers).json()
    assert r1["id"] == r2["id"]


def test_state_conflict_error_409(client):
    r = client.post("/api/remittances", json=create_body()).json()
    rid = r["id"]
    # Settle it
    client.post(f"/api/remittances/{rid}/run")
    # Stepping a settled remittance must raise 409 conflict
    step_resp = client.post(f"/api/remittances/{rid}/step")
    assert step_resp.status_code == 409
    assert step_resp.json()["detail"]["code"] == "ERR_STATE_CONFLICT"


def test_websocket_live_event_delivery(client):
    import app.main as m
    with client.websocket_connect("/ws/events") as ws:
        # Drain any backlog events sent on connection
        backlog_count = len(m.broadcaster.recent_events[-20:])
        for _ in range(backlog_count):
            ws.receive_json()

        # Create and run transfer
        r = client.post("/api/remittances", json=create_body()).json()
        rid = r["id"]
        client.post(f"/api/remittances/{rid}/run")

        received_events = []
        for _ in range(7):
            data = ws.receive_json()
            if data.get("remittanceId") == rid:
                received_events.append(data)

        # Proves events were actively delivered via WebSocket during /run
        assert len(received_events) > 0
        assert any(e.get("step") in ("CREATE", "LOCK_QUOTE", "SCREEN", "VERIFY_BENEFICIARY", "SETTLE_PAYOUT") for e in received_events)


def test_latency_telemetry_endpoint(client):
    r = client.post("/api/remittances", json=create_body()).json()
    rid = r["id"]
    client.post(f"/api/remittances/{rid}/run")

    resp = client.get("/api/latency")
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert data["summary"]["count"] >= 1
    assert data["summary"]["p50Ms"] >= 0
    assert "speedupVsSwift" in data
    assert data["speedupVsSwift"] > 0
    assert "recentSettlements" in data
    assert any(rec["id"] == rid for rec in data["recentSettlements"])


def test_cost_comparison_endpoint(client):
    resp = client.get("/api/compare?corridor=US-IN&amountMinor=100000")
    assert resp.status_code == 200
    data = resp.json()
    assert data["corridor"] == "US-IN"
    assert "providers" in data
    assert len(data["providers"]) >= 5
    # RemitChain should be the lowest cost
    assert data["providers"][0]["provider"] == "RemitChain"
    assert data["savingsVsBankWire"]["annualRupees"] > 0


def test_upi_pre_send_lookup(client):
    # Valid VPA
    r1 = client.post("/api/upi/lookup", json={"vpa": "meera@okbank", "declaredName": "Meera Rao"})
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["verified"] is True
    assert d1["bank"] == "OKBANK"
    assert d1["matchScore"] >= 70

    # Invalid VPA format
    r2 = client.post("/api/upi/lookup", json={"vpa": "invalidvpa", "declaredName": "Meera Rao"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "INVALID_FORMAT"
    assert r2.json()["verified"] is False


def test_maker_checker_enforcement(client):
    # Transfer created by Asha Rao
    b = create_body(senderName="Asha Rao", scenario="high_risk")
    r = client.post("/api/remittances", json=b).json()
    rid = r["id"]

    # Run to trigger compliance hold
    held = client.post(f"/api/remittances/{rid}/run").json()
    assert held["status"] == "HELD"

    # Maker (Asha Rao) tries to approve own transfer -> 403 Forbidden
    rej_maker = client.post(f"/api/remittances/{rid}/review", json={"approve": True, "reviewerId": "Asha Rao"})
    assert rej_maker.status_code == 403
    assert rej_maker.json()["detail"]["code"] == "ERR_MAKER_CHECKER"

    # Separate Checker (Officer Vikram) approves -> 200 OK
    appr = client.post(f"/api/remittances/{rid}/review", json={"approve": True, "reviewerId": "Officer Vikram"})
    assert appr.status_code == 200
    assert appr.json()["status"] in ("CREATED", "QUOTED", "SCREENED", "VERIFIED", "FUNDED", "PAYOUT_SUBMITTED", "SETTLED")


def test_compliance_pending_endpoint(client):
    b = create_body(scenario="high_risk")
    r = client.post("/api/remittances", json=b).json()
    rid = r["id"]
    client.post(f"/api/remittances/{rid}/run")

    pending = client.get("/api/compliance/pending").json()
    assert len(pending) >= 1
    found = next((item for item in pending if item["id"] == rid), None)
    assert found is not None
    assert found["status"] == "HELD"
    assert "elapsedSeconds" in found
    assert "riskBreakdown" in found


def test_auth_jwt_token_and_rbac(client):
    # Obtain JWT token for auditor
    tok_resp = client.post("/api/auth/token", json={"userId": "auditor_smith", "role": "auditor"})
    assert tok_resp.status_code == 200
    token = tok_resp.json()["accessToken"]

    # Call /api/auth/me with Bearer token
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["userId"] == "auditor_smith"
    assert me_data["role"] == "auditor"
    assert me_data["authenticated"] is True

    # Auditor accessing audit trail with Bearer token -> 200 OK
    aud_resp = client.get("/api/audit", headers={"Authorization": f"Bearer {token}"})
    assert aud_resp.status_code == 200

    # Sender role attempting to access audit trail -> 403 Forbidden
    sender_tok = client.post("/api/auth/token", json={"userId": "sender_joe", "role": "sender"}).json()["accessToken"]
    forbidden_resp = client.get("/api/audit", headers={"Authorization": f"Bearer {sender_tok}"})
    assert forbidden_resp.status_code == 403
    assert forbidden_resp.json()["detail"]["code"] == "ERR_FORBIDDEN"


def test_pii_vault_and_gdpr_shredding(client):
    # Create remittance with PII
    b = create_body(senderName="Deepika Padukone", beneficiaryName="Ranveer Singh", beneficiaryVpa="ranveer@okbank")
    r = client.post("/api/remittances", json=b).json()
    rid = r["id"]

    # Verify PII status in vault
    status_resp = client.get(f"/api/pii/{rid}/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "ACTIVE"

    # Retrieve off-ledger PII
    pii_resp = client.get(f"/api/pii/{rid}")
    assert pii_resp.status_code == 200
    pii = pii_resp.json()["pii"]
    assert pii["senderName"] == "Deepika Padukone"
    assert pii["beneficiaryVpa"] == "ranveer@okbank"

    # GDPR Right-to-be-Forgotten: shred off-ledger PII
    del_resp = client.delete(f"/api/pii/{rid}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "SHREDDED"

    # Post-shredding: PII retrieval must return 410 Gone
    gone_resp = client.get(f"/api/pii/{rid}")
    assert gone_resp.status_code == 410
    assert gone_resp.json()["detail"]["code"] == "ERR_PII_SHREDDED"

    # Verify ledger still retains immutable record and trail
    ledger_rec = client.get(f"/api/remittances/{rid}").json()
    assert ledger_rec["id"] == rid
    assert "senderHash" in ledger_rec  # Salted hash remains for verification


def test_prometheus_metrics_endpoint(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    text = resp.text
    assert "remitchain_transfers_total" in text
    assert "remitchain_active_websockets" in text
    assert "remitchain_settlement_duration_seconds" in text


def test_async_202_execution_and_job_polling(client):
    import time
    r = client.post("/api/remittances", json=create_body()).json()
    rid = r["id"]

    # Submit async execution -> 202 Accepted
    async_resp = client.post(f"/api/remittances/{rid}/async-run")
    assert async_resp.status_code == 202
    data = async_resp.json()
    assert data["status"] == "QUEUED"
    job_id = data["jobId"]

    # Poll job status until COMPLETED (with timeout)
    for _ in range(30):
        job_info = client.get(f"/api/jobs/{job_id}").json()
        if job_info["status"] == "COMPLETED":
            break
        time.sleep(0.05)

    assert job_info["status"] == "COMPLETED"

    # Confirm remittance settled on ledger
    settled = client.get(f"/api/remittances/{rid}").json()
    assert settled["status"] == "SETTLED"


def test_cryptographic_trail_verification(client):
    r = client.post("/api/remittances", json=create_body()).json()
    rid = r["id"]
    client.post(f"/api/remittances/{rid}/run")

    verify_resp = client.get(f"/api/remittances/{rid}/verify")
    assert verify_resp.status_code == 200
    v = verify_resp.json()
    assert v["remittanceId"] == rid
    assert v["verified"] is True
    assert v["tamperDetected"] is False
    assert v["stepsCount"] >= 7
    assert len(v["finalChainHash"]) == 64  # SHA-256 hex digest





