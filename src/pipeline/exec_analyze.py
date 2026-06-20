"""LLM 推文分析任务。

从 task_executor.py 抽出。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from src.pipeline.task_executor import _PIPELINE_CFG

# 模块级缓存：避免每次 analyze 都全量读 prices/fundamentals JSON
# task_executor.execute_tasks 结束后会清空缓存
_prices_cache: dict = {"data": {}, "ts": 0.0}
_fundamentals_cache: dict = {"data": {}, "ts": 0.0}
_CACHE_TTL = 60  # 秒


def _enrich_price_context(stocks: list[str], created_at: str) -> list[dict]:
    prices_path = Path("data/prices.json")
    now = time.time()
    if now - _prices_cache["ts"] > _CACHE_TTL and prices_path.exists():
        _prices_cache["data"] = json.loads(prices_path.read_text(encoding="utf-8"))
        _prices_cache["ts"] = now
    prices = _prices_cache["data"]

    fundamentals_path = Path("data/fundamentals.json")
    if now - _fundamentals_cache["ts"] > _CACHE_TTL and fundamentals_path.exists():
        _fundamentals_cache["data"] = json.loads(fundamentals_path.read_text(encoding="utf-8"))
        _fundamentals_cache["ts"] = now
    fundamentals = _fundamentals_cache["data"]
    enriched = []
    for s in stocks:
        ctx = {"ticker": s, "backward_available": False, "price_at_tweet": None,
               "price_change_30d": None, "current_price": None,
               "fundamentals": fundamentals.get(s, {})}
        if s in prices:
            bars = prices[s].get("results", [])
            ctx["current_price"] = bars[-1]["c"] if bars else None
            tweet_date = created_at[:10] if created_at else ""
            if tweet_date and bars:
                for i, b in enumerate(bars):
                    ts = b.get("t", "")
                    bar_date = (str(ts)[:10] if isinstance(ts, int) and ts > 10000000000
                                else str(ts)[:10]) if ts else ""
                    if bar_date and bar_date == tweet_date:
                        ctx["price_at_tweet"] = b["c"]
                        ctx["backward_available"] = (i + 30) < len(bars)
                        if i + 30 < len(bars):
                            ctx["price_change_30d"] = round(
                                (bars[i + 30]["c"] - b["c"]) / b["c"] * 100, 1)
                        break
        enriched.append(ctx)
    return enriched


def _save_analyzed(username: str, result: dict) -> None:
    from datetime import datetime
    month = result.get("created_at", datetime.utcnow().strftime("%Y-%m-%d"))[:7]
    fp = Path(f"data/pipeline/{username}_{month}_analyzed.json")
    data = []
    if fp.exists():
        data = json.loads(fp.read_text(encoding="utf-8"))
    data.append(result)
    fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _analyze_tweet(payload: dict) -> dict:
    from src.ai.chat_engine import chat_engine_factory
    text = payload.get("text", "")
    username = payload.get("username", "")
    created_at = payload.get("created_at", "")
    is_reply = payload.get("is_reply", False)
    is_quote = payload.get("is_quote", False)
    base_url = _PIPELINE_CFG.get("api", {}).get("img_url", "")
    from src.crawler.twitterapi_fetcher import ImageFetcher
    media_text = ""
    try:
        imgs = ImageFetcher.get_tweet_media(payload.get("tweet_id_str", ""))
        if imgs:
            media_lines = []
            for mtype, murl in imgs[:3]:
                local_path = ImageFetcher.download(murl, base_url)
                if local_path:
                    media_lines.append(f"[图片]({local_path}) {mtype}")
                else:
                    media_lines.append(f"[图片]({murl}) {mtype}")
            if media_lines:
                media_text = "\n---\n### 推文相关媒体:\n" + "\n".join(media_lines)
    except Exception:
        pass
    all_stocks_text = ""
    try:
        stocks = payload.get("stock_details", [])
        if stocks:
            tickers = list(set(s["ticker"] for s in stocks if s.get("verified")))
            if tickers:
                enriched = _enrich_price_context(tickers, created_at)
                sub_lines = []
                for ec in enriched:
                    p = ec.get("current_price", "")
                    f = ec.get("fundamentals", {})
                    pe = f.get("pe_ratio", "-")
                    sub_lines.append(
                        f"- **{ec['ticker']}**: 当前价={p}, PE={pe}, "
                        f"发布时价={ec.get('price_at_tweet', '-')}, "
                        f"30天后变化={ec.get('price_change_30d', '-')}%"
                    )
                all_stocks_text = "\n---\n### 分析涉及的股票:\n" + "\n".join(sub_lines)
    except Exception:
        pass
    prompt = f"""你是一个专业的财经分析师。请分析下面的推文，提取投资信号。

推文作者: {username}
发布时间: {created_at}
{'（该推文是一条回复）' if is_reply else ''}{'（该推文是一条引用/转发）' if is_quote else ''}

---
### 推文内容:
{text}{media_text}{all_stocks_text}

请按以下 JSON 格式输出分析结果（只输出 JSON，不要用代码块）:
{{
    "topic": "话题（如：半导体/加密货币/宏观/行业/公司/其他...）",
    "stance": "看多/看空/中性",
    "confidence": 0-100,
    "targets": [{{"ticker": "股票代码/加密代码", "action": "买入/卖出/持有/关注", "description": "简要说明"}}],
    "reasoning": "分析推理过程（2-3句话）",
    "risks": ["风险1", "风险2"],
    "references": [],
    "signal_type": "事件驱动/趋势跟踪/价值发现/技术分析/其他"
}}"""
    engine = chat_engine_factory()
    for attempt in range(3):
        try:
            result = engine.query(prompt)
            if result:
                result.update({"tweet_id": payload.get("tweet_id"), "username": username,
                               "text": text, "created_at": created_at,
                               "origin_payload": payload})
                _save_analyzed(username, result)
                return {"ok": True, "tweet_id": payload.get("tweet_id")}
        except Exception:
            if attempt < 2:
                time.sleep(5)
                continue
            return {"error": "分析失败"}
    return {"error": "重试耗尽"}
