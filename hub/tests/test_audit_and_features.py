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
    return TestClient(m.app)


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
    assert "Unsupported corridor" in resp.json()["detail"]

    # Negative amountMinor (violates gt=0)
    resp = client.get("/api/quote?corridor=US-IN&amountMinor=-500")
    assert resp.status_code == 422

    # Non-existent remittance lookup
    resp = client.get("/api/remittances/NONEXISTENT123")
    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"]


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
