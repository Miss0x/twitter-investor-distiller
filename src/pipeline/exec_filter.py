"""LLM 推文过滤任务。

从 task_executor.py 抽出。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from src.pipeline.task_executor import _PIPELINE_CFG  # noqa: F401  # 保留供将来扩展


def _filter_tweets(payload: dict) -> dict:
    from src.ai.chat_engine import chat_engine_factory
    action = payload.get("action", "filter_single")
    if action == "filter_single":
        tweet_id = payload.get("tweet_id")
        from src.storage.database import db
        from src.storage.models import Tweet, User as DbUser
        db.init_db()
        session = db.get_session()
        try:
            tweet = session.query(Tweet).get(tweet_id)
            if not tweet:
                return {"error": "推文不存在"}
            user = session.query(DbUser).get(tweet.user_id)
            username = user.username if user else "unknown"
            text = tweet.text or ""
            created_at = str(tweet.created_at) if tweet.created_at else ""
        finally:
            session.close()
        prompt = f"""判断以下推文是否与投资/金融/市场相关。
如果相关，提取股票/加密货币信息。

推文作者: {username}
发布时间: {created_at}
推文内容: {text[:500]}

请用 JSON 格式回答（只输出 JSON）:
{{
    "is_investment_related": true/false,
    "confidence": 0-100,
    "reasoning": "一句话判断理由",
    "mentioned_stocks": [],
    "crypto_details": [],
    "stock_details": []
}}"""
        engine = chat_engine_factory()
        for attempt in range(2):
            try:
                result = engine.query(prompt)
                if result:
                    result["tweet_id"] = tweet_id
                    result["text"] = text
                    result["created_at"] = created_at
                    result["username"] = username
                    from datetime import datetime
                    month = created_at[:7] if len(created_at) >= 7 else datetime.utcnow().strftime("%Y-%m")
                    fp = Path(f"data/pipeline/{username}_{month}_filtered.json")
                    data = []
                    if fp.exists():
                        data = json.loads(fp.read_text(encoding="utf-8"))
                    data.append(result)
                    fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                    return {"ok": True, "is_investment_related": result.get("is_investment_related", False)}
            except Exception:
                if attempt < 1:
                    time.sleep(3)
                    continue
                return {"error": "过滤失败"}
        return {"error": "重试耗尽"}
    return {"error": f"未知 filter action: {action}"}
