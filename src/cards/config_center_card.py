"""User configuration center card — manage LLM, Twitter, Telegram, and observations."""

from __future__ import annotations

from src.cards.base import Card
from src.cards import register
from src.config_center import ConfigManager


@register
class ConfigCenterCard(Card):
    """集中管理所有用户配置的卡片：LLM、Twitter API、Telegram、观察对象。"""

    name = "config_center"
    display_title = "用户配置中心"
    template = "config_center.html"

    def get_data(self) -> dict:
        try:
            mgr = ConfigManager()
            masked = mgr.load_masked()
            return {
                "empty": False,
                "llm": masked.get("llm", {}),
                "twitter": masked.get("twitter", {}),
                "telegram": masked.get("telegram", {}),
                "observations": masked.get("observations", []),
            }
        except Exception:
            return {"empty": True}
