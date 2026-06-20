"""分析师画像生成任务。

从 task_executor.py 抽出。
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from src.pipeline.task_executor import _PIPELINE_CFG  # noqa: F401  # 保留供将来扩展


def _generate_portrait(username: str) -> dict:
    from src.ai.chat_engine import chat_engine_factory
    window_label = ""
    match = __import__("re").match(r"(.+?)_(.+)", username)
    if match:
        username = match.group(1)
        window_label = match.group(2)
    all_tweets = []
    for fp in sorted(Path("data/pipeline").glob(f"{username}_*_analyzed.json")):
        if "_cleaned" in fp.name:
            continue
        data = json.loads(fp.read_text(encoding="utf-8"))
        all_tweets.extend(data)
    if not all_tweets:
        return {"error": "无分析记录"}
    window_days_map = {"1个月": 30, "3个月": 90, "6个月": 180, "1年": 365, "全量": 9999}
    days = window_days_map.get(window_label, 9999)
    cutoff = datetime.utcnow() - timedelta(days=days) if days < 9999 else datetime(2000, 1, 1)
    filtered = [t for t in all_tweets
                if t.get("created_at", "") and t["created_at"][:10] >= cutoff.strftime("%Y-%m-%d")]
    if not filtered:
        filtered = all_tweets[-50:] if len(all_tweets) > 50 else all_tweets
    tweets_sample = filtered[-30:]
    tweets_text = "\n---\n".join(
        f"推文({t.get('created_at','')[:10]}): {t.get('text','')[:200]}"
        f"\n分析: 话题={t.get('topic','')}, 立场={t.get('stance','')}, "
        f"置信度={t.get('confidence','')}"
        for t in tweets_sample
    )
    prompt = f"""你是一名金融分析师。请根据以下 {len(filtered)} 条（展示最近 {len(tweets_sample)} 条）推文分析记录，生成 {username} 的投资风格画像。

### 分析师的推文分析记录:
{tweets_text}

请按以下 JSON 格式输出画像（只输出 JSON）:
{{
    "analyst": "{username}",
    "summary": "分析师风格概括（2-3句话）",
    "preferred_sectors": ["偏好行业"],
    "signal_accuracy": "高/中/低",
    "typical_stance": "看多/看空/均衡",
    "confidence_level": "高/中/低",
    "focus_areas": ["主要关注领域"],
    "style_tags": ["价值投资", "成长投资", "趋势跟踪", "事件驱动"],
    "strengths": ["优势"],
    "weaknesses": ["劣势"]
}}"""
    engine = chat_engine_factory()
    for attempt in range(3):
        try:
            result = engine.query(prompt)
            if result:
                portrait_path = Path(f"data/pipeline/{username}_{window_label}_portrait.md")
                md = f"# {username} 投资风格画像\n\n"
                md += f"**生成时间**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}\n\n"
                md += f"**分析窗口**: {window_label}（{len(filtered)} 条推文）\n\n"
                md += "## 概要\n" + result.get("summary", "") + "\n\n"
                md += "## 偏好行业\n"
                for s in result.get("preferred_sectors", []):
                    md += f"- {s}\n"
                md += "\n## 风格标签\n"
                for t in result.get("style_tags", []):
                    md += f"- {t}\n"
                md += "\n## 优势\n"
                for s in result.get("strengths", []):
                    md += f"- {s}\n"
                md += "\n## 劣势\n"
                for w in result.get("weaknesses", []):
                    md += f"- {w}\n"
                portrait_path.parent.mkdir(parents=True, exist_ok=True)
                portrait_path.write_text(md, encoding="utf-8")
                return {"ok": True, "portrait": md[:100]}
        except Exception:
            if attempt < 2:
                time.sleep(5)
                continue
            return {"error": "画像生成失败"}
    return {"error": "重试耗尽"}
