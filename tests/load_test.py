"""
Load test for Twitter Investor Distiller.
Usage: locust -f tests/load_test.py --host=http://127.0.0.1:8000 --users=50 --spawn-rate=10 --run-time=60s --headless
"""
from locust import HttpUser, task, between


class DistillerUser(HttpUser):
    wait_time = between(0.5, 2)

    def on_start(self):
        # Register + login to get cookies
        self.client.post("/auth/register", json={
            "email": "load@test.com", "username": "loadtest", "password": "test123"
        })
        self.client.post("/auth/login", json={
            "email": "load@test.com", "password": "test123"
        })

    @task(5)
    def dashboard(self):
        self.client.get("/dashboard")

    @task(3)
    def cards_meta(self):
        self.client.get("/cards/meta")

    @task(2)
    def config_get(self):
        self.client.get("/api/config")

    @task(1)
    def valuation_dcf(self):
        self.client.get("/api/valuation/dcf?ticker=NVDA")

    @task(1)
    def watchlist(self):
        self.client.get("/api/watchlist")

    @task(1)
    def card_quality_gate(self):
        self.client.get("/cards/quality_gate")

    @task(1)
    def card_consensus(self):
        self.client.get("/cards/consensus")
