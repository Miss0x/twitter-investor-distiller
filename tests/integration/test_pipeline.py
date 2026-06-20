"""集成测试 — Pipeline 任务管理 API。

health 端点用匿名 client(无需登录),其他端点用 make_user factory。
"""
from __future__ import annotations


class TestPipelineTasks:
    def test_list_tasks_returns_list(self, make_user):
        """GET /pipeline/tasks 应返回 {tasks: [...], running, progress}。"""
        auth_client = make_user("pipe_list")
        r = auth_client.get("/pipeline/tasks")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        assert isinstance(data.get("tasks"), list)
        assert "running" in data
        assert "progress" in data

    def test_seed_tasks_returns_count(self, make_user):
        """POST /pipeline/tasks/seed 应返回计数(即使为 0 也是合法响应)。"""
        auth_client = make_user("pipe_seed")
        r = auth_client.post("/pipeline/tasks/seed")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, dict)

    def test_run_clean_returns_summary(self, make_user):
        """POST /pipeline/clean 应返回清洗结果。"""
        auth_client = make_user("pipe_clean")
        r = auth_client.post("/pipeline/clean")
        assert r.status_code == 200
        body = r.json()
        assert "ok" in body or "cleaned" in body

    def test_list_fetched_tickers(self, make_user):
        """GET /pipeline/tasks/fetched 应返回 {tickers: [...], count: int}。"""
        auth_client = make_user("pipe_fetched")
        r = auth_client.get("/pipeline/tasks/fetched")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        assert isinstance(data.get("tickers"), list)
        assert isinstance(data.get("count"), int)
        assert data["count"] == len(data["tickers"])

    def test_list_crypto_fetched(self, make_user):
        """GET /pipeline/tasks/crypto_fetched 应返回 {tickers: [...], count: int}。"""
        auth_client = make_user("pipe_crypto")
        r = auth_client.get("/pipeline/tasks/crypto_fetched")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        assert isinstance(data.get("tickers"), list)
        assert isinstance(data.get("count"), int)
        assert data["count"] == len(data["tickers"])


class TestHealthEndpoints:
    def test_health_endpoints(self, client):
        """无认证的匿名请求也能访问健康检查端点。"""
        r = client.get("/healthz")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

        r = client.get("/ready")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
