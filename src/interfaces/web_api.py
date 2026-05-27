"""FastAPI Web API。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from src.ai.chat_engine import ChatEngine
from src.storage.database import db
from src.storage.models import PipelineTask

# 单例 ChatEngine，避免每次请求重建
_chat_engine: ChatEngine | None = None


def _get_chat_engine() -> ChatEngine:
    global _chat_engine
    if _chat_engine is None:
        _chat_engine = ChatEngine()
    return _chat_engine

app = FastAPI(title="Twitter 用户蒸馏 AI 助手")

from src.config import config  # noqa: E402
import time as _time  # noqa: E402
from fastapi import Request  # noqa: E402


# ── 简易中间件：限流 ──
import threading  # noqa: E402
_rate_buckets: dict[str, list[float]] = {}
_rate_lock = threading.Lock()


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # ── 速限中间件 ──────────────────────────────────────
    # TODO(prod): 正式上线前需重新设计限流策略:
    #   - 当前: 卡片查询跳过限流, 外部API阈值max(env,120)/min
    #   - 上线需考虑: 按端点分级(POST/chat限120/min, GET/本地不限)
    #   - 多用户场景: 按用户ID+API Key而非IP限流
    #   - 突发缓冲: 允许短暂burst(如5s内10次)而非均匀60s窗口
    #   - 监控面板: /metrics 端点暴露限流命中率
    #   - 参考: Stripe rate limiter, Cloudflare rate limiting docs
    # ─────────────────────────────────────────────────┘
    if request.method == "GET" and request.url.path.startswith("/cards/"):
        return await call_next(request)
    if request.url.path.startswith(("/timeline/", "/static/", "/favicon")):
        return await call_next(request)
    ip = request.client.host if request.client else "unknown"
    now = _time.time()
    with _rate_lock:
        bucket = _rate_buckets.setdefault(ip, [])
        bucket[:] = [t for t in bucket if now - t < 60]
        if len(bucket) >= max(config.rate_limit_per_minute, 120):
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=429, content={"error": "rate limit exceeded"})
        bucket.append(now)
    return await call_next(request)


class ChatRequest(BaseModel):
    question: str
    top_k: int = 5


class ChatResponse(BaseModel):
    answer: str



class ActiveJobResponse(BaseModel):
    active_job_id: int | None
    job: JobResponse | None


def serialize_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


import threading


@app.get("/pipeline/tasks")
def list_tasks(task_type: str | None = None, status: str | None = None, limit: int = 200, offset: int = 0) -> dict:
    session = db.get_session()
    try:
        q = session.query(PipelineTask)
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
            "running": is_running(),
            "progress": get_progress(),
        }
    finally:
        session.close()


@app.post("/pipeline/tasks/execute")
def execute_selected(payload: dict) -> dict:
    task_ids = payload.get("task_ids", [])
    if not task_ids:
        return {"ok": False, "message": "未选择任务"}
    if is_running():
        return {"ok": False, "message": "已有任务在执行中"}
    # 兼容前端传字符串 ID，安全转换
    try:
        task_ids = [int(x) for x in task_ids]
    except (ValueError, TypeError):
        return {"ok": False, "message": "非法任务ID"}
    session = db.get_session()
    try:
        valid_ids = session.query(PipelineTask.id).filter(
            PipelineTask.id.in_(task_ids), PipelineTask.status == "pending"
        ).all()
        ids = [v[0] for v in valid_ids]
    finally:
        session.close()
    if not ids:
        return {"ok": False, "message": "没有可执行的待办任务"}
    threading.Thread(target=execute_tasks, args=(ids,), daemon=True).start()
    return {"ok": True, "message": f"已启动 {len(ids)} 个任务", "count": len(ids)}


@app.post("/pipeline/tasks/{task_id}/skip")
def skip_task(task_id: int) -> dict:
    """标记任务为跳过（人工审核后决定忽略）。"""
    session = db.get_session()
    try:
        t = session.query(PipelineTask).get(task_id)
        if not t:
            return {"ok": False, "message": "任务不存在"}
        old_ticker = json.loads(t.payload).get("ticker", "")
        t.status = "skipped"
        t.error_msg = (t.error_msg or "") + " [人工跳过]"
        # CSV 写入放在 DB 提交之前，保证一致性
        if old_ticker:
            _save_alias(old_ticker, "", "人工跳过")
        session.commit()
        return {"ok": True}
    finally:
        session.close()


@app.post("/pipeline/tasks/{task_id}/retry")
def retry_task(task_id: int) -> dict:
    """重置失败任务为待办。"""
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
    """编辑任务并记忆映射。"""
    session = db.get_session()
    try:
        t = session.query(PipelineTask).get(task_id)
        if not t:
            return {"ok": False, "message": "任务不存在"}
        old_ticker = json.loads(t.payload).get("ticker", "")
        new_ticker = payload.get("ticker", "").strip().upper()
        if not new_ticker:
            return {"ok": False, "message": "ticker 不能为空"}
        t.payload = json.dumps({"ticker": new_ticker, "sources": json.loads(t.payload).get("sources", [])})
        t.status = "pending"
        t.error_msg = None
        session.commit()
        _save_alias(old_ticker, new_ticker, "人工修正")
        return {"ok": True, "message": f"已更新为 {new_ticker}"}
    finally:
        session.close()


def _save_alias(from_name: str, to_ticker: str, note: str = "") -> None:
    """将别名映射追加到 stock_alias.csv（去重）。"""
    alias_path = Path("data/stock_alias.csv")
    lines = alias_path.read_text(encoding="utf-8").split("\n") if alias_path.exists() else []
    norm = from_name.strip()
    for line in lines:
        if line.strip() and line.split(",")[0].strip().lower() == norm.lower():
            return  # 已存在
    with open(alias_path, "a", encoding="utf-8") as f:
        f.write(f"\n{norm},{to_ticker},{note}")


@app.get("/pipeline/tasks/fetched")
def list_fetched_tickers() -> dict:
    """返回已有股价数据的 ticker 列表。"""
    pp = Path("data/prices.json")
    if pp.exists():
        tickers = sorted(json.loads(pp.read_text(encoding="utf-8")).keys())
        return {"tickers": tickers, "count": len(tickers)}
    return {"tickers": [], "count": 0}


@app.get("/pipeline/tasks/crypto_fetched")
def list_crypto_fetched() -> dict:
    """返回已有加密货币行情的列表。"""
    pp = Path("data/crypto_prices.json")
    if pp.exists():
        tickers = sorted(json.loads(pp.read_text(encoding="utf-8")).keys())
        return {"tickers": tickers, "count": len(tickers)}
    return {"tickers": [], "count": 0}


@app.post("/pipeline/filter")
def run_filter() -> dict:
    """运行过滤：扫描 DB 新推文 → 过滤模型 → 写入 filtered JSON。"""
    t = PipelineTask(task_type="filter", status="pending", payload=json.dumps({"action": "filter_new"}, ensure_ascii=False))
    session = db.get_session()
    session.add(t)
    session.commit()
    tid = t.id
    session.close()
    threading.Thread(target=execute_tasks, args=([tid],), daemon=True).start()
    return {"ok": True, "message": "过滤已启动"}


def _load_skip_set() -> set[str]:
    """从别名表读取已跳过/已修正的条目。"""
    skip = set()
    ap = Path("data/stock_alias.csv")
    if ap.exists():
        for line in ap.read_text(encoding="utf-8").split("\n"):
            parts = line.strip().split(",")
            if len(parts) >= 2:
                alias = parts[0].strip()
                target = parts[1].strip()
                if alias and not target:  # 跳过类：空目标
                    skip.add(alias.upper())
                elif alias and target:  # 修正类：用修正后的名字
                    skip.add(alias.upper())
    return skip


def _is_known_stock_ticker(ticker: str) -> bool:
    """判断 crypto_details 中的项是否实际是已知股票代码。"""
    import re as _re
    if not _re.match(r"^[A-Z]{1,5}$", ticker):
        return False
    ap = Path("data/stock_alias.csv")
    if not ap.exists():
        return False
    for line in ap.read_text(encoding="utf-8").split("\n"):
        parts = [x.strip() for x in line.strip().split(",")]
        if len(parts) >= 2 and parts[0].upper() == ticker.upper():
            return bool(parts[1])  # 有目标 = 已知股票
    return False


@app.post("/pipeline/tasks/seed")
def seed_tasks() -> dict:
    """扫描未处理项，写入任务表。"""
    session = db.get_session()
    count = 0
    try:
        # 辅助：从文件名提取用户+月份
        def _parse_stem(stem: str) -> tuple[str, str]:
            import re as _re
            m = _re.match(r"(.+?)_(\d{4}-\d{2})_.*", stem)
            if m:
                return m.group(1), m.group(2)
            parts = stem.split("_")
            if len(parts) >= 2:
                return parts[0], "_".join(parts[1:])
            return stem, ""

        # ── 清旧待办 ──
        session.query(PipelineTask).filter(
            PipelineTask.task_type == "analyze", PipelineTask.status == "pending"
        ).delete()

        # ── 收集已有分析任务的 tweet_id（避免 Like 查询）──
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
            # 收集该用户所有月份已分析的 tweet_id（不限于当前文件月份）
            done_ids = set()
            for ap in Path("data/pipeline").glob(f"{username}_*_analyzed.json"):
                if "_cleaned" in ap.name:
                    continue
                for r in json.loads(ap.read_text(encoding="utf-8")):
                    done_ids.add(r.get("tweet_id"))
            for tweet in data:
                if not tweet.get("is_investment_related") or tweet["id"] in done_ids or tweet["id"] in existing_tweet_ids:
                    continue
                t = PipelineTask(task_type="analyze", status="pending", payload=json.dumps({
                    "username": username, "tweet_id": tweet["id"], "text": tweet["text"],
                    "created_at": tweet.get("created_at", ""),
                    "tweet_id_str": tweet.get("tweet_id", ""),
                    "is_reply": tweet.get("is_reply", False),
                    "is_quote": tweet.get("is_quote", False),
                    "replied_to_user": tweet.get("replied_to_user", ""),
                    "quoted_user": tweet.get("quoted_user", ""),
                }, ensure_ascii=False))
                session.add(t)
                count += 1

        # ── 拉取股价（从清洗后数据提取已验证股票）──
        price_path = Path("data/prices.json")
        existing_prices = set()
        if price_path.exists():
            existing_prices = set(json.loads(price_path.read_text(encoding="utf-8")).keys())

        # 加载已跳过/修正的别名（种子时不生成这些）
        skip_set = _load_skip_set()

        # 清除旧的未执行股价任务
        session.query(PipelineTask).filter(
            PipelineTask.task_type == "fetch_price", PipelineTask.status == "pending"
        ).delete()

        # 收集每个 ticker 的来源推文（最多 3 条）
        all_stocks = {}  # ticker → [{username, text, date}]
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
            t = PipelineTask(task_type="fetch_price", status="pending", payload=json.dumps({
                "ticker": ticker,
                "sources": all_stocks[ticker],
            }, ensure_ascii=False))
            session.add(t)
            count += 1

        # ── 加密货币行情 ──
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
                                "user": username, "text": r.get("text", "")[:100],
                                "date": r.get("created_at", "")[:10],
                                "url": f"https://x.com/{username}/status/{r.get('twitter_id', '')}",
                            })
        for ticker in sorted(all_cryptos):
            if ticker in skip_set:
                continue
            if _is_known_stock_ticker(ticker):
                continue
            t = PipelineTask(task_type="fetch_crypto", status="pending", payload=json.dumps({
                "ticker": ticker, "sources": all_cryptos[ticker],
            }, ensure_ascii=False))
            session.add(t)
            count += 1

        # ── 画像生成（每用户 × 5 个时间窗口）──
        from datetime import datetime, timedelta
        import re as _re
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
                cutoff = now - timedelta(days=days) if days < 9999 else datetime(2000, 1, 1)
                count = sum(1 for t in tweets if t.get("created_at", "") and t["created_at"][:10] >= cutoff.strftime("%Y-%m-%d"))
                tag = f"{username}_{label}"
                existing = session.query(PipelineTask).filter(
                    PipelineTask.task_type == "portrait",
                    PipelineTask.payload.contains(f'"username": "{tag}"'),
                ).first()
                if existing:
                    continue
                t = PipelineTask(task_type="portrait", status="pending", payload=json.dumps({
                    "username": tag, "label": label, "window_days": days,
                    "tweet_count": count,
                }, ensure_ascii=False))
                session.add(t)
                count += 1

        session.commit()
        return {"ok": True, "message": f"已创建 {count} 个待办任务"}
    finally:
        session.close()


# ══════ 卡片模块化 API ══════

from src.cards import CARDS, get_card  # noqa: E402
import time as _time  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402

# 服务端缓存：{name: (html, expire_ts)}
_card_cache: dict[str, tuple[str, float]] = {}
_CACHE_TTL = 2  # 秒


def _get_cached_card_html(name: str) -> str | None:
    now = _time.time()
    if name in _card_cache:
        html, expire = _card_cache[name]
        if now < expire:
            return html
    return None


def _set_cached_card_html(name: str, html: str) -> None:
    _card_cache[name] = (html, _time.time() + _CACHE_TTL)


@app.get("/cards/meta")
async def cards_meta():
    """返回所有已注册卡片元数据。"""
    return [c.to_dict() for c in CARDS]


@app.get("/cards/{name}")
async def card_data(name: str):
    """返回单个卡片渲染后的 HTML 片段（2秒服务端缓存）。"""
    cached = _get_cached_card_html(name)
    if cached is not None:
        return HTMLResponse(content=cached)

    card = get_card(name)
    if card is None:
        raise HTTPException(status_code=404, detail=f"Card '{name}' not found")
    try:
        data = card.get_data()
        html = card.render(data)
        _set_cached_card_html(name, html)
        return HTMLResponse(content=html)
    except Exception as e:
        return HTMLResponse(content=f'<div class="card"><div class="flex"><div class="status-dot err"></div><span class="text-secondary">{name}: {str(e).replace("<","&lt;").replace(">","&gt;")}</span></div></div>')


@app.post("/cards/{name}/action")
async def card_action(name: str, payload: dict = None):
    """处理卡片交互动作（如 daemon toggle）。"""
    if name == "daemon" and payload and payload.get("action") == "toggle":
        try:
            import subprocess, sys
            from src.cards import get_card
            card = get_card("daemon")
            proc = getattr(card, "_proc", None)
            if proc and proc.poll() is None:
                proc.terminate()
                card._proc = None
            else:
                proc = subprocess.Popen(
                    [sys.executable, "scripts/daemon_worker.py"]
                )
                card._proc = proc
            _card_cache.pop("daemon", None)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    if name == "telegram" and payload:
        try:
            import json as _json
            from pathlib import Path as _Path
            token = payload.get("token", "")
            chat_id = payload.get("chat_id", "")
            _Path("data/telegram_config.json").write_text(_json.dumps({
                "bot_token": token,
                "chat_id": chat_id
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            _card_cache.pop("telegram", None)
            # 如果是测试消息
            if payload.get("action") == "test":
                import requests as _req
                _req.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat_id, "text": "✅ Twitter Investor Distiller 测试消息成功！"})
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    if name == "role_picker" and payload:
        try:
            result = _handle_role_picker(payload)
            return {"ok": True, "html": result}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    if name == "portfolio" and payload:
        try:
            result = _handle_portfolio_analysis(payload)
            return {"ok": True, "html": result}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    if name == "fetch_control" and payload:
        try:
            result = _handle_fetch_control(payload)
            return {'ok': True, 'total': result.get('total_new', 0)}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    if name == "pipeline_execute" and payload:
        return _handle_pipeline_action(payload)
    if name == "script_runner" and payload:
        return _handle_script_run(payload)
    if name == "portrait_generate" and payload:
        return _handle_portrait_generate(payload)
    if name == "asset_alias" and payload:
        return _handle_asset_alias(payload)
    if name == "api_status" and payload and payload.get("action") in ("add_user", "remove_user"):
        return _handle_user_manage(payload)
    return {"ok": False, "error": "unknown action"}



from src.interfaces.handlers_insights import _handle_role_picker, _handle_portfolio_analysis
from src.interfaces.handlers_exec import _handle_fetch_control, _handle_pipeline_action, _handle_script_run
from src.interfaces.handlers_data import _handle_asset_alias, _handle_portrait_generate, _handle_user_manage

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """服务模块化仪表盘主页。"""
    from src.cards.base import TEMPLATE_DIR
    base = TEMPLATE_DIR / "base.html"
    return HTMLResponse(
        content=base.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )


@app.get("/timeline/{path:path}", response_class=HTMLResponse)
async def serve_timeline(path: str):
    """服务 timeline 图表 HTML 文件。"""
    import os as _os
    fp = (Path("data/timeline") / path).resolve()
    allowed = Path("data/timeline").resolve()
    if not str(fp).startswith(str(allowed)):
        raise HTTPException(status_code=403, detail="forbidden")
    if fp.exists() and fp.suffix == ".html":
        return HTMLResponse(content=fp.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404, detail="not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
