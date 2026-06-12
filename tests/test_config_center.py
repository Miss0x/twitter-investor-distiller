"""Tests for the user configuration center module."""
import json
import tempfile
from pathlib import Path

from src.config_center import ConfigManager


def _fresh(tmp_path):
    return ConfigManager(config_path=tmp_path / "user_config.json")


def test_config_creates_default_file_on_first_load():
    with tempfile.TemporaryDirectory() as td:
        mgr = _fresh(Path(td))
        config = mgr.load()
        assert config["llm"]["base_url"] == ""
        assert config["llm"]["api_key"] == ""
        assert config["llm"]["model"] == ""
        assert config["twitter"]["api_key"] == ""
        assert config["telegram"]["bot_token"] == ""
        assert config["observations"] == []
        assert Path(td, "user_config.json").exists()


def test_config_save_and_reload_preserves_all_sections():
    with tempfile.TemporaryDirectory() as td:
        mgr = _fresh(Path(td))
        mgr.save_section("llm", {"base_url": "https://api.deepseek.com/v1", "api_key": "sk-test", "model": "deepseek-chat"})
        mgr.save_section("twitter", {"api_key": "tw-test", "api_secret": "tw-secret"})
        mgr.save_section("telegram", {"bot_token": "123:abc", "chat_id": "456"})
        mgr.add_observation("TJ_Research")
        mgr.add_observation("dearbaibabybus")

        reloaded = _fresh(Path(td)).load()
        assert reloaded["llm"]["base_url"] == "https://api.deepseek.com/v1"
        assert reloaded["llm"]["api_key"] == "sk-test"
        assert reloaded["twitter"]["api_key"] == "tw-test"
        assert reloaded["telegram"]["bot_token"] == "123:abc"
        assert "TJ_Research" in reloaded["observations"]
        assert "dearbaibabybus" in reloaded["observations"]


def test_observation_dedup_and_remove():
    with tempfile.TemporaryDirectory() as td:
        mgr = _fresh(Path(td))
        mgr.add_observation("user1")
        mgr.add_observation("user1")  # duplicate
        assert mgr.load()["observations"] == ["user1"]

        mgr.remove_observation("user1")
        assert mgr.load()["observations"] == []


def test_mask_sensitive_fields():
    with tempfile.TemporaryDirectory() as td:
        mgr = _fresh(Path(td))
        mgr.save_section("llm", {"api_key": "sk-secret-key-12345"})

        masked = mgr.load_masked()
        assert masked["llm"]["api_key"] == "sk-****2345"


def test_llm_settings_applied_to_environment():
    """Model reads from config, falls back to env vars."""
    import os
    with tempfile.TemporaryDirectory() as td:
        mgr = _fresh(Path(td))
        mgr.save_section("llm", {"base_url": "https://custom.api/v1", "api_key": "sk-xyz", "model": "custom-model"})

        applied = mgr.apply_llm_config()
        assert applied["base_url"] == "https://custom.api/v1"
        assert applied["model"] == "custom-model"
        # api_key should be set from config
        assert os.environ.get("LLM_API_KEY") == "sk-xyz"
        # restore
        os.environ.pop("LLM_API_KEY", None)
