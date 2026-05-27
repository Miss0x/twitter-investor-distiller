"""
关联网络卡片（Network）
========================

展示投资者之间的信息关联关系，推荐潜在的高质量信源。
基于分析师互动行为（转发、引用、提及等）构建关系图谱，
推荐与已监控分析师高度关联但尚未关注的其他投资者。

数据来源: data/network/investor_network.json 文件，
由 build_network.py 脚本构建生成。
"""
import json
from pathlib import Path
from src.cards.base import Card
from src.cards import register


@register
class NetworkCard(Card):
    """
    投资者关联网络面板。

    展示基于互动关系的投资者推荐列表和网络图规模统计。

    属性:
        name="network"             — 唯一标识
        tab="insights"             — 属于分析洞察标签页
        endpoint="/api/network"    — API 路由
        refresh=3600               — 每小时自动刷新（网络结构变化慢）
        template="network.html"    — Jinja2 模板

    get_data() 数据来源:
        data/network/investor_network.json 文件，
        由节点(nodes)和边(edges)组成的关系图数据。

    返回结构:
        {
            "recs": [               # TOP 5 推荐信源
                {
                    "username": str,
                    "score": float,
                    "reason": str,
                    ...
                },
                ...
            ],
            "edges": int,           # 关系边总数
            "nodes": int            # 节点总数
        }
    """
        fp = Path("data/network/investor_network.json")
        if not fp.exists():
            return {"recs": [], "edges": 0, "nodes": 0}
        d = json.loads(fp.read_text(encoding="utf-8"))
        return {"recs": d.get("recommendations", [])[:5],
                "edges": len(d.get("edges", [])),
                "nodes": len(d.get("nodes", []))}