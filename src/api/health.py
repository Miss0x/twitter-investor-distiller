"""健康检查端点 — K8s liveness + readiness 模式。

端点:
    GET /healthz — 存活探针（轻量，不查依赖），用于 K8s livenessProbe
    GET /ready   — 就绪探针（查依赖），用于 K8s readinessProbe

设计:
    /healthz: 进程是否存活 — 即使 DB 暂时连不上也不重启 pod
    /ready:   依赖是否就绪 — DB/Redis 等不可用时返回 503，K8s 摘流量
"""
from __future__ import annotations

from fastapi import APIRouter, Response, status

from src.api.schemas import HealthResponse, ReadyResponse
from src.storage.database import db

router = APIRouter()


@router.get("/healthz", response_model=HealthResponse)
def liveness() -> dict:
    """Liveness 探针: 进程是否存活（最轻量级，不查依赖）。"""
    return {"status": "ok"}


@router.get("/ready", response_model=ReadyResponse)
def readiness(response: Response) -> dict:
    """Readiness 探针: 依赖是否就绪（DB 可达 + 查询能跑通）。"""
    checks: dict = {"status": "ok", "checks": {}}

    # ── DB 检查 ──
    try:
        session = db.get_session()
        try:
            session.execute(__import__("sqlalchemy").text("SELECT 1"))
            checks["checks"]["database"] = "ok"
        finally:
            session.close()
    except Exception as e:
        checks["status"] = "degraded"
        checks["checks"]["database"] = f"error: {e}"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return checks
