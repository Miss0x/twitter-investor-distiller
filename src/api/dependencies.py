"""FastAPI 公共依赖函数。

集中管理 web_api.py 中分散的认证 + 配置注入逻辑，
遵循 FastAPI 官方 "Bigger Applications" 推荐的 ``app/dependencies.py`` 模式。

使用:
    from src.api.dependencies import get_tenant_config, require_superuser
    from src.multi_tenant.config import PerUserConfig

    @app.post("/api/config/llm")
    async def save_llm(cfg: PerUserConfig = Depends(get_tenant_config), ...):
        ...
"""
from __future__ import annotations

from fastapi import HTTPException, Request


def get_tenant_config(request: Request):
    """FastAPI dependency: 从 JWT cookie 注入当前用户的 PerUserConfig。

    如果用户未登录，使用 ``"default"`` tenant（允许匿名使用部分功能）。
    认证失败时不会抛 401 —— 无 token 视为匿名用户。
    """
    from src.admin.auth import get_current_user
    from src.multi_tenant.config import PerUserConfig

    user = get_current_user(request)
    tenant_id = str(user.id) if user else "default"
    return PerUserConfig(tenant_id)


def require_user(request: Request):
    """FastAPI dependency: 必须已登录，否则 401。"""
    from src.admin.auth import get_current_user

    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def require_superuser(request: Request):
    """FastAPI dependency: 必须超级管理员，否则 403。"""
    user = require_user(request)
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
