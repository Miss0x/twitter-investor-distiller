"""用户配置中心 API：/api/config/{*, llm, twitter, telegram, observations/add, observations/remove}。

从 web_api.py 抽出，路径与原 @app 完全一致。
"""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
async def get_full_config(request: Request):
    """返回当前用户配置（敏感字段已脱敏，磁盘加密存储）。"""
    from src.admin.auth import get_current_user  # noqa: PLC0415
    from src.multi_tenant.config import PerUserConfig  # noqa: PLC0415
    user = get_current_user(request)
    tenant_id = str(user.id) if user else "default"
    try:
        return PerUserConfig(tenant_id).load_masked()
    except Exception:
        from src.config_center import ConfigManager  # noqa: PLC0415
        return ConfigManager().load_masked()


@router.post("/llm")
async def save_llm_config(request: Request, payload: dict):
    """保存 LLM 配置（加密存储到磁盘）。"""
    from src.admin.auth import get_current_user  # noqa: PLC0415
    from src.multi_tenant.config import PerUserConfig  # noqa: PLC0415
    user = get_current_user(request)
    tenant_id = str(user.id) if user else "default"
    try:
        cfg = PerUserConfig(tenant_id)
        cfg.save_section("llm", {
            "base_url": str(payload.get("base_url") or ""),
            "api_key": str(payload.get("api_key") or ""),
            "model": str(payload.get("model") or ""),
        })
        cfg.apply_llm_config()
        return {"ok": True, "config": cfg.load_masked()["llm"]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/twitter")
async def save_twitter_config(request: Request, payload: dict):
    """保存 Twitter API 配置（加密存储）。"""
    from src.admin.auth import get_current_user  # noqa: PLC0415
    from src.multi_tenant.config import PerUserConfig  # noqa: PLC0415
    user = get_current_user(request)
    tenant_id = str(user.id) if user else "default"
    try:
        cfg = PerUserConfig(tenant_id)
        cfg.save_section("twitter", {
            "provider": str(payload.get("provider") or "official"),
            "api_key": str(payload.get("api_key") or ""),
            "api_secret": str(payload.get("api_secret") or ""),
            "access_token": str(payload.get("access_token") or ""),
            "access_secret": str(payload.get("access_secret") or ""),
            "base_url": str(payload.get("base_url") or ""),
        })
        return {"ok": True, "config": cfg.load_masked()["twitter"]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/telegram")
async def save_telegram_config(request: Request, payload: dict):
    """保存 Telegram Bot 配置（加密存储）。"""
    from src.admin.auth import get_current_user  # noqa: PLC0415
    from src.multi_tenant.config import PerUserConfig  # noqa: PLC0415
    user = get_current_user(request)
    tenant_id = str(user.id) if user else "default"
    try:
        cfg = PerUserConfig(tenant_id)
        cfg.save_section("telegram", {
            "bot_token": str(payload.get("bot_token") or ""),
            "chat_id": str(payload.get("chat_id") or ""),
        })
        return {"ok": True, "config": cfg.load_masked()["telegram"]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/observations/add")
async def add_observation(request: Request, payload: dict):
    """添加观察对象（到当前用户配置）。"""
    username = str(payload.get("username") or "").strip().lstrip("@")
    if not username:
        return {"ok": False, "error": "请输入用户名"}
    from src.admin.auth import get_current_user  # noqa: PLC0415
    from src.multi_tenant.config import PerUserConfig  # noqa: PLC0415
    user = get_current_user(request)
    tenant_id = str(user.id) if user else "default"
    try:
        cfg = PerUserConfig(tenant_id)
        config = cfg.add_observation(username)
        return {"ok": True, "observations": config["observations"]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/observations/remove")
async def remove_observation(request: Request, payload: dict):
    """移除观察对象（从当前用户配置）。"""
    username = str(payload.get("username") or "").strip()
    if not username:
        return {"ok": False, "error": "请指定用户名"}
    from src.admin.auth import get_current_user  # noqa: PLC0415
    from src.multi_tenant.config import PerUserConfig  # noqa: PLC0415
    user = get_current_user(request)
    tenant_id = str(user.id) if user else "default"
    try:
        cfg = PerUserConfig(tenant_id)
        config = cfg.remove_observation(username)
        return {"ok": True, "observations": config["observations"]}
    except Exception as e:
        return {"ok": False, "error": str(e)}
