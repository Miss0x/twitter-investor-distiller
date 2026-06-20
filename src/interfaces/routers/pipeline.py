r"""流水线任务管理 API：/pipeline/{tasks, clean}。

从 web_api.py 抽出，路径与原 @app 完全一致。

依赖：
    - src.storage.database.db, src.storage.models.PipelineTask
    - src.pipeline.task_executor (execute_tasks, get_progress, is_running)
    - data/prices.json, data/crypto_prices.json, data/stock_alias.csv
    - data/pipeline/*.json (filtered, analyzed, cleaned)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter

from src.pipeline.task_executor import execute_tasks, get_progress, is_running
from src.storage.database import db
from src.storage.models import PipelineTask

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


# ── 辅助函数 ──

def _save_alias(from_name: str, to_ticker: str, note: str = "") -> None:
    """将别名映射追加到 stock_alias.csv（去重）。"""
    import csv as _csv  # noqa: PLC0415
    alias_path = Path("data/stock_alias.csv")
    norm = from_name.strip()
    if alias_path.exists():
        with open(alias_path, encoding="utf-8", newline="") as f:
            for row in _csv.reader(f):
                if row and row[0].strip().lower() == norm.lower():
                    return
    with open(alias_path, "a", encoding="utf-8", newline="") as f:
        _csv.writer(f).writerow([norm, to_ticker, note])


def _load_skip_set() -> set[str]:
    """从别名表读取已跳过/已修正的条目（防止种子时重复生成任务）。"""
    import csv as _csv  # noqa: PLC0415
    skip = set()
    ap = Path("data/stock_alias.csv")
    if ap.exists():
        with open(ap, encoding="utf-8", newline="") as f:
            for parts in _csv.reader(f):
                if len(parts) >= 2:
                    alias = parts[0].strip()
                    target = parts[1].strip()
                    if alias and not target:
                        skip.add(alias.upper())
                    elif alias and target:
                        skip.add(alias.upper())
    return skip


def _is_known_stock_ticker(ticker: str) -> bool:
    """判断 crypto_details 中的项是否实际是已知股票代码。"""
    if not re.match(r"^[A-Z]{1,5}$", ticker):
        return False
    ap = Path("data/stock_alias.csv")
    if not ap.exists():
        return False
    import csv as _csv  # noqa: PLC0415
    with open(ap, encoding="utf-8", newline="") as f:
        for parts in _csv.reader(f):
            if len(parts) >= 2 and parts[0].strip().upper() == ticker.upper():
                return bool(parts[1].strip())
    return False



# ── 路由 ──

@router.get("/tasks")
def list_tasks(task_type: str | None = None, status: str | None = None,
               limit: int = 200, offset: int = 0) -> dict:
    """列出流水线任务列表。"""
    session = db.get_session()
    try:
        q = session.query(PipelineTask)
        if task_type:
            q = q.filter(PipelineTask.task_type == task_type)
        if status:
            q = q.filter(PipelineTask.status == status)
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


@router.post("/tasks/execute")
def execute_selected(payload: dict) -> dict:
    """执行选中的待办任务。"""
    task_ids = payload.get("task_ids", [])
    if not task_ids:
        return {"ok": False, "message": "未选择任务"}
    if is_running():
        return {"ok": False, "message": "已有任务在执行中"}
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
    import threading  # noqa: PLC0415
    threading.Thread(target=execute_tasks, args=(ids,), daemon=True).start()
    return {"ok": True, "message": f"已启动 {len(ids)} 个任务", "count": len(ids)}


@router.post("/tasks/{task_id}/skip")
def skip_task(task_id: int) -> dict:
    """标记任务为跳过状态。"""
    session = db.get_session()
    try:
        t = session.query(PipelineTask).get(task_id)
        if not t:
            return {"ok": False, "message": "任务不存在"}
        old_ticker = json.loads(t.payload).get("ticker", "")
        t.status = "skipped"
        t.error_msg = (t.error_msg or "") + " [人工跳过]"
        if old_ticker:
            _save_alias(old_ticker, "", "人工跳过")
        session.commit()
        return {"ok": True}
    finally:
        session.close()


@router.post("/tasks/{task_id}/retry")
def retry_task(task_id: int) -> dict:
    """重置失败任务为待办状态。"""
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


@router.post("/tasks/{task_id}/edit")
def edit_task(task_id: int, payload: dict) -> dict:
    """编辑任务 ticker 并记忆映射。"""
    session = db.get_session()
    try:
        t = session.query(PipelineTask).get(task_id)
        if not t:
            return {"ok": False, "message": "任务不存在"}
        old_ticker = json.loads(t.payload).get("ticker", "")
        new_ticker = payload.get("ticker", "").strip().upper()
        if not new_ticker:
            return {"ok": False, "message": "ticker 不能为空"}
        t.payload = json.dumps({
            "ticker": new_ticker,
            "sources": json.loads(t.payload).get("sources", [])
        })
        t.status = "pending"
        t.error_msg = None
        session.commit()
        _save_alias(old_ticker, new_ticker, "人工修正")
        return {"ok": True, "message": f"已更新为 {new_ticker}"}
    finally:
        session.close()


@router.get("/tasks/fetched")
def list_fetched_tickers() -> dict:
    """返回已有股价数据的 ticker 列表。"""
    pp = Path("data/prices.json")
    if pp.exists():
        tickers = sorted(json.loads(pp.read_text(encoding="utf-8")).keys())
        return {"tickers": tickers, "count": len(tickers)}
    return {"tickers": [], "count": 0}


@router.get("/tasks/crypto_fetched")
def list_crypto_fetched() -> dict:
    """返回已有加密货币行情的列表。"""
    pp = Path("data/crypto_prices.json")
    if pp.exists():
        tickers = sorted(json.loads(pp.read_text(encoding="utf-8")).keys())
        return {"tickers": tickers, "count": len(tickers)}
    return {"tickers": [], "count": 0}


@router.post("/clean")
def run_clean() -> dict:
    """运行数据清洗：用 stock_alias.csv 校准已分析推文的股票别名。"""
    import csv as _csv  # noqa: PLC0415
    try:
        alias = {}
        afp = Path("data/stock_alias.csv")
        if afp.exists():
            with open(afp, encoding="utf-8") as f:
                for row in _csv.reader(f):
                    if row and not row[0].startswith("#") and len(row) >= 2 \
                       and row[0].strip() and row[1].strip():
                        alias[row[0].strip()] = row[1].strip()
        cleaned = 0
        for fp in sorted(Path("data/pipeline").glob("*_analyzed.json")):
            data = json.loads(fp.read_text(encoding="utf-8"))
            updated = False
            for item in data:
                stocks = item.get("mentioned_stocks", [])
                if stocks:
                    mapped = [alias.get(s.strip(), s.strip()) for s in stocks]
                    if mapped != stocks:
                        item["mentioned_stocks"] = mapped
                        item["_cleaned"] = True
                        updated = True
                        cleaned += 1
            if updated:
                fp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        return {"ok": True, "cleaned": cleaned}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/tasks/seed")
def seed_tasks() -> dict:
    """扫描未处理项，写入任务表（增量模式）。"""
    session = db.get_session()
    counts = {"filter": 0, "analyze": 0, "fetch_price": 0, "fetch_crypto": 0, "portrait": 0}
    type_names = {"filter": "筛选推文", "analyze": "分析观点",
                  "fetch_price": "补全行情", "fetch_crypto": "补全加密行情", "portrait": "生成画像"}
    try:
        def _parse_stem(stem: str) -> tuple[str, str]:
            m = re.match(r"(.+?)_(\d{4}-\d{2})_.*", stem)
            if m:
                return m.group(1), m.group(2)
            parts = stem.split("_")
            if len(parts) >= 2:
                return parts[0], "_".join(parts[1:])
            return stem, ""

        from src.storage.models import Tweet, User as DbUser  # noqa: PLC0415

        # 第一步: filter 任务
        filtered_ids: set[int] = set()
        for fp in Path("data/pipeline").glob("*_filtered.json"):
            for t in json.loads(fp.read_text(encoding="utf-8")):
                filtered_ids.add(t.get("tweet_id"))
                filtered_ids.add(t.get("id"))
        for t in session.query(PipelineTask).filter(PipelineTask.task_type == "filter").all():
            try:
                pid = json.loads(t.payload).get("tweet_id")
                if pid:
                    filtered_ids.add(pid)
            except (json.JSONDecodeError, TypeError):
                pass
        for u in session.query(DbUser).all():
            for tw in session.query(Tweet).filter(
                Tweet.user_id == u.id, Tweet.text.isnot(None), Tweet.text != ""
            ).order_by(Tweet.id).all():
                if tw.id not in filtered_ids and tw.tweet_id not in filtered_ids:
                    t = PipelineTask(task_type="filter", status="pending",
                                     payload=json.dumps({
                                         "action": "filter_single",
                                         "tweet_id": tw.id,
                                     }, ensure_ascii=False))
                    session.add(t)
                    counts["filter"] += 1

        # 第二步: analyze 任务
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
            done_ids = set()
            for ap in Path("data/pipeline").glob(f"{username}_*_analyzed.json"):
                if "_cleaned" in ap.name:
                    continue
                for r in json.loads(ap.read_text(encoding="utf-8")):
                    done_ids.add(r.get("tweet_id"))
            for tweet in data:
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

        # 第三步: fetch_price 任务
        price_path = Path("data/prices.json")
        existing_prices = set()
        if price_path.exists():
            existing_prices = set(json.loads(price_path.read_text(encoding="utf-8")).keys())
        skip_set = _load_skip_set()
        all_stocks: dict[str, list[dict]] = {}
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

        # 第四步: crypto 任务
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
            if _is_known_stock_ticker(ticker):
                continue
            t = PipelineTask(task_type="fetch_crypto", status="pending",
                             payload=json.dumps({
                                 "ticker": ticker,
                                 "sources": all_cryptos[ticker],
                             }, ensure_ascii=False))
            session.add(t)
            counts["fetch_crypto"] += 1

        # 第五步: portrait 任务
        from datetime import datetime, timedelta  # noqa: PLC0415

        windows = {"1个月": 30, "3个月": 90, "6个月": 180, "1年": 365, "全量": 9999}
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
                count = sum(1 for t in tweets
                           if t.get("created_at", "") and
                           t["created_at"][:10] >= cutoff.strftime("%Y-%m-%d"))
                tag = f"{username}_{label}"
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
        parts = [f"{v} 条{type_names.get(k, k)}" for k, v in counts.items() if v > 0]
        msg = "新增: " + ", ".join(parts) if parts else "无需新增任务"
        return {"ok": True, "message": msg, "counts": counts}
    except Exception as e:
        session.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        session.close()
