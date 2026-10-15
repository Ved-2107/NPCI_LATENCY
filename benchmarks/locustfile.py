"""Locust Load Testing Suite for RemitChain Hub.

Simulates concurrent remitter traffic:
1. Requests binding quotes
2. Pre-validates beneficiary VPA
3. Initiates remittance transactions
4. Executes state machine transitions to settlement
5. Fetches telemetry and Prometheus metrics
"""
import random
import uuid
from locust import HttpUser, task, between

CORRIDORS = ["US-IN", "AE-IN", "GB-IN", "SG-IN", "EU-IN"]
PURPOSES = ["FAMILY_MAINTENANCE", "EDUCATION", "MEDICAL", "GIFT"]


class RemittanceUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task(4)
    def fetch_binding_quote(self):
        corridor = random.choice(CORRIDORS)
        amt = random.randint(100, 5000) * 100
        self.client.post("/api/quotes", json={"corridor": corridor, "amountMinor": amt})

    @task(3)
    def pre_verify_vpa(self):
        self.client.post("/api/upi/lookup", json={
            "vpa": f"user_{random.randint(1, 9999)}@okbank",
            "declaredName": "Asha Rao",
            "scenario": "happy"
        })

    @task(5)
    def full_remittance_lifecycle(self):
        corridor = random.choice(CORRIDORS)
        amt = random.randint(100, 3000) * 100
        idem_key = str(uuid.uuid4())

        # 1. Create remittance
        r = self.client.post(
            "/api/remittances",
            json={
                "corridor": corridor,
                "senderName": "Asha Rao",
                "beneficiaryName": "Meera Rao",
                "beneficiaryVpa": "meera@okbank",
                "purpose": random.choice(PURPOSES),
                "amountMinor": amt,
                "scenario": "happy"
            },
            headers={"Idempotency-Key": idem_key}
        )
        if r.status_code != 200:
            return

        rid = r.json().get("id")
        if not rid:
            return

        # 2. Run remittance to settlement
        self.client.post(f"/api/remittances/{rid}/run")

        # 3. Cryptographically verify trail
        self.client.get(f"/api/remittances/{rid}/verify")

    @task(2)
    def telemetry_and_metrics(self):
        self.client.get("/api/latency")
        self.client.get("/metrics")
        self.client.get("/api/compare?corridor=US-IN&amountMinor=100000")
