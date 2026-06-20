"""Pydantic 响应模型（完整覆盖 —— 所有 API 路由均已 schema 化）。

设计原则:
    - 保持与前端现有解析逻辑完全兼容(不加 field alias, 不改字段名)
    - 简单的 ok 模式, 与现有 `{"ok": True/False, ...}` 完全一致
    - 复杂数据路由(Auth/Cards/meta、valuation、report 等)用 dict 兜底
    - 便于后续进一步细化

FastAPI 的 response_model 机制:
    1. 将 handler 返回的 dict 转换为 Pydantic 模型
    2. 运行时校验字段类型是否符合 schema
    3. 自动更新 OpenAPI 文档的 response 结构
    4. 排除未在 schema 中声明的字段(安全过滤)
"""
from __future__ import annotations

from pydantic import BaseModel, RootModel


# ═══════════════════════════════════════════════════════
# 基础响应(ok 模式 — 项目内最通用的模式)
# ═══════════════════════════════════════════════════════

class OkResponse(BaseModel):
    """通用 ok/error 响应基类。

    覆盖:
        - POST /auth/logout
        - POST /auth/refresh
        - POST /pipeline/tasks/{id}/skip
        - POST /pipeline/tasks/{id}/retry
    """
    ok: bool
    error: str | None = None


class OkWithMessage(OkResponse):
    """带 message 字段的 ok 响应。"""
    message: str | None = None


class OkWithCount(OkWithMessage):
    """带 message + count 的 ok 响应(用于 execute / clean 等)。"""
    count: int | None = None


# ═══════════════════════════════════════════════════════
# Auth 认证
# ═══════════════════════════════════════════════════════

class RegisterResponse(OkWithMessage):
    """POST /auth/register 响应。"""


class LoginResponse(OkResponse):
    """POST /auth/login 响应(成功时)。"""
    user_id: int | None = None
    username: str | None = None
    is_superuser: bool | None = None


class MeResponse(BaseModel):
    """GET /auth/me 响应。

    注意: 匿名未登录时 ok=False 但 logged_in=False 是合法响应, 不是错误。
    """
    ok: bool
    logged_in: bool
    user_id: int | None = None
    username: str | None = None
    is_superuser: bool | None = None


# ═══════════════════════════════════════════════════════
# 邀请码
# ═══════════════════════════════════════════════════════

class InviteCodeGenerateResponse(OkResponse):
    """POST /auth/invite-code/generate 响应。"""
    code: str | None = None


class InviteCodeItem(BaseModel):
    """单个邀请码记录。"""
    code: str
    is_used: bool
    created_at: str
    used_at: str
    used_by: int | None = None


class InviteCodeListResponse(BaseModel):
    """GET /auth/invite-codes 响应。"""
    codes: list[InviteCodeItem]
    total: int
    used: int


# ═══════════════════════════════════════════════════════
# 配置（LLM / Twitter / Telegram 共享同一模式）
# ═══════════════════════════════════════════════════════

class ConfigResponse(OkResponse):
    """POST /api/config/* 通用配置保存响应。"""
    config: dict | None = None


# ═══════════════════════════════════════════════════════
# 治理管线门禁
# ═══════════════════════════════════════════════════════

class GovernanceGapResponse(OkResponse):
    """POST /api/governance/gaps/* 响应。"""
    signal_id: str | None = None
    publish_status: str | None = None


# ═══════════════════════════════════════════════════════
# Pipeline 任务管理
# ═══════════════════════════════════════════════════════

class TaskItem(BaseModel):
    """Pipeline 任务列表中的单个任务。"""
    id: int
    task_type: str
    status: str
    payload: dict
    error_msg: str | None = None
    created_at: str | None = None


class ProgressInfo(BaseModel):
    """Pipeline 执行进度。"""
    total: int = 0
    done: int = 0
    msg: str = ""


class PipelineTasksResponse(BaseModel):
    """GET /pipeline/tasks 响应。"""
    tasks: list[TaskItem]
    running: bool
    progress: ProgressInfo


class TickersCountResponse(BaseModel):
    """GET /pipeline/tasks/fetched 和 crypto_fetched 响应。"""
    tickers: list[str]
    count: int


class PipelineActionResponse(OkWithCount):
    """POST /pipeline/{execute|skip|retry|edit} 响应。"""


class CleanResponse(OkResponse):
    """POST /pipeline/clean 响应。"""
    cleaned: int | None = None


class SeedResponse(OkWithMessage):
    """POST /pipeline/tasks/seed 响应。"""
    counts: dict | None = None


# ═══════════════════════════════════════════════════════
# Dashboard 卡片
# ═══════════════════════════════════════════════════════

class CardMetaItem(BaseModel):
    """单张卡片的元数据(供 /cards/meta 返回)。"""
    name: str
    tab: str
    tab_label: str
    tab_order: int
    order: int
    is_headline: bool = False
    span_full: bool = False
    refresh: int = 0
    display_title: str = ""
    subtitle: str = ""
    endpoint: str


class CardRenderResponse(BaseModel):
    """GET /cards/{name} 响应。"""
    html: str
    data: dict
    error: str | None = None


class CardActionResponse(OkResponse):
    """POST /cards/{name}/action 响应(动态字段由具体 action 决定)。"""
    html: str | None = None
    answer: str | None = None
    total: int | None = None


# ═══════════════════════════════════════════════════════
# 估值工具
# ═══════════════════════════════════════════════════════

class ValuationDcfResponse(BaseModel):
    """GET /api/valuation/dcf 响应。

    confidence 取值: "low" / "medium" / "high" / "unavailable"。
    unavailable 表示外部数据源（yfinance）异常或 ticker 找不到。
    """
    ticker: str
    intrinsic_value: float | None = None
    current_price: float | None = None
    upside_pct: float | None = None
    wacc: float | None = None
    growth_5y: float | None = None
    terminal_growth: float | None = None
    fcf: float | None = None
    confidence: str | None = None


class ValuationDDItem(BaseModel):
    """单条 DD checklist 项(供 /api/valuation/dd 返回)。"""
    category: str
    question: str
    status: str
    evidence: str = ""


# ═══════════════════════════════════════════════════════
# 预警
# ═══════════════════════════════════════════════════════

class AlertItem(BaseModel):
    """单个价格预警项目。"""
    ticker: str
    direction: str
    price: float


class AlertAddResponse(OkResponse):
    """POST /api/alerts/add 和 /remove 共享模式。"""
    alerts: list[AlertItem] | None = None


class AlertsCheckResponse(BaseModel):
    """POST /api/alerts/check 响应。"""
    checked: int
    triggered: int
    results: list[dict]


# ═══════════════════════════════════════════════════════
# Watchlist 自选操作
# ═══════════════════════════════════════════════════════

class WatchlistResponse(RootModel):
    """GET /api/watchlist 响应 — 直接暴露 list[str] 根级(保持前端兼容)。

    用 Pydantic v2 的 RootModel 包装 list[str],避免用 dict 兜底丢失类型信息。
    前端 / 集成测试都期望裸 list 返回, 直接传 `list[str]` 时 FastAPI 不会渲染字段说明;
    用 RootModel 可以让 OpenAPI 显示 `array of string` 的明确类型。
    """
    root: list[str]


class WatchlistModifyResponse(OkResponse):
    """POST /api/watchlist/add 和 /remove 响应。"""
    watchlist: list[str] | None = None


# ═══════════════════════════════════════════════════════
# 观察对象操作
# ═══════════════════════════════════════════════════════

class ObservationsResponse(OkResponse):
    """POST /api/config/observations/add 和 /remove 响应。"""
    observations: list[str] | None = None


# ═══════════════════════════════════════════════════════
# 团队共享池
# ═══════════════════════════════════════════════════════

class TeamSharedPoolResponse(BaseModel):
    """GET /api/team/shared-pool 响应。"""
    observations: list[str]


class TeamSharedPoolUpdateResponse(OkResponse):
    """POST /api/team/shared-pool/update 响应。"""
    observations: list[str]


# ═══════════════════════════════════════════════════════
# 报告
# ═══════════════════════════════════════════════════════

class SignalQualityReportResponse(BaseModel):
    """GET /api/reports/signal-quality 响应。"""
    period_days: int
    total_signals: int
    passed_gate: int
    pass_rate: float
    avg_confidence: float
    risk_flags: int
    panel_consensus: dict
    generated_at: str


# ═══════════════════════════════════════════════════════
# 健康检查
# ═══════════════════════════════════════════════════════

class HealthResponse(BaseModel):
    """GET /healthz 响应。"""
    status: str


class ReadyCheckResponse(BaseModel):
    """/ready 的 checks 子对象。"""
    database: str


class ReadyResponse(HealthResponse):
    """GET /ready 响应(包含详细检查)。"""
    checks: ReadyCheckResponse | None = None
