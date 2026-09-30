"""Locust load testing for RemitChain Hub.

Run: pip install locust && locust -f hub/tests/locustfile.py --host http://localhost:8000

Simulates concurrent users creating remittances and running them to completion,
exercising all corridors and scenarios.
"""
import random
from locust import HttpUser, task, between


CORRIDORS = ["AE-IN", "US-IN", "SG-IN", "GB-IN", "CA-IN", "AU-IN", "EU-IN", "JP-IN", "MY-IN"]
PURPOSES = ["FAMILY_MAINTENANCE", "EDUCATION", "MEDICAL", "GIFT", "INVESTMENT", "TRAVEL"]
SCENARIOS = ["happy", "high_risk", "payout_fail", "bad_beneficiary"]
NAMES = ["Asha Rao", "Raj Patel", "Priya Kumar", "Arun Singh", "Meera Nair", "Vikram Shah",
         "Anita Reddy", "Suresh Gupta", "Kavita Das", "Rohit Joshi"]
VPAS = [f"user{i}@okbank" for i in range(20)]


class RemitUser(HttpUser):
    """Simulates a bank operator creating and processing remittances."""
    wait_time = between(0.5, 2)

    @task(5)
    def send_and_run(self):
        """Create a remittance and run it to completion."""
        body = {
            "corridor": random.choice(CORRIDORS),
            "senderName": random.choice(NAMES),
            "beneficiaryName": random.choice(NAMES),
            "beneficiaryVpa": random.choice(VPAS),
            "purpose": random.choice(PURPOSES),
            "amountMinor": random.randint(10000, 500000),
            "scenario": "happy",
        }
        r = self.client.post("/api/remittances", json=body)
        if r.status_code == 200:
            rid = r.json()["id"]
            self.client.post(f"/api/remittances/{rid}/run")

    @task(2)
    def get_quote(self):
        """Fetch a live quote."""
        corridor = random.choice(CORRIDORS)
        amount = random.randint(10000, 500000)
        self.client.get(f"/api/quote?corridor={corridor}&amountMinor={amount}")

    @task(2)
    def list_remittances(self):
        """List all remittances."""
        self.client.get("/api/remittances")

    @task(1)
    def get_stats(self):
        """Fetch network stats."""
        self.client.get("/api/stats")

    @task(1)
    def get_health(self):
        """Health check."""
        self.client.get("/api/health")

    @task(1)
    def cost_compare(self):
        """Compare costs across providers."""
        corridor = random.choice(CORRIDORS)
        amount = random.randint(10000, 500000)
        self.client.get(f"/api/compare?corridor={corridor}&amountMinor={amount}")

    @task(1)
    def compliance_summary(self):
        """Fetch compliance summary."""
        self.client.get("/api/audit/summary")
