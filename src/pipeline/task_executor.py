"""流水线任务执行器 —— 单线程顺序执行，通过数据库同步状态。"""
from __future__ import annotations

import csv
import json
import re
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

from src.storage.database import db
from src.storage.models import PipelineTask


_executor_lock = threading.Lock()
_current_task_id: int | None = None

# 模块级 alias 缓存（避免每个任务重复读 CSV）
_alias_cache: dict[str, str] | None = None


def _load_alias() -> dict[str, str]:
    global _alias_cache
    if _alias_cache is not None:
        return _alias_cache
    _alias_cache = {}
    alias_path = Path("data/stock_alias.csv")
    if alias_path.exists():
        with open(alias_path, encoding="utf-8") as f:
            for row in csv.reader(f):
                if row and not row[0].startswith("#") and len(row) >= 2 and row[0].strip() and row[1].strip():
                    _alias_cache[row[0].strip()] = row[1].strip()
    return _alias_cache


def _clean_analysis() -> dict:
    """数据清洗：用 stock_alias.csv 校准已分析推文中的股票别名。"""
    import re as _re
    alias = _load_alias()
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


_progress: dict = {"total": 0, "done": 0, "msg": ""}


def get_progress() -> dict:
    return dict(_progress)


def is_running() -> bool:
    return _current_task_id is not None


def execute_tasks(task_ids: list[int]) -> None:
    """后台线程入口：指定 ID 顺序执行。"""
    global _current_task_id

    if not _executor_lock.acquire(blocking=False):
        return  # 已有任务在执行

    try:
        session = db.get_session()
        tasks = session.query(PipelineTask).filter(PipelineTask.id.in_(task_ids)).all()
        pending = [t for t in tasks if t.status == "pending"]
        session.close()

        if not pending:
            return

        _progress["total"] = len(pending)
        _progress["done"] = 0
        _progress["msg"] = "准备执行..."

        for i, task in enumerate(pending):
            _current_task_id = task.id
            session = db.get_session()
            try:
                t = session.query(PipelineTask).get(task.id)
                t.status = "running"
                session.commit()
                _progress["done"] = i
                _progress["msg"] = f"执行 {t.task_type} #{t.id}..."

                payload = json.loads(t.payload)
                if t.task_type == "filter":
                    result = _filter_tweets(payload)
                elif t.task_type == "fetch_price":
                    result = _fetch_price(payload["ticker"])
                elif t.task_type == "fetch_crypto":
                    result = _fetch_crypto(payload["ticker"])
                elif t.task_type == "analyze":
                    result = _analyze_tweet(payload)
                elif t.task_type == "portrait":
                    result = _generate_portrait(payload["username"])
                elif t.task_type == "clean":
                    result = _clean_analysis()
                else:
                    result = {"error": f"未知任务类型: {t.task_type}"}

                t.result = json.dumps(result, ensure_ascii=False)
                t.status = "done" if "error" not in result else "failed"
                t.error_msg = result.get("error")
                t.updated_at = None
                session.commit()
            except Exception as exc:
                t.status = "failed"
                t.error_msg = str(exc)[:500]
                session.commit()
            finally:
                session.close()
                time.sleep(0.3)  # 让出 CPU

        _progress["done"] = len(pending)
        _progress["msg"] = "全部完成"
        _current_task_id = None
    finally:
        _executor_lock.release()


# ── 具体执行逻辑 ──

import yaml as _yaml
with open(Path(__file__).parent.parent.parent / "config" / "pipeline.yaml", encoding="utf-8") as _f:
    _PIPELINE_CFG = _yaml.safe_load(_f) or {}
POLYGON_KEY = _PIPELINE_CFG.get("api", {}).get("polygon_key", "")
PRICES_PATH = Path("data/prices.json")
CRYPTO_PRICES_PATH = Path("data/crypto_prices.json")


def _fetch_price(ticker: str) -> dict:
    return _fetch_polygon(ticker, PRICES_PATH)


def _fetch_crypto(ticker: str) -> dict:
    """拉取加密货币行情（Polygon X: 前缀）。"""
    return _fetch_polygon(f"X:{ticker}USD", CRYPTO_PRICES_PATH)


def _fetch_polygon(ticker: str, store_path: Path) -> dict:
    from datetime import date
    from_date = _PIPELINE_CFG.get("api", {}).get("polygon_from_date", "2015-01-01")
    to_date = date.today().strftime("%Y-%m-%d")
    url = (f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/"
           f"{from_date}/{to_date}?apiKey={POLYGON_KEY}&limit=5000")
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
            if resp.get("resultsCount", 0) > 0:
                prices = {}
                if store_path.exists():
                    prices = json.loads(store_path.read_text(encoding="utf-8"))
                prices[ticker] = resp
                store_path.write_text(json.dumps(prices, ensure_ascii=False), encoding="utf-8")
                return {"ok": True, "bars": resp["resultsCount"]}
            return {"error": "无数据"}
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(15)
                continue
            return {"error": f"HTTP {e.code}"}
        except Exception as e:
            return {"error": str(e)}
    return {"error": "重试失败"}


def _analyze_tweet(payload: dict) -> dict:
    """分析单条推文。payload: {username, tweet_id, text, created_at, ...}"""
    from collections import Counter
    import csv, re

    from src.ai.llm_client import chat_vision
    from src.storage.models import Media

    session = db.get_session()
    img_paths = []
    try:
        for m in session.query(Media).filter(
            Media.tweet_id == payload.get("tweet_id"), Media.downloaded == True
        ).all():
            if m.local_path:
                img_paths.append(m.local_path)
    finally:
        session.close()

    alias = _load_alias()

    PROMPT = (
        '分析推文,仅输出JSON: {"topic":"个股分析|行业研判|宏观分析|加密货币|操作记录|投资策略|信息分享|招聘/人脉|其他",'
        '"mentioned_stocks":[],"mentioned_crypto":[],"mentioned_sectors":[],'
        '"stance":"看多|看空|中性|观望|无明确方向","confidence":"high|medium|low",'
        '"reasoning_chain":"","action_hint":"买入|卖出|持有|加仓|减仓|观望|无",'
        '"key_quote":"","image_analysis":null}\n\n'
    )
    ctx = [payload.get("text", "")]
    if payload.get("is_reply"):
        ctx.append(f"回复 @{payload.get('replied_to_user', '?')}")
    if payload.get("is_quote"):
        ctx.append(f"引用 @{payload.get('quoted_user', '?')}")
    ctx.append(f"时间: {payload.get('created_at', '?')}")
    prompt = PROMPT + "\n".join(ctx)

    for retry in range(3):
        try:
            resp = chat_vision(text_prompt=prompt, image_paths=img_paths[:3], role="analyzer")
            clean = resp.strip().lstrip("```json").rstrip("```").strip()
            result = json.loads(clean)
            # normalize stocks
            stocks = result.get("mentioned_stocks", [])
            norm = []
            for s in stocks:
                s = str(s).strip().lstrip("$")
                if s in alias:
                    if alias[s]:
                        norm.append(alias[s])
                elif re.match(r"^[A-Za-z0-9.]+$", s):
                    norm.append(s.upper())
                else:
                    norm.append(s)
            result["mentioned_stocks"] = list(dict.fromkeys(norm))
            result["tweet_id"] = payload.get("tweet_id")
            result["twitter_id"] = payload.get("tweet_id_str", "")
            result["text"] = payload.get("text", "")
            result["created_at"] = payload.get("created_at", "")
            _save_analyzed(payload.get("username", ""), result)
            time.sleep(20)
            return {"ok": True}
        except (json.JSONDecodeError, ConnectionError, OSError) as exc:
            if retry < 2:
                time.sleep(5)
                continue
            return {"error": f"API 失败: {exc}"}
    return {"error": "重试失败"}


def _save_analyzed(username: str, result: dict) -> None:
    # 根据 tweet 日期决定存入哪个月份文件
    created = result.get("created_at", "")
    month = created[:7] if created else "unknown"
    fp = Path(f"data/pipeline/{username}_{month}_analyzed.json")
    existing = []
    if fp.exists():
        existing = json.loads(fp.read_text(encoding="utf-8"))
    ids = {r["tweet_id"] for r in existing if "tweet_id" in r}
    if result.get("tweet_id") not in ids:
        existing.append(result)
        fp.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def _generate_portrait(username: str) -> dict:
    from src.ai.llm_client import chat
    from datetime import datetime, timedelta

    # 解析组合名：
    # 格式A: TJ_Research_1个月 → user=TJ_Research, window=30
    # 格式B: TJ_Research_2026-01-01_2026-05-27 → user=TJ_Research, 日期范围
    m = re.match(r"(.+)_(1个月|3个月|6个月|1年|全量)$", username)
    use_date_range = False
    date_from = date_to = ""
    if m:
        user = m.group(1)
        window_label = m.group(2)
        window_map = {"1个月": 30, "3个月": 90, "6个月": 180, "1年": 365, "全量": 9999}
        window_days = window_map.get(window_label, 9999)
    else:
        # 尝试解析日期范围: user_YYYY-MM-DD_YYYY-MM-DD
        m2 = re.match(r"(.+?)_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})", username)
        if m2:
            user = m2.group(1)
            date_from = m2.group(2)
            date_to = m2.group(3)
            window_label = f"{date_from} ~ {date_to}"
            window_days = 9999
            use_date_range = True
        else:
            return {"error": f"无法解析用户名+窗口: {username}"}

    # 加载该用户所有已清洗分析数据
    data = []
    for fp in Path("data/pipeline").glob(f"{user}_*_analyzed_cleaned.json"):
        data.extend(json.loads(fp.read_text(encoding="utf-8")))
    if not data:
        return {"error": "无分析数据"}

    # 时间窗口过滤
    if use_date_range:
        windowed = [r for r in data if r.get("created_at", "") and date_from <= r["created_at"][:10] <= date_to]
    else:
        now = datetime.utcnow()
        cutoff = now - timedelta(days=window_days) if window_days < 9999 else datetime(2000, 1, 1)
        windowed = [r for r in data if r.get("created_at", "") and r["created_at"][:10] >= cutoff.strftime("%Y-%m-%d")]
    if not windowed:
        return {"error": f"时间窗口 {window_label} 内无推文" if not use_date_range else f"日期范围 {date_from}~{date_to} 内无推文"}
    data = windowed

    # 统计摘要（用清洗后的 stock_details）
    from collections import Counter
    topics = Counter(r.get("topic", "?") for r in data)
    stances = Counter(r.get("stance", "?") for r in data)
    stocks = Counter()
    for r in data:
        for sd in r.get("stock_details", []):
            stocks[sd.get("ticker", "?")] += 1
    times = sorted(r["created_at"][:10] for r in data if r.get("created_at"))

    prompt = f"""你是投资分析师。基于 {len(data)} 条 {user} 的推文分析结果，生成投资风格画像。

时间窗口: {window_label} ({times[0]} ~ {times[-1]})
话题: {dict(topics.most_common())}
态度: 看多{stances.get('看多',0)} 看空{stances.get('看空',0)} 观望{stances.get('观望',0)}
重仓股: {dict(stocks.most_common(15))}

输出格式:
### 1. 投资哲学（200字）
### 2. 核心板块
### 3. 操作风格
### 4. 仓位管理与Beta调节（重点分析：净仓位暴露范围、现金比例、降beta的触发条件、降beta时会切换到哪些防御板块或现金等价物、加仓/减仓的节奏和信号）
### 5. 风险偏好
### 6. 决策框架
### 7. 情绪特征
### 8. 预测准确率（对照股价）
### 9. 进化轨迹
### 10. 一句话总结"""

    report = chat(messages=[{"role": "user", "content": prompt}], role="analyzer", max_tokens=8192, temperature=0.5)
    # 在输出文件头部写入元数据
    meta = f"""---
user: {user}
window: {window_label}
tweets: {len(data)}
date_range: {times[0]} ~ {times[-1]}
generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
---
"""
    out = Path(f"data/pipeline/{username}_portrait.md")
    out.write_text(meta + report, encoding="utf-8")
    return {"ok": True, "path": str(out), "window": window_label, "tweets": len(data)}


def _filter_tweets(payload: dict) -> dict:
    """过滤新入库推文：从 DB 扫描 → 过滤模型 → 写入 filtered JSON。"""
    from src.storage.database import db
    from src.storage.models import Tweet, User
    from src.ai.llm_client import chat

    FILTER_PROMPT = """你是一个推文过滤器。判断每条推文是否与投资/金融/市场相关。
相关话题：股票、加密货币、期权、期货、宏观分析、行业分析、投资策略、仓位管理、公司基本面、财报、估值、技术分析、交易心理、市场情绪。
无关话题：日常生活、闲聊、娱乐、纯政治、纯表情、纯转发无评论。
输入是一批推文（JSON 数组），每条有 id 和 text。
输出严格 JSON 数组，每项格式：{"id": <tweet_id>, "is_investment_related": true/false}
只输出 JSON，不要解释。"""

    session = db.get_session()
    try:
        # 收集已过滤的 tweet ID
        done_ids = set()
        for fp in Path("data/pipeline").glob("*_filtered.json"):
            for t in json.loads(fp.read_text(encoding="utf-8")):
                done_ids.add(t.get("tweet_id"))
                done_ids.add(t.get("id"))

        users = session.query(User).all()
        total_new = 0
        BATCH = 20

        for u in users:
            tweets = session.query(Tweet).filter(Tweet.user_id == u.id).order_by(Tweet.id).all()
            # 找未过滤的
            new = []
            for t in tweets:
                if t.id not in done_ids and t.tweet_id not in done_ids and t.text:
                    new.append({
                        "id": t.id, "tweet_id": t.tweet_id,
                        "text": t.text or "", "created_at": t.created_at_twitter.isoformat(),
                        "is_reply": t.is_reply or False, "is_quote": t.is_quote or False,
                        "replied_to_user": t.replied_to_user, "quoted_user": t.quoted_user,
                        "quoted_text": t.quoted_text, "has_media": t.has_media or False,
                    })

            if not new:
                continue

            # 分批过滤
            results = []
            for i in range(0, len(new), BATCH):
                batch = new[i:i + BATCH]
                resp = chat(messages=[
                    {"role": "system", "content": FILTER_PROMPT},
                    {"role": "user", "content": json.dumps(batch, ensure_ascii=False)},
                ], role="filter", max_tokens=2048)
                resp = resp.strip().lstrip("```json").rstrip("```").strip()
                try:
                    results.extend(json.loads(resp))
                except json.JSONDecodeError:
                    continue

            filter_map = {r["id"]: r["is_investment_related"] for r in results}
            for t in new:
                t["is_investment_related"] = filter_map.get(t["id"], False)

            # 按推文实际月份分组写入
            from collections import defaultdict
            monthly: dict[str, list[dict]] = defaultdict(list)
            for t in new:
                month_tag = t["created_at"][:7] if t.get("created_at") else "unknown"
                monthly[month_tag].append(t)

            for month_tag, month_tweets in monthly.items():
                tag = f"{u.username}_{month_tag}"
                out_path = Path(f"data/pipeline/{tag}_filtered.json")
                existing = []
                if out_path.exists():
                    existing = json.loads(out_path.read_text(encoding="utf-8"))
                existing_ids = {t["id"] for t in existing}
                for t in month_tweets:
                    if t["id"] not in existing_ids:
                        existing.append(t)
                out_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
                related = sum(1 for t in month_tweets if t.get("is_investment_related"))
                total_new += len(month_tweets)

        session.close()
        return {"ok": True, "new_filtered": total_new, "message": f"已过滤 {total_new} 条新推文"}
    finally:
        session.close()
