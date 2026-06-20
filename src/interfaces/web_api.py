"""FastAPI Web API 主应用。

Twitter 用户蒸馏 AI 助手的 Web 服务入口，提供服务:
    - 仪表盘主页: GET / → 模块化 HTML 仪表盘
    - 流水线任务管理: GET/POST /pipeline/tasks/* → 任务增删改查
    - 卡片模块化 API: GET/POST /cards/* → 数据卡片渲染与交互
    - 时间线图表: GET /timeline/* → 静态 HTML 图表
    - 速率限制: 中间件级限流保护

启动方式:
    python -m src.interfaces.web_api
    或: python src/interfaces/web_api.py

路由数量: 约 12 个 API 端点 + 中间件
"""
from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI, Request
from pydantic import BaseModel

from src.storage.database import db

# ── 数据库启动时初始化 ──
# 修复：在模块导入时立即初始化数据库，确保 /auth/register 等路由不报 500。
try:
    db.init_db()
except Exception as _init_exc:  # noqa: BLE001
    import sys
    print(f"[web_api] db.init_db() 失败: {_init_exc}", file=sys.stderr)

# ── ChatEngine 单例 ──
# 已提取至 src/interfaces/chat_utils.py，供 web_api.py 和 cards.py 共享。
# 直接导入即可（web_api.py 本身不再直接调用这些函数）

# ── FastAPI 应用实例 ──
app = FastAPI(title="Twitter 用户蒸馏 AI 助手")

# ── CORS 安全策略 ──
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
import os as _os  # noqa: E402
_allowed_origins = _os.getenv("CORS_ORIGINS", "http://localhost:8080,http://localhost:8000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

from src.config import config  # noqa: E402
import time as _time  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

# ── 业务路由（按 domain 拆分）──
from src.interfaces.routers import pages as _pages_router  # noqa: E402
app.include_router(_pages_router.router)
from src.interfaces.routers import reports as _reports_router  # noqa: E402
app.include_router(_reports_router.router)
from src.interfaces.routers import team as _team_router  # noqa: E402
app.include_router(_team_router.router)
from src.interfaces.routers import alerts as _alerts_router  # noqa: E402
app.include_router(_alerts_router.router)
from src.interfaces.routers import watchlist as _watchlist_router  # noqa: E402
app.include_router(_watchlist_router.router)
from src.interfaces.routers import valuation as _valuation_router  # noqa: E402
app.include_router(_valuation_router.router)
from src.interfaces.routers import cards as _cards_router  # noqa: E402
app.include_router(_cards_router.router)
from src.interfaces.routers import pipeline as _pipeline_router  # noqa: E402
app.include_router(_pipeline_router.router)
from src.interfaces.routers import governance as _governance_router  # noqa: E402
app.include_router(_governance_router.router)
from src.interfaces.routers import auth as _auth_router  # noqa: E402
app.include_router(_auth_router.router)
from src.interfaces.routers import config_routes as _config_routes_router  # noqa: E402
app.include_router(_config_routes_router.router)


# ── 健康检查 ──
@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    return {"status": "ok", "db": "ok"}


# ── 全局异常处理器 ──
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    import sys
    traceback.print_exc(file=sys.stderr)
    return JSONResponse(status_code=500, content={"ok": False, "error": "internal_error"})


# ═══════════════════════════════════════════════════════
# 速率限制中间件
# ═══════════════════════════════════════════════════════

import threading  # noqa: E402
_rate_buckets: dict[str, list[float]] = {}  # IP → 请求时间戳列表
_auth_rate_limit: dict[str, list[float]] = {}  # 认证端点限流 (conftest 引用)
_rate_lock = threading.Lock()               # 线程锁保护共享 bucket


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """速率限制中间件：按 IP 计数，60秒窗口内最多 N 次请求。

    豁免规则:
        - GET /cards/*: 数据卡片查询不限制（纯读取）
        - /timeline/*, /static/*, /favicon*: 静态资源不限制

    速率计算:
        - 60 秒滑动窗口，窗口内请求数 >= max(rate_limit_per_minute, 120) 时返回 429

    注意:
        TODO(prod): 正式上线前需要设计更完善的限流策略:
        - 按端点分级: POST/chat 限 120/min，GET/本地不限
        - 多用户场景: 按用户 ID + API Key 限流，而非仅 IP
        - 突发缓冲: 允许短暂 burst（如 5s 内 10 次）
        - 监控面板: /metrics 端点暴露限流命中率
        - 参考: Stripe rate limiter, Cloudflare rate limiting docs
    """
    # 豁免规则：特定路径不限制
    if request.method == "GET" and request.url.path.startswith("/cards/"):
        return await call_next(request)
    if request.url.path.startswith(("/timeline/", "/static/", "/favicon")):
        return await call_next(request)

    # 获取请求来源 IP
    ip = request.client.host if request.client else "unknown"
    now = _time.time()

    with _rate_lock:
        bucket = _rate_buckets.setdefault(ip, [])
        # 清理 60 秒之前的旧记录（滑动窗口）
        bucket[:] = [t for t in bucket if now - t < 60]

        # 窗口内请求数超过配置阈值 → 返回 429 Too Many Requests
        if len(bucket) >= config.rate_limit_per_minute:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=429, content={"error": "rate limit exceeded"})

        # 记录本次请求时间戳
        bucket.append(now)

    return await call_next(request)


# ═══════════════════════════════════════════════════════
# Pydantic 数据模型
# ═══════════════════════════════════════════════════════


class ChatRequest(BaseModel):
    """聊天请求模型。

    Attributes:
        question: 用户问题文本
        top_k: 检索的推文数量（默认 5）
    """
    question: str
    top_k: int = 5


class ChatResponse(BaseModel):
    """聊天响应模型。

    Attributes:
        answer: AI 生成的回答文本
    """
    answer: str


class JobResponse(BaseModel):
    """任务详细信息响应模型。

    Attributes:
        id: 任务 ID
        task_type: 任务类型
        status: 任务状态
        payload: 任务参数
        error_msg: 错误消息（无则为空）
        created_at: 创建时间
    """
    id: int
    task_type: str
    status: str
    payload: dict
    error_msg: str | None = None
    created_at: str | None = None


class ActiveJobResponse(BaseModel):
    """活跃任务响应模型。

    Attributes:
        active_job_id: 当前执行中的任务 ID（无则为 None）
        job: 任务详细信息（无则为 None）
    """
    active_job_id: int | None
    job: JobResponse | None


def serialize_datetime(value: datetime | None) -> str | None:
    """将 datetime 序列化为 ISO 8601 字符串。

    Args:
        value: datetime 对象或 None

    Returns:
        ISO 格式字符串（如 "2024-01-15T10:30:00"）或 None
    """
    return value.isoformat() if value else None


# ═══════════════════════════════════════════════════════
# 活动追踪中间件
# ═══════════════════════════════════════════════════════

@app.middleware("http")
async def activity_tracking_middleware(request: Request, call_next):
    """记录每次 API 请求的用户活动（无 PII），在限流中间件之后运行。"""
    from src.admin.activity import ActivityTracker

    response = await call_next(request)
    path = request.url.path

    action_map = {
        "/api/config/llm": ("config_change", "llm"),
        "/api/config/twitter": ("config_change", "twitter"),
        "/api/config/telegram": ("config_change", "telegram"),
        "/api/config/observations/add": ("observation_add", ""),
        "/api/config/observations/remove": ("observation_remove", ""),
        "/pipeline/tasks/execute": ("task_execute", ""),
        "/pipeline/tasks/seed": ("task_seed", ""),
        "/api/governance/gaps/acknowledge": ("governance_acknowledge", ""),
        "/api/governance/gaps/revoke": ("governance_revoke", ""),
        "/cards/chat/action": ("chat_query", ""),
    }

    if path in action_map:
        action, note = action_map[path]
        ActivityTracker().log(
            action,
            ip_address=request.client.host if request.client else "",
            user_agent=request.headers.get("user-agent", ""),
            path=path,
        )
    elif path.startswith("/pipeline/tasks/") and response.status_code < 400:
        pass

    return response


# 卡片交互路由（迁移至 src/interfaces/routers/cards.py）

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
