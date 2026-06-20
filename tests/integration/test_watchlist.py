"""集成测试 — 股票自选 + 价格预警 API。

每个测试用独立 user(make_user factory),每个测试的 ticker 都用唯一值,杜绝互相污染。
"""
from __future__ import annotations


class TestWatchlist:
    def test_get_watchlist_returns_list(self, make_user):
        """GET /api/watchlist 应返回列表(初始为空,因为是新 user)。"""
        auth_client = make_user("wl_empty")
        r = auth_client.get("/api/watchlist")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert r.json() == []

    def test_add_ticker(self, make_user):
        """添加代码后应出现在列表中。"""
        auth_client = make_user("wl_add")
        r = auth_client.post("/api/watchlist/add", json={"ticker": "WLA1"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert "WLA1" in body.get("watchlist", [])

    def test_add_duplicate(self, make_user):
        """重复添加不应增加列表。"""
        auth_client = make_user("wl_dup")
        # 第一次添加
        auth_client.post("/api/watchlist/add", json={"ticker": "WLD1"})
        # 第二次添加相同 ticker
        r = auth_client.post("/api/watchlist/add", json={"ticker": "WLD1"})
        wl = r.json().get("watchlist", [])
        assert wl.count("WLD1") == 1

    def test_remove_ticker(self, make_user):
        """移除代码后应不在列表中。"""
        auth_client = make_user("wl_rm")
        # 先添加
        auth_client.post("/api/watchlist/add", json={"ticker": "WLR1"})
        # 再移除
        r = auth_client.post("/api/watchlist/remove", json={"ticker": "WLR1"})
        assert r.status_code == 200
        assert "WLR1" not in r.json().get("watchlist", [])


class TestPriceAlerts:
    def test_add_alert(self, make_user):
        """添加价格预警应返回 alerts 列表。"""
        auth_client = make_user("alert_ok")
        r = auth_client.post("/api/alerts/add", json={
            "ticker": "ALA1",
            "direction": "above",
            "price": 100.0,
        })
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert len(body.get("alerts", [])) == 1

    def test_add_alert_invalid_data(self, make_user):
        """价格 <=0 时应被拒绝。"""
        auth_client = make_user("alert_bad")
        r = auth_client.post("/api/alerts/add", json={
            "ticker": "ALB1",
            "direction": "below",
            "price": 0,
        })
        assert r.status_code == 200
        assert r.json()["ok"] is False

    def test_remove_alert(self, make_user):
        """移除预警应返回剩余列表(格式正确)。"""
        auth_client = make_user("alert_rm")
        r = auth_client.post("/api/alerts/remove", json={"alert_id": 999})
        assert r.status_code == 200
        assert "alerts" in r.json()
        assert isinstance(r.json()["alerts"], list)