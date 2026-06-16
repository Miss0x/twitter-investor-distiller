"""
系统统计卡片（System Status）
==============================

展示系统的核心数据统计：数据库推文总数、已完成分析文件数、
画像文件数、信号评分条数。Dashboard 首页概览卡片。
"""
import json
from pathlib import Path
from src.cards.base import Card
from src.cards import register


@register
class SystemStatusCard(Card):
    """
    系统统计概览卡片。

    提供四大核心指标的快照统计，是 Dashboard 的入口级概览。

    属性:
        name="system_status"        — 唯一标识
        tab="dashboard"             — 属于主仪表盘标签页
        endpoint="/api/system_status" — API 路由
        refresh=60                  — 每 60 秒自动刷新
        template="system_status.html" — Jinja2 模板

    get_data() 数据来源:
        - tweets 表: 推文总数
        - data/pipeline/*_analyzed_cleaned.json: 分析完成文件数
        - data/pipeline/*portrait.md: 画像文件数
        - 分析文件内部的 signal_score 字段: 信号评分条数

    返回结构:
        {
            "tweets": int,       # 数据库 tweets 表总行数
            "analyzed": int,     # 已完成分析的分析师数
            "portraits": int,    # 生成的画像文件数
            "signals": int       # 生成评分的信号总条数
        }
    """
    name = "system_status"
    def get_data(self, **params) -> dict:
        from src.storage.database import db
        from src.storage.models import Tweet
        db.init_db()
        s = db.get_session()
        tweets = s.query(Tweet).count()
        s.close()
        analyzed_files = list(Path("data/pipeline").glob("*_analyzed_cleaned.json"))
        pipeline = len(analyzed_files)
        portraits = len(list(Path("data/pipeline").glob("*portrait.md")))
        signals = 0
        for fp in analyzed_files:
            for r in json.loads(fp.read_text(encoding="utf-8")):
                if r.get("signal_score"):
                    signals += 1
        return {"tweets": tweets, "analyzed": pipeline, "portraits": portraits, "signals": signals}

