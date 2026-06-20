"""自选股 API：/api/watchlist/*。

从 web_api.py 抽出，路径与原 @app.get/@app.post 完全一致。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.dependencies import get_tenant_config
from src.api.schemas import WatchlistModifyResponse, WatchlistResponse

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("", response_model=WatchlistResponse)
async def get_watchlist(cfg = Depends(get_tenant_config)):
    """GET /api/watchlist — 返回根级 list[str],与前端解析逻辑保持兼容。"""
    return cfg.load().get("watchlist", [])


@router.post("/add", response_model=WatchlistModifyResponse)
async def add_watchlist(payload: dict, cfg = Depends(get_tenant_config)):
    ticker = str(payload.get("ticker") or "").strip().upper()
    if not ticker:
        return {"ok": False, "error": "请输入股票代码"}
    config = cfg.load()
    wl = config.setdefault("watchlist", [])
    if ticker not in wl:
        wl.append(ticker)
    config["watchlist"] = wl
    cfg._save_encrypted(config)
    from src.multi_tenant.config import _cache_set  # noqa: PLC0415
    _cache_set(f"config:{cfg.tenant_id}", config)
    return {"ok": True, "watchlist": wl}


@router.post("/remove", response_model=WatchlistModifyResponse)
async def remove_watchlist(payload: dict, cfg = Depends(get_tenant_config)):
    ticker = str(payload.get("ticker") or "").strip().upper()
    config = cfg.load()
    wl = config.get("watchlist", [])
    if ticker in wl:
        wl.remove(ticker)
    config["watchlist"] = wl
    cfg._save_encrypted(config)
    from src.multi_tenant.config import _cache_set  # noqa: PLC0415
    _cache_set(f"config:{cfg.tenant_id}", config)
    return {"ok": True, "watchlist": wl}