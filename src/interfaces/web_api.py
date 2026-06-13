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

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from src.storage.database import db
from src.storage.models import PipelineTask
from src.pipeline.task_executor import execute_tasks, is_running

# ── ChatEngine 单例 ──
# 避免每次请求都重新初始化 LLM 客户端连接；同时避免 Dashboard 启动依赖 ChromaDB。
_chat_engine = None


def _get_chat_engine():
    """获取 ChatEngine 单例实例（懒初始化）。"""
    global _chat_engine
    if _chat_engine is None:
        from src.ai.chat_engine import ChatEngine
        _chat_engine = ChatEngine()  # 首次调用时初始化
    return _chat_engine


def _normalize_chat_top_k(raw_value, default: int = 5) -> int:
    """规范化智能问答检索条数，避免非法值或过量检索。"""
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, 20))


# ── FastAPI 应用实例 ──
app = FastAPI(title="Twitter 用户蒸馏 AI 助手")

from src.config import config  # noqa: E402
import time as _time  # noqa: E402
from fastapi import Request  # noqa: E402


# ═══════════════════════════════════════════════════════
# 速率限制中间件
# ═══════════════════════════════════════════════════════

import threading  # noqa: E402
_rate_buckets: dict[str, list[float]] = {}  # IP → 请求时间戳列表
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
# 流水线任务管理 API
# ═══════════════════════════════════════════════════════


@app.get("/pipeline/tasks")
def list_tasks(task_type: str | None = None, status: str | None = None,
               limit: int = 200, offset: int = 0) -> dict:
    """列出流水线任务列表。

    请求格式:
        GET /pipeline/tasks?task_type=analyze&status=pending&limit=50&offset=0

    查询参数:
        - task_type: 任务类型筛选（filter/analyze/fetch_price/fetch_crypto/portrait）
        - status: 状态筛选（pending/running/completed/failed/skipped）
        - limit: 每页数量（默认 200）
        - offset: 分页偏移量

    Returns:
        {tasks: [...], running: bool, progress: ...}

    业务逻辑:
        查询 PipelineTask 表，支持类型和状态过滤，按 ID 降序排列
    """
    session = db.get_session()
    try:
        q = session.query(PipelineTask)
        # 可选筛选条件
        if task_type:
            q = q.filter(PipelineTask.task_type == task_type)
        if status:
            q = q.filter(PipelineTask.status == status)

        total = q.count()
        tasks = q.order_by(PipelineTask.id.desc()).limit(limit).offset(offset).all()

        return {
            "tasks": [
                {"id": t.id, "task_type": t.task_type, "status": t.status,
                 "payload": json.loads(t.payload) if t.payload else {},
                 "error_msg": t.error_msg,
                 "created_at": str(t.created_at)[:19] if t.created_at else None}
                for t in tasks
            ],
            "running": is_running(),       # 是否有后台任务执行中
            "progress": get_progress(),     # 当前执行进度
        }
    finally:
        session.close()  # 确保会话关闭


@app.post("/pipeline/tasks/execute")
def execute_selected(payload: dict) -> dict:
    """执行选中的待办任务。

    请求格式:
        POST /pipeline/tasks/execute
        Body: {"task_ids": [1, 2, 3]}

    业务逻辑:
        1. 校验任务 ID 列表合法性（非空、纯数字）
        2. 检查是否有任务正在执行（互斥锁）
        3. 查询 pending 状态的任务 ID 并过滤
        4. 启动后台线程执行任务（daemon 模式）

    Returns:
        {ok: True/False, message: ..., count: N}
    """
    task_ids = payload.get("task_ids", [])
    if not task_ids:
        return {"ok": False, "message": "未选择任务"}

    # 互斥：同时只能有一个任务组在运行
    if is_running():
        return {"ok": False, "message": "已有任务在执行中"}

    # 安全转换：兼容前端传字符串 ID
    try:
        task_ids = [int(x) for x in task_ids]
    except (ValueError, TypeError):
        return {"ok": False, "message": "非法任务ID"}

    # 查询数据库中实际存在的 pending 任务
    session = db.get_session()
    try:
        valid_ids = session.query(PipelineTask.id).filter(
            PipelineTask.id.in_(task_ids), PipelineTask.status == "pending"
        ).all()
        ids = [v[0] for v in valid_ids]  # 提取 ID 值
    finally:
        session.close()

    if not ids:
        return {"ok": False, "message": "没有可执行的待办任务"}

    # 后台线程执行，不阻塞 API 响应
    threading.Thread(target=execute_tasks, args=(ids,), daemon=True).start()
    return {"ok": True, "message": f"已启动 {len(ids)} 个任务", "count": len(ids)}


@app.post("/pipeline/tasks/{task_id}/skip")
def skip_task(task_id: int) -> dict:
    """标记任务为跳过状态（人工审核后决定忽略）。

    请求格式:
        POST /pipeline/tasks/42/skip

    业务逻辑:
        1. 查找指定 ID 的任务
        2. 状态更新为 "skipped"，error_msg 追加 "[人工跳过]"
        3. 如果有 ticker，同时写入 stock_alias.csv 记录映射关系

    Returns:
        {ok: True/False}
    """
    session = db.get_session()
    try:
        t = session.query(PipelineTask).get(task_id)
        if not t:
            return {"ok": False, "message": "任务不存在"}

        # 提取旧 ticker 用于别名保存
        old_ticker = json.loads(t.payload).get("ticker", "")

        # 更新任务状态
        t.status = "skipped"
        t.error_msg = (t.error_msg or "") + " [人工跳过]"

        # 写入别名映射（无目标 ticker = 标记跳过该别名）
        if old_ticker:
            _save_alias(old_ticker, "", "人工跳过")

        session.commit()
        return {"ok": True}
    finally:
        session.close()


@app.post("/pipeline/tasks/{task_id}/retry")
def retry_task(task_id: int) -> dict:
    """重置失败任务为待办状态（重试）。

    请求格式:
        POST /pipeline/tasks/42/retry

    业务逻辑:
        1. 查找任务
        2. 状态重置为 "pending"，清空 error_msg
        3. 提交数据库

    Returns:
        {ok: True/False}
    """
    session = db.get_session()
    try:
        t = session.query(PipelineTask).get(task_id)
        if not t:
            return {"ok": False, "message": "任务不存在"}

        t.status = "pending"
        t.error_msg = None
        session.commit()
        return {"ok": True}
    finally:
        session.close()


@app.post("/pipeline/tasks/{task_id}/edit")
def edit_task(task_id: int, payload: dict) -> dict:
    """编辑任务 ticker 并记忆映射。

    请求格式:
        POST /pipeline/tasks/42/edit
        Body: {"ticker": "AAPL", "sources": [...]}

    业务逻辑:
        1. 查找任务
        2. 从旧 payload 提取旧 ticker
        3. 更新 ticker 字段，重置状态为 pending
        4. 自动写入 stock_alias.csv 建立别名映射

    Returns:
        {ok: True/False, message: ...}
    """
    session = db.get_session()
    try:
        t = session.query(PipelineTask).get(task_id)
        if not t:
            return {"ok": False, "message": "任务不存在"}

        # 提取旧 ticker（用于建立别名映射）
        old_ticker = json.loads(t.payload).get("ticker", "")
        new_ticker = payload.get("ticker", "").strip().upper()

        if not new_ticker:
            return {"ok": False, "message": "ticker 不能为空"}

        # 更新 payload（保留 sources 不变，替换 ticker）
        t.payload = json.dumps({
            "ticker": new_ticker,
            "sources": json.loads(t.payload).get("sources", [])
        })
        t.status = "pending"
        t.error_msg = None
        session.commit()

        # 自动建立别名映射（如 "NVIDIA" → "NVDA"）
        _save_alias(old_ticker, new_ticker, "人工修正")
        return {"ok": True, "message": f"已更新为 {new_ticker}"}
    finally:
        session.close()


def _save_alias(from_name: str, to_ticker: str, note: str = "") -> None:
    """将别名映射追加到 stock_alias.csv（去重）。

    别名映射格式:
        from_name,to_ticker,note
        如: NVIDIA,NVDA,人工修正

    Args:
        from_name: 来源名称（如 LLM 提取的 "NVIDIA"）
        to_ticker: 目标代码（如 "NVDA"），空字符串表示标记跳过
        note: 备注信息（如 "人工跳过"、"人工修正"）
    """
    alias_path = Path("data/stock_alias.csv")

    # 读取现有数据
    lines = alias_path.read_text(encoding="utf-8").split("\n") if alias_path.exists() else []
    norm = from_name.strip()
    for line in lines:
        # 已存在同名的→跳过写入
        if line.strip() and line.split(",")[0].strip().lower() == norm.lower():
            return

    # 追加新行
    with open(alias_path, "a", encoding="utf-8") as f:
        f.write(f"\n{norm},{to_ticker},{note}")


@app.get("/pipeline/tasks/fetched")
def list_fetched_tickers() -> dict:
    """返回已有股价数据的 ticker 列表。

    请求格式:
        GET /pipeline/tasks/fetched

    Returns:
        {tickers: ["AAPL", "NVDA", ...], count: N}

    数据来源: data/prices.json
    """
    pp = Path("data/prices.json")
    if pp.exists():
        tickers = sorted(json.loads(pp.read_text(encoding="utf-8")).keys())
        return {"tickers": tickers, "count": len(tickers)}
    return {"tickers": [], "count": 0}


@app.get("/pipeline/tasks/crypto_fetched")
def list_crypto_fetched() -> dict:
    """返回已有加密货币行情的列表。

    请求格式:
        GET /pipeline/tasks/crypto_fetched

    Returns:
        {tickers: ["BTC-USD", "ETH-USD", ...], count: N}

    数据来源: data/crypto_prices.json
    """
    pp = Path("data/crypto_prices.json")
    if pp.exists():
        tickers = sorted(json.loads(pp.read_text(encoding="utf-8")).keys())
        return {"tickers": tickers, "count": len(tickers)}
    return {"tickers": [], "count": 0}


def _load_skip_set() -> set[str]:
    """从别名表读取已跳过/已修正的条目（防止种子时重复生成任务）。

    Returns:
        需要跳过的 alias 集合（大写格式）
    """
    skip = set()
    ap = Path("data/stock_alias.csv")
    if ap.exists():
        for line in ap.read_text(encoding="utf-8").split("\n"):
            parts = line.strip().split(",")
            if len(parts) >= 2:
                alias = parts[0].strip()
                target = parts[1].strip()
                # 空目标 = 标记跳过
                if alias and not target:
                    skip.add(alias.upper())
                elif alias and target:
                    skip.add(alias.upper())  # 已修正的也不再新生成任务
    return skip


def _is_known_stock_ticker(ticker: str) -> bool:
    """判断 crypto_details 中的项是否实际是已知股票代码。

    场景: LLM 可能将 "TSM" 同时标记为 crypto，但 TSM 是台积电股票

    Args:
        ticker: 待判断的代码

    Returns:
        True = 该代码在股票别名表中且已映射到有效目标
    """
    import re as _re
    # 必须是 1-5 位大写字母
    if not _re.match(r"^[A-Z]{1,5}$", ticker):
        return False
    ap = Path("data/stock_alias.csv")
    if not ap.exists():
        return False
    for line in ap.read_text(encoding="utf-8").split("\n"):
        parts = [x.strip() for x in line.strip().split(",")]
        if len(parts) >= 2 and parts[0].upper() == ticker.upper():
            return bool(parts[1])  # 有目标 ticker = 是股票代码
    return False


@app.post("/pipeline/clean")
def run_clean() -> dict:
    """运行数据清洗：用 stock_alias.csv 校准已分析推文的股票别名。

    请求格式:
        POST /pipeline/clean

    业务逻辑:
        1. 加载 stock_alias.csv 中所有有效别名映射（alias → ticker）
        2. 遍历 data/pipeline/*_analyzed.json 中的每条记录
        3. 对每条记录的 mentioned_stocks 列表应用别名映射替换
        4. 标记变更过的记录（_cleaned = True）

    Returns:
        {ok: True, cleaned: N} 或 {ok: False, error: ...}
    """
    import csv as _csv
    try:
        # ── 加载别名映射表 ──
        alias = {}
        afp = Path("data/stock_alias.csv")
        if afp.exists():
            with open(afp, encoding="utf-8") as f:
                for row in _csv.reader(f):
                    # 过滤掉注释行和空映射
                    if row and not row[0].startswith("#") and len(row) >= 2 \
                       and row[0].strip() and row[1].strip():
                        alias[row[0].strip()] = row[1].strip()

        cleaned = 0  # 清洗计数

        # ── 遍历所有分析结果文件 ──
        for fp in sorted(Path("data/pipeline").glob("*_analyzed.json")):
            data = json.loads(fp.read_text(encoding="utf-8"))
            updated = False
            for item in data:
                stocks = item.get("mentioned_stocks", [])
                if stocks:
                    # 应用别名映射替换
                    mapped = [alias.get(s.strip(), s.strip()) for s in stocks]
                    if mapped != stocks:
                        item["mentioned_stocks"] = mapped
                        item["_cleaned"] = True  # 标记已清洗
                        updated = True
                        cleaned += 1
            if updated:
                fp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        return {"ok": True, "cleaned": cleaned}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/pipeline/tasks/seed")
def seed_tasks() -> dict:
    """扫描未处理项，写入任务表（增量模式，不清理已有待办）。

    请求格式:
        POST /pipeline/tasks/seed

    任务类型与生成逻辑:
        1. filter: 扫描 DB 中新推文（未在 filtered JSON 中的）
        2. analyze: 从过滤结果中生成分析任务（投资相关 + 未分析）
        3. fetch_price: 从清洗后数据提取已验证的股票 ticker
        4. fetch_crypto: 从清洗后数据提取加密货币代码
        5. portrait: 每用户 × 5 个时间窗口（1月/3月/6月/1年/全量）

    Returns:
        执行结果消息（新增任务汇总）
    """
    session = db.get_session()
    counts = {"filter": 0, "analyze": 0, "fetch_price": 0, "fetch_crypto": 0, "portrait": 0}
    type_names = {"filter": "筛选推文", "analyze": "分析观点",
                  "fetch_price": "补全行情", "fetch_crypto": "补全加密行情", "portrait": "生成画像"}
    try:
        # ── 辅助函数：从文件名解析用户名和月份 ──
        def _parse_stem(stem: str) -> tuple[str, str]:
            """从文件名 stem 提取 (username, month_label)"""
            import re as _re
            # 格式: username_YYYY-MM_...
            m = _re.match(r"(.+?)_(\d{4}-\d{2})_.*", stem)
            if m:
                return m.group(1), m.group(2)
            parts = stem.split("_")
            if len(parts) >= 2:
                return parts[0], "_".join(parts[1:])
            return stem, ""

        # ══ 第一步: 从 DB 扫描新推文 → 创建 filter 任务 ══
        from src.storage.models import Tweet, User as DbUser

        # 收集已过滤的 tweet_id（避免重复创建 filter 任务）
        filtered_ids: set[int] = set()
        for fp in Path("data/pipeline").glob("*_filtered.json"):
            for t in json.loads(fp.read_text(encoding="utf-8")):
                filtered_ids.add(t.get("tweet_id"))
                filtered_ids.add(t.get("id"))

        # 也检查数据库中已有 filter 任务的 tweet_id
        for t in session.query(PipelineTask).filter(PipelineTask.task_type == "filter").all():
            try:
                pid = json.loads(t.payload).get("tweet_id")
                if pid:
                    filtered_ids.add(pid)
            except (json.JSONDecodeError, TypeError):
                pass

        # 遍历所有用户的所有推文，生成 filter 任务
        for u in session.query(DbUser).all():
            for tw in session.query(Tweet).filter(
                Tweet.user_id == u.id, Tweet.text != None, Tweet.text != ""
            ).order_by(Tweet.id).all():
                if tw.id not in filtered_ids and tw.tweet_id not in filtered_ids:
                    t = PipelineTask(task_type="filter", status="pending",
                                     payload=json.dumps({
                                         "action": "filter_single",
                                         "tweet_id": tw.id,
                                     }, ensure_ascii=False))
                    session.add(t)
                    counts["filter"] += 1

        # ══ 第二步: 从过滤结果生成 analyze 任务 ══
        # 收集已有分析任务的 tweet_id（避免 Like 查询）
        existing_tweet_ids = set()
        for t in session.query(PipelineTask).filter(PipelineTask.task_type == "analyze").all():
            try:
                pid = json.loads(t.payload).get("tweet_id")
                if pid:
                    existing_tweet_ids.add(pid)
            except (json.JSONDecodeError, TypeError):
                pass

        for fp in Path("data/pipeline").glob("*_filtered.json"):
            username, month = _parse_stem(fp.stem.replace("_filtered", ""))
            data = json.loads(fp.read_text(encoding="utf-8"))

            # 收集该用户所有已分析的 tweet_id
            done_ids = set()
            for ap in Path("data/pipeline").glob(f"{username}_*_analyzed.json"):
                if "_cleaned" in ap.name:
                    continue
                for r in json.loads(ap.read_text(encoding="utf-8")):
                    done_ids.add(r.get("tweet_id"))

            for tweet in data:
                # 仅处理投资相关 + 未分析 + 未在 DB 中存在的
                if not tweet.get("is_investment_related") or \
                   tweet["id"] in done_ids or tweet["id"] in existing_tweet_ids:
                    continue
                t = PipelineTask(task_type="analyze", status="pending",
                                 payload=json.dumps({
                                     "username": username, "tweet_id": tweet["id"],
                                     "text": tweet["text"],
                                     "created_at": tweet.get("created_at", ""),
                                     "tweet_id_str": tweet.get("tweet_id", ""),
                                     "is_reply": tweet.get("is_reply", False),
                                     "is_quote": tweet.get("is_quote", False),
                                     "replied_to_user": tweet.get("replied_to_user", ""),
                                     "quoted_user": tweet.get("quoted_user", ""),
                                 }, ensure_ascii=False))
                session.add(t)
                counts["analyze"] += 1

        # ══ 第三步: 拉取股价任务 ══
        price_path = Path("data/prices.json")
        existing_prices = set()
        if price_path.exists():
            existing_prices = set(json.loads(price_path.read_text(encoding="utf-8")).keys())

        skip_set = _load_skip_set()  # 已跳过/修正的别名单

        # 收集每个 ticker 的来源推文（最多 3 条，用于前端显示）
        all_stocks = {}  # ticker → [{user, text, date, url}]
        for ap in Path("data/pipeline").glob("*_analyzed_cleaned.json"):
            username, _ = _parse_stem(ap.stem.replace("_analyzed_cleaned", ""))
            for r in json.loads(ap.read_text(encoding="utf-8")):
                for sd in r.get("stock_details", []):
                    if not sd.get("verified") or sd.get("type") not in ("stock", "etf"):
                        continue
                    ticker = sd["ticker"]
                    if ticker and ticker not in existing_prices:
                        if ticker not in all_stocks:
                            all_stocks[ticker] = []
                        if len(all_stocks[ticker]) < 3:
                            all_stocks[ticker].append({
                                "user": username,
                                "text": r.get("text", "")[:100],
                                "date": r.get("created_at", "")[:10],
                                "url": f"https://x.com/{username}/status/{r.get('twitter_id', '')}",
                            })

        for ticker in sorted(all_stocks):
            if ticker in skip_set:
                continue
            t = PipelineTask(task_type="fetch_price", status="pending",
                             payload=json.dumps({
                                 "ticker": ticker,
                                 "sources": all_stocks[ticker],
                             }, ensure_ascii=False))
            session.add(t)
            counts["fetch_price"] += 1

        # ══ 第四步: 加密货币行情任务 ══
        crypto_path = Path("data/crypto_prices.json")
        existing_crypto = set()
        if crypto_path.exists():
            existing_crypto = set(json.loads(crypto_path.read_text(encoding="utf-8")).keys())

        all_cryptos: dict[str, list[dict]] = {}
        for ap in Path("data/pipeline").glob("*_analyzed_cleaned.json"):
            username, _ = _parse_stem(ap.stem.replace("_analyzed_cleaned", ""))
            for r in json.loads(ap.read_text(encoding="utf-8")):
                for c in r.get("crypto_details", []):
                    if c and c not in existing_crypto:
                        if c not in all_cryptos:
                            all_cryptos[c] = []
                        if len(all_cryptos[c]) < 3:
                            all_cryptos[c].append({
                                "user": username,
                                "text": r.get("text", "")[:100],
                                "date": r.get("created_at", "")[:10],
                                "url": f"https://x.com/{username}/status/{r.get('twitter_id', '')}",
                            })

        for ticker in sorted(all_cryptos):
            if ticker in skip_set:
                continue
            if _is_known_stock_ticker(ticker):  # 排除已知的股票代码
                continue
            t = PipelineTask(task_type="fetch_crypto", status="pending",
                             payload=json.dumps({
                                 "ticker": ticker,
                                 "sources": all_cryptos[ticker],
                             }, ensure_ascii=False))
            session.add(t)
            counts["fetch_crypto"] += 1

        # ══ 第五步: 用户画像生成任务 ══
        from datetime import datetime, timedelta
        import re as _re

        # 预设时间窗口
        windows = {
            "1个月": 30, "3个月": 90, "6个月": 180, "1年": 365, "全量": 9999,
        }

        # 收集每用户所有推文
        user_tweets: dict[str, list[dict]] = {}
        for ap in Path("data/pipeline").glob("*_analyzed_cleaned.json"):
            username, _ = _parse_stem(ap.stem.replace("_analyzed_cleaned", ""))
            if username not in user_tweets:
                user_tweets[username] = []
            user_tweets[username].extend(json.loads(ap.read_text(encoding="utf-8")))

        now = datetime.utcnow()
        for username, tweets in user_tweets.items():
            for label, days in windows.items():
                # 计算窗口截止日期
                cutoff = now - timedelta(days=days) if days < 9999 else datetime(2000, 1, 1)
                # 统计窗口内推文数量
                count = sum(1 for t in tweets
                           if t.get("created_at", "") and
                           t["created_at"][:10] >= cutoff.strftime("%Y-%m-%d"))

                tag = f"{username}_{label}"  # 如: TJ_Research_1个月

                # 检查是否已有该画像任务
                existing = session.query(PipelineTask).filter(
                    PipelineTask.task_type == "portrait",
                    PipelineTask.payload.contains(f'"username": "{tag}"'),
                ).first()
                if existing:
                    continue

                t = PipelineTask(task_type="portrait", status="pending",
                                 payload=json.dumps({
                                     "username": tag, "label": label,
                                     "window_days": days, "tweet_count": count,
                                 }, ensure_ascii=False))
                session.add(t)
                counts["portrait"] += 1

        session.commit()

        # 构建汇总消息
        parts = [f"{v} 条{type_names.get(k, k)}" for k, v in counts.items() if v > 0]
        msg = "新增: " + ", ".join(parts) if parts else "无需新增任务"
        return {"ok": True, "message": msg, "counts": counts}
    except Exception as e:
        session.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        session.close()


# ═══════════════════════════════════════════════════════
# 卡片模块化 API
# ═══════════════════════════════════════════════════════

from src.cards import CARDS, get_card  # noqa: E402
from src.cards.base import TEMPLATE_DIR  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402

# 卡片缓存：{name: ((html, data), expire_timestamp)}
_card_cache: dict[str, tuple[tuple[str, dict], float]] = {}
_CACHE_TTL = 2  # 缓存生存时间（秒）


def _get_cached_card_html(name: str) -> tuple[str, dict] | None:
    """从服务端缓存获取卡片 HTML 和 data。

    Args:
        name: 卡片名称

    Returns:
        (html, data) 元组，None 表示未命中或已过期
    """
    now = _time.time()
    if name in _card_cache:
        (html, data), expire = _card_cache[name]
        if now < expire:
            return (html, data)
    return None


def _set_cached_card_html(name: str, html: str, data: dict) -> None:
    """设置卡片缓存（HTML + data 一起缓存）。

    Args:
        name: 卡片名称
        html: 渲染后的 HTML 字符串
        data: get_data() 返回的结构化数据
    """
    _card_cache[name] = ((html, data), _time.time() + _CACHE_TTL)


# ═══════════════════════════════════════════════════════
# 卡片 API
# ═══════════════════════════════════════════════════════

@app.get("/cards/meta")
async def cards_meta():
    """返回所有已注册卡片的元数据列表。

    请求格式:
        GET /cards/meta

    Returns:
        [{name: "dashboard_stats", title: "...", ...}, ...]

    用于前端自动发现和渲染卡片列表
    """
    return [c.to_dict() for c in CARDS]


@app.get("/cards/{name}")
async def card_data(name: str, request: Request):
    """返回单个卡片渲染结果，信封模式 {html, data, error}。"""
    # 设置当前请求上下文，供卡片 get_data() 读取用户信息
    from src.cards.config_center_card import _current_request
    _current_request.set(request)
    try:
        return await _render_card_data(name)
    finally:
        _current_request.set(None)


async def _render_card_data(name: str):
    # 尝试从缓存读取
    cached = _get_cached_card_html(name)
    if cached is not None:
        html, data = cached
        return {"html": html, "data": data, "error": None}

    card = get_card(name)
    if card is None:
        raise HTTPException(status_code=404, detail=f"Card '{name}' not found")

    try:
        data = card.get_data()       # 获取卡片数据
        # ── 规则五：dataclass schema 校验 ──
        from src.cards.card_schema import validate_card_data
        data, schema_warning = validate_card_data(name, data)
        html = card.render(data)     # 渲染为 HTML
        _set_cached_card_html(name, html, data)
        return {"html": html, "data": data, "error": None}
    except Exception as e:
        return {
            "html": (
                f'<div class="card"><div class="flex">'
                f'<div class="status-dot err"></div>'
                f'<span class="text-secondary">{name}: '
                f'{str(e).replace("<","&lt;").replace(">","&gt;")}'
                f'</span></div></div>'
            ),
            "data": {},
            "error": str(e),
        }


@app.post("/api/governance/gaps/acknowledge")
async def acknowledge_governance_gap(payload: dict):
    """Temporarily accept a governance data issue and rerun checks."""
    try:
        from src.governance.gap_actions import acknowledge_gap_for_signal
        from src.governance.repository import GovernanceRepository

        result = acknowledge_gap_for_signal(
            repo=GovernanceRepository(),
            signal_id=str(payload.get("signal_id") or ""),
            gap_code=str(payload.get("gap_code") or ""),
            reason=str(payload.get("reason") or ""),
            expires_in_hours=int(payload.get("expires_in_hours") or 72),
        )
        _card_cache.pop("quality_gate", None)
        _card_cache.pop("publish_review", None)
        return result
    except Exception as e:
        return {"ok": False, "error": str(e) or "操作没有保存成功"}


@app.post("/api/governance/gaps/revoke")
async def revoke_governance_gap(payload: dict):
    """Stop accepting a governance data issue and rerun checks."""
    try:
        from src.governance.gap_actions import revoke_gap_acknowledgement
        from src.governance.repository import GovernanceRepository

        result = revoke_gap_acknowledgement(
            repo=GovernanceRepository(),
            signal_id=str(payload.get("signal_id") or ""),
            gap_code=str(payload.get("gap_code") or ""),
            reason=str(payload.get("reason") or "重新检查这个风险"),
        )
        _card_cache.pop("quality_gate", None)
        _card_cache.pop("publish_review", None)
        return result
    except Exception as e:
        return {"ok": False, "error": str(e) or "操作没有保存成功"}


# ═══════════════════════════════════════════════════════
# 认证 API — 注册/登录/登出
# ═══════════════════════════════════════════════════════

@app.post("/auth/register")
async def auth_register(payload: dict):
    """用户注册。"""
    from src.admin.auth import hash_password
    from src.admin.auth_models import User
    from src.storage.database import db
    email = str(payload.get("email") or "").strip()
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    if not email or not username or not password:
        return {"ok": False, "error": "请填写邮箱、用户名和密码"}
    if len(password) < 6:
        return {"ok": False, "error": "密码至少 6 位"}
    session = db.get_session()
    try:
        if session.query(User).filter(User.email == email).first():
            return {"ok": False, "error": "邮箱已注册"}
        if session.query(User).filter(User.username == username).first():
            return {"ok": False, "error": "用户名已存在"}
        user = User(email=email, username=username, hashed_password=hash_password(password))
        session.add(user)
        session.commit()
        return {"ok": True, "user_id": user.id, "username": user.username}
    finally:
        session.close()


@app.post("/auth/login")
async def auth_login(payload: dict, response: Response):
    """用户登录。返回 Access Token (Cookie) + Refresh Token (Cookie)。"""
    from src.admin.auth import create_access_token, verify_password
    from src.admin.auth_models import User
    from src.admin.refresh_token import create_refresh_family
    from src.storage.database import db
    email = str(payload.get("email") or "").strip()
    password = str(payload.get("password") or "")
    if not email or not password:
        return {"ok": False, "error": "请填写邮箱和密码"}
    session = db.get_session()
    try:
        user = session.query(User).filter(User.email == email).first()
        if not user or not verify_password(password, user.hashed_password):
            return {"ok": False, "error": "邮箱或密码错误"}
        if not user.is_active:
            return {"ok": False, "error": "账号已被停用"}
        access_token = create_access_token({"sub": user.id, "email": user.email})
        raw_refresh, _ = create_refresh_family(session, user.id, days=7)
        response.set_cookie(
            key="access_token", value=access_token, httponly=True, samesite="lax",
            max_age=1800, secure=False, path="/",
        )
        response.set_cookie(
            key="refresh_token", value=raw_refresh, httponly=True, samesite="strict",
            max_age=7*86400, secure=False, path="/auth/refresh",
        )
        return {
            "ok": True, "user_id": user.id, "username": user.username,
            "is_superuser": user.is_superuser,
        }
    finally:
        session.close()


@app.post("/auth/refresh")
async def auth_refresh(request: Request, response: Response):
    """刷新 Access Token。使用 Refresh Token 轮换机制。"""
    from src.admin.auth import create_access_token
    from src.admin.refresh_token import rotate_refresh_token
    from src.storage.database import db
    raw_refresh = request.cookies.get("refresh_token", "")
    if not raw_refresh:
        return {"ok": False, "error": "无 Refresh Token"}
    session = db.get_session()
    try:
        result = rotate_refresh_token(session, raw_refresh)
        if result is None:
            return {"ok": False, "error": "Token 无效或已过期，请重新登录"}
        new_raw, _ = result
        # 从旧 refresh token 中获取 user_id（通过 hash 查记录）
        from src.admin.refresh_token import _hash_token
        from src.admin.refresh_token import RefreshToken
        record = session.query(RefreshToken).filter(
            RefreshToken.used == False,
            RefreshToken.family.in_(
                session.query(RefreshToken.family).filter(
                    RefreshToken.token_hash == _hash_token(raw_refresh)
                ).subquery()
            )
        ).order_by(RefreshToken.created_at.desc()).first()
        user_id = record.user_id if record else None
        if user_id is None:
            return {"ok": False, "error": "会话已失效"}
        access_token = create_access_token({"sub": user_id, "email": ""})
        response.set_cookie(
            key="access_token", value=access_token, httponly=True, samesite="lax",
            max_age=1800, secure=False, path="/",
        )
        response.set_cookie(
            key="refresh_token", value=new_raw, httponly=True, samesite="strict",
            max_age=7*86400, secure=False, path="/auth/refresh",
        )
        return {"ok": True}
    finally:
        session.close()
        }
    finally:
        session.close()


@app.post("/auth/logout")
async def auth_logout(response: Response):
    """登出。"""
    response.delete_cookie("access_token")
    return {"ok": True}


@app.get("/auth/me")
async def auth_me(request: Request):
    """获取当前登录用户信息。"""
    from src.admin.auth import get_current_user
    user = get_current_user(request)
    if user is None:
        return {"ok": False, "logged_in": False}
    return {
        "ok": True, "logged_in": True,
        "user_id": user.id, "username": user.username,
        "is_superuser": user.is_superuser,
    }


# ═══════════════════════════════════════════════════════
# 用户配置中心 API
# ═══════════════════════════════════════════════════════

@app.get("/api/config")
async def get_full_config(request: Request):
    """返回当前用户配置（敏感字段已脱敏，磁盘加密存储）。"""
    from src.admin.auth import get_current_user
    from src.multi_tenant.config import PerUserConfig
    user = get_current_user(request)
    tenant_id = str(user.id) if user else "default"
    try:
        return PerUserConfig(tenant_id).load_masked()
    except Exception:
        from src.config_center import ConfigManager
        return ConfigManager().load_masked()


@app.post("/api/config/llm")
async def save_llm_config(request: Request, payload: dict):
    """保存 LLM 配置（加密存储到磁盘）。"""
    from src.admin.auth import get_current_user
    from src.multi_tenant.config import PerUserConfig
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


@app.post("/api/config/twitter")
async def save_twitter_config(request: Request, payload: dict):
    """保存 Twitter API 配置（加密存储）。"""
    from src.admin.auth import get_current_user
    from src.multi_tenant.config import PerUserConfig
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


@app.post("/api/config/telegram")
async def save_telegram_config(request: Request, payload: dict):
    """保存 Telegram Bot 配置（加密存储）。"""
    from src.admin.auth import get_current_user
    from src.multi_tenant.config import PerUserConfig
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


@app.post("/api/config/observations/add")
async def add_observation(request: Request, payload: dict):
    """添加观察对象（到当前用户配置）。"""
    username = str(payload.get("username") or "").strip().lstrip("@")
    if not username:
        return {"ok": False, "error": "请输入用户名"}
    from src.admin.auth import get_current_user
    from src.multi_tenant.config import PerUserConfig
    user = get_current_user(request)
    tenant_id = str(user.id) if user else "default"
    try:
        cfg = PerUserConfig(tenant_id)
        config = cfg.add_observation(username)
        return {"ok": True, "observations": config["observations"]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/config/observations/remove")
async def remove_observation(request: Request, payload: dict):
    """移除观察对象（从当前用户配置）。"""
    username = str(payload.get("username") or "").strip()
    if not username:
        return {"ok": False, "error": "请指定用户名"}
    from src.admin.auth import get_current_user
    from src.multi_tenant.config import PerUserConfig
    user = get_current_user(request)
    tenant_id = str(user.id) if user else "default"
    try:
        cfg = PerUserConfig(tenant_id)
        config = cfg.remove_observation(username)
        return {"ok": True, "observations": config["observations"]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── 用户配置中心 API ──


# ── 活动追踪中间件：自动记录 API 请求 ──

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


@app.post("/cards/{name}/action")
async def card_action(name: str, payload: dict = None):
    """处理卡片交互动作（统一分发入口）。

    请求格式:
        POST /cards/{name}/action
        Body: {action: "...", ...}

    支持的动作分发（按卡片名称路由）:
        - daemon: 守护进程启停控制
        - telegram: Telegram 配置保存/测试
        - role_picker: 角色代入选股（→ handlers_insights）
        - portfolio: 持仓分析（→ handlers_insights）
        - fetch_control: 手动拉取推文（→ handlers_exec）
        - pipeline_execute: 流水线执行（→ handlers_exec）
        - script_runner: 脚本运行（→ handlers_exec）
        - portrait_generate: 画像生成（→ handlers_data）
        - asset_alias: 资产别名管理（→ handlers_data）
        - api_status: 用户管理（→ handlers_data）

    Returns:
        {ok: True/False, ...} 或 {ok: False, error: "unknown action"}
    """
    # ── 守护进程控制 ──
    if name == "daemon" and payload and payload.get("action") == "toggle":
        try:
            import subprocess, sys
            from src.cards import get_card
            card = get_card("daemon")
            proc = getattr(card, "_proc", None)

            if proc and proc.poll() is None:
                # 进程正在运行 → 终止
                proc.terminate()
                card._proc = None
            else:
                # 进程未运行 → 启动
                proc = subprocess.Popen([sys.executable, "scripts/daemon_worker.py"])
                card._proc = proc

            _card_cache.pop("daemon", None)  # 清除缓存（状态已变）
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Telegram 配置 ──
    if name == "telegram" and payload:
        try:
            from src.admin.auth import get_current_user
            from src.multi_tenant.config import PerUserConfig
            user = get_current_user(request)
            tenant_id = str(user.id) if user else "default"
            token = payload.get("token", "")
            chat_id = payload.get("chat_id", "")
            cfg = PerUserConfig(tenant_id)
            cfg.save_section("telegram", {"bot_token": token, "chat_id": chat_id})
            _card_cache.pop("telegram", None)

            if payload.get("action") == "test":
                import requests as _req
                _req.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat_id,
                                "text": "✅ 投资信号蒸馏台测试消息成功！"})
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── 智能问答 ──
    if name == "chat" and payload and payload.get("action") == "ask":
        try:
            question = (payload.get("question") or "").strip()
            if not question:
                return {"ok": False, "error": "问题不能为空"}
            top_k = _normalize_chat_top_k(payload.get("top_k", 5))
            answer = _get_chat_engine().answer(question, top_k=top_k)
            return {"ok": True, "answer": answer}
        except Exception as e:
            return {"ok": False, "error": f"智能问答暂不可用：{e}"}

    # ── 角色代入选股 ──
    if name == "role_picker" and payload:
        try:
            result = _handle_role_picker(payload)
            return {"ok": True, "html": result}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── 持仓分析 ──
    if name == "portfolio" and payload:
        try:
            result = _handle_portfolio_analysis(payload)
            return {"ok": True, "html": result}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── 手动拉取控制 ──
    if name == "fetch_control" and payload:
        try:
            result = _handle_fetch_control(payload)
            return {'ok': True, 'total': result.get('total_new', 0)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── 流水线执行 ──
    if name == "pipeline_execute" and payload:
        return _handle_pipeline_action(payload)

    # ── 脚本运行 ──
    if name == "script_runner" and payload:
        return _handle_script_run(payload)

    # ── 画像生成 ──
    if name == "portrait_generate" and payload:
        return _handle_portrait_generate(payload)

    # ── 资产别名管理 ──
    if name == "asset_alias" and payload:
        return _handle_asset_alias(payload)

    # ── 用户管理 ──
    if name == "api_status" and payload and payload.get("action") in ("add_user", "remove_user"):
        return _handle_user_manage(payload)

    return {"ok": False, "error": "unknown action"}


# ═══════════════════════════════════════════════════════
# 跨模块 Handler 导入
# ═══════════════════════════════════════════════════════
# 这些函数被上面的 card_action 分发器调用，
# 单独提取到独立文件以保持 web_api.py 简洁

from src.interfaces.handlers_insights import _handle_role_picker, _handle_portfolio_analysis
from src.interfaces.handlers_exec import _handle_fetch_control, _handle_pipeline_action, _handle_script_run
from src.interfaces.handlers_data import _handle_asset_alias, _handle_portrait_generate, _handle_user_manage


# ═══════════════════════════════════════════════════════
# 静态页面路由
# ═══════════════════════════════════════════════════════


@app.get("/", response_class=HTMLResponse)
async def serve_landing():
    """服务产品首页（Landing Page）。

    展示产品介绍、核心能力和流水线流程，
    引导用户进入控制台。
    """
    landing = TEMPLATE_DIR / "landing.html"
    if landing.exists():
        return HTMLResponse(
            content=landing.read_text(encoding="utf-8"),
        )
    # Fallback：如果 landing.html 不存在，跳转到 dashboard
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    """仪表盘主页（需要登录）。未登录重定向到首页。"""
    from src.admin.auth import get_current_user
    user = get_current_user(request)
    if user is None:
        return RedirectResponse("/", status_code=302)
    base = TEMPLATE_DIR / "base.html"
    return HTMLResponse(
        content=base.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )


@app.get("/timeline/{path:path}", response_class=HTMLResponse)
async def serve_timeline(path: str):
    """服务时间线图表 HTML 文件。

    请求格式:
        GET /timeline/some_chart.html

    安全:
        - 路径解析后验证必须在 data/timeline/ 目录内（防目录遍历）
        - 仅允许 .html 文件

    Returns:
        HTMLResponse: 时间线图表的 HTML

    Raises:
        HTTPException(403): 路径不在允许范围内
        HTTPException(404): 文件不存在或不是 .html
    """
    import os as _os
    fp = (Path("data/timeline") / path).resolve()
    allowed = Path("data/timeline").resolve()

    # 路径安全检查：防止 ../ 逃逸到上级目录
    if not str(fp).startswith(str(allowed)):
        raise HTTPException(status_code=403, detail="forbidden")

    if fp.exists() and fp.suffix == ".html":
        return HTMLResponse(content=fp.read_text(encoding="utf-8"))

    raise HTTPException(status_code=404, detail="not found")


# ═══════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════
# 估值工具 API — DCF/Comps/DD
# ═══════════════════════════════════════════════════════

@app.get("/api/valuation/dcf")
async def valuation_dcf(ticker: str, wacc: float | None = None, growth: float | None = None, terminal: float | None = None):
    from src.data.valuation_tools import ValuationTools
    result = ValuationTools().recalculate_dcf(
        ticker.upper(), wacc=wacc, growth_5y=growth, terminal_growth=terminal)
    return {
        "ticker": result.ticker, "intrinsic_value": result.intrinsic_value,
        "current_price": result.current_price, "upside_pct": result.upside_pct,
        "wacc": result.wacc, "growth_5y": result.growth_rate_5y,
        "terminal_growth": result.terminal_growth, "fcf": result.free_cash_flow,
        "confidence": result.confidence,
    }


@app.get("/api/valuation/dd")
async def valuation_dd(ticker: str):
    from src.data.valuation_tools import ValuationTools
    items = ValuationTools().generate_dd_checklist(ticker.upper())
    return [{"category": i.category, "question": i.question, "status": i.status, "evidence": i.evidence} for i in items]


# ═══════════════════════════════════════════════════════
# 股票自选 Watchlist API
# ═══════════════════════════════════════════════════════

@app.get("/api/watchlist")
async def get_watchlist(request: Request):
    from src.admin.auth import get_current_user
    from src.multi_tenant.config import PerUserConfig
    user = get_current_user(request)
    tenant_id = str(user.id) if user else "default"
    cfg = PerUserConfig(tenant_id)
    return cfg.load().get("watchlist", [])


@app.post("/api/watchlist/add")
async def add_watchlist(request: Request, payload: dict):
    ticker = str(payload.get("ticker") or "").strip().upper()
    if not ticker: return {"ok": False, "error": "请输入股票代码"}
    from src.admin.auth import get_current_user
    from src.multi_tenant.config import PerUserConfig
    user = get_current_user(request)
    tenant_id = str(user.id) if user else "default"
    cfg = PerUserConfig(tenant_id)
    config = cfg.load()
    wl = config.setdefault("watchlist", [])
    if ticker not in wl: wl.append(ticker)
    cfg.save_section("watchlist", wl)
    return {"ok": True, "watchlist": wl}


@app.post("/api/watchlist/remove")
async def remove_watchlist(request: Request, payload: dict):
    ticker = str(payload.get("ticker") or "").strip().upper()
    from src.admin.auth import get_current_user
    from src.multi_tenant.config import PerUserConfig
    user = get_current_user(request)
    tenant_id = str(user.id) if user else "default"
    cfg = PerUserConfig(tenant_id)
    config = cfg.load()
    wl = config.get("watchlist", [])
    if ticker in wl: wl.remove(ticker)
    cfg.save_section("watchlist", wl)
    return {"ok": True, "watchlist": wl}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
