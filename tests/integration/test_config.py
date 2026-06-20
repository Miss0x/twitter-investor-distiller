"""集成测试 — 用户配置 CRUD(LLM/Twitter/Telegram/Observations)。

每个测试用独立 user(make_user factory),observations 用唯一 username 避免冲突。
"""
from __future__ import annotations


class TestConfigGet:
    def test_get_config_returns_dict(self, make_user):
        """GET /api/config 应返回包含主要配置节的字典。"""
        auth_client = make_user("cfg_get")
        r = auth_client.get("/api/config")
        assert r.status_code == 200
        body = r.json()
        # 应包含关键配置节
        for section in ["llm", "twitter", "telegram", "observations"]:
            assert section in body, f"缺少配置节: {section}"


class TestConfigLLM:
    def test_save_llm_config(self, make_user):
        """保存 LLM 配置后应返回 ok=True。"""
        auth_client = make_user("cfg_llm_save")
        r = auth_client.post("/api/config/llm", json={
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test",
            "model": "gpt-4o-mini",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert "config" in body

    def test_save_llm_then_get_matches(self, make_user):
        """保存 LLM 配置后,GET /api/config 应返回相同值。"""
        auth_client = make_user("cfg_llm_roundtrip")
        auth_client.post("/api/config/llm", json={
            "base_url": "https://test.api.com/v1",
            "api_key": "sk-verify",
            "model": "gpt-4o",
        })
        r = auth_client.get("/api/config")
        cfg = r.json().get("llm", {})
        assert cfg.get("base_url") == "https://test.api.com/v1", f"不匹配: {cfg}"


class TestConfigTwitter:
    def test_save_twitter_config(self, make_user):
        """保存 Twitter 配置应返回 ok=True。"""
        auth_client = make_user("cfg_tw")
        r = auth_client.post("/api/config/twitter", json={
            "provider": "official",
            "api_key": "tw-key",
            "api_secret": "tw-secret",
            "access_token": "tw-token",
            "access_secret": "tw-asecret",
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True


class TestConfigTelegram:
    def test_save_telegram_config(self, make_user):
        """保存 Telegram 配置应返回 ok=True。"""
        auth_client = make_user("cfg_tg")
        r = auth_client.post("/api/config/telegram", json={
            "bot_token": "tg-test-token",
            "chat_id": "123456",
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True


class TestObservations:
    def test_add_observation(self, make_user):
        """添加观察对象应更新 observation 列表。"""
        auth_client = make_user("obs_add")
        r = auth_client.post("/api/config/observations/add", json={
            "username": "obs_user_add",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert "obs_user_add" in body.get("observations", [])

    def test_add_then_get_contains(self, make_user):
        """添加后 GET /api/config 应包含该观察对象。"""
        auth_client = make_user("obs_round")
        auth_client.post("/api/config/observations/add", json={"username": "obs_user_round"})
        r = auth_client.get("/api/config")
        obs = r.json().get("observations", [])
        assert "obs_user_round" in obs

    def test_remove_observation(self, make_user):
        """移除观察对象应从列表中删除。"""
        auth_client = make_user("obs_rm")
        auth_client.post("/api/config/observations/add", json={"username": "obs_user_rm"})
        r = auth_client.post("/api/config/observations/remove", json={"username": "obs_user_rm"})
        assert r.status_code == 200
        assert "obs_user_rm" not in r.json().get("observations", [])