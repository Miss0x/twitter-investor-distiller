"""集成测试 — Dashboard 卡片 API。

验证卡片元数据和关键卡片能正常返回 HTML/JSON。
"""
from __future__ import annotations


class TestCardsMeta:
    def test_meta_returns_card_list(self, make_user):
        """GET /cards/meta 应返回所有注册的卡片元数据。"""
        auth_client = make_user("cards_meta")
        r = auth_client.get("/cards/meta")
        assert r.status_code == 200
        cards = r.json()
        assert isinstance(cards, list)
        assert len(cards) >= 28  # 应包含全部注册卡片
        names = {c["name"] for c in cards}
        for key in ["system_status", "consensus", "daemon", "chat"]:
            assert key in names, f"缺少卡片: {key}"

    def test_meta_card_has_required_fields(self, make_user):
        """每张卡片应包含 name/tab/tab_label/refresh/display_title。"""
        auth_client = make_user("cards_fields")
        cards = auth_client.get("/cards/meta").json()
        for c in cards:
            for field in ["name", "tab", "tab_label", "refresh", "display_title"]:
                assert field in c, f"卡片 {c.get('name')} 缺少字段 {field}"


class TestCardRender:
    def test_system_status_returns_html(self, make_user):
        """GET /cards/system_status 应返回 HTML 字符串。"""
        auth_client = make_user("cards_sys")
        r = auth_client.get("/cards/system_status")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body.get("html"), str)
        assert len(body["html"]) > 0

    def test_daemon_returns_data(self, make_user):
        """GET /cards/daemon 应返回 daemon 状态数据。"""
        auth_client = make_user("cards_daemon")
        r = auth_client.get("/cards/daemon")
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        assert "running" in body["data"]

    def test_api_status_returns_data(self, make_user):
        """GET /cards/api_status 应返回采集状态。"""
        auth_client = make_user("cards_api")
        r = auth_client.get("/cards/api_status")
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        assert "total_fetched" in body.get("data", {})

    def test_unknown_card_returns_404(self, make_user):
        """不存在的卡片应返回 404。"""
        auth_client = make_user("cards_404")
        r = auth_client.get("/cards/nonexistent_card_xyz")
        assert r.status_code == 404