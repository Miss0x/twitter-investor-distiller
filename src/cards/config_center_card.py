"""User configuration center card — manage LLM, Twitter, Telegram, and observations."""

from __future__ import annotations

from src.cards.base import Card
from src.cards import register


@register
class ConfigCenterCard(Card):
    """集中管理所有用户配置的卡片：LLM、Twitter API、Telegram、观察对象。"""

    name = "config_center"
    display_title = "用户配置中心"
    template = "config_center.html"

    def get_data(self) -> dict:
        try:
            # 优先使用多用户加密配置，回退到旧全局配置
            from src.admin.auth import get_current_user
            req = _current_request.get()
            tenant_id = "default"
            if req is not None:
                user = get_current_user(req)
                if user:
                    tenant_id = str(user.id)
            from src.multi_tenant.config import PerUserConfig
            masked = PerUserConfig(tenant_id).load_masked()
        except Exception:
            try:
                from src.config_center import ConfigManager
                masked = ConfigManager().load_masked()
            except Exception:
                return {"empty": True}

        return {
            "empty": False,
            "llm": masked.get("llm", {}),
            "twitter": masked.get("twitter", {}),
            "telegram": masked.get("telegram", {}),
            "observations": masked.get("observations", []),
        }


# Thread-safe request context for card rendering
# E402: 此处 import 必须在 @register 装饰器执行后导入，
# 避免循环依赖（cards → contextvars → ... → cards）
import contextvars  # noqa: E402
_current_request: contextvars.ContextVar = contextvars.ContextVar("current_request", default=None)
