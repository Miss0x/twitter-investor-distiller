"""团队共享观察池 API：/api/team/shared-pool。

从 web_api.py 抽出，路径与原 @app.get/@app.post 完全一致。
"""
from __future__ import annotations

import json as _json
from pathlib import Path

from fastapi import APIRouter, Request

from src.api.schemas import TeamSharedPoolResponse, TeamSharedPoolUpdateResponse

router = APIRouter(prefix="/api/team", tags=["team"])


@router.get("/shared-pool", response_model=TeamSharedPoolResponse)
async def get_shared_pool(request: Request):
    """获取团队共享观察池（管理员配置）。"""
    pool_file = Path("data/team_shared_pool.json")
    if not pool_file.exists():
        return {"observations": []}
    return _json.loads(pool_file.read_text(encoding="utf-8"))


@router.post("/shared-pool/update", response_model=TeamSharedPoolUpdateResponse)
async def update_shared_pool(request: Request, payload: dict):
    """更新团队共享观察池（管理员操作）。"""
    observations = payload.get("observations", [])
    pool_file = Path("data/team_shared_pool.json")
    pool_file.parent.mkdir(parents=True, exist_ok=True)
    pool_file.write_text(_json.dumps({"observations": observations}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "observations": observations}