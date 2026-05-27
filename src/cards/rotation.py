"""
板块轮动卡片（Rotation）
=========================

展示各分析师对行业/板块话题的热度变化。
通过 Z-score 衡量话题提及频率相对于历史均值的偏离程度，
正 Z 表示热度上升，负 Z 表示热度下降。

数据来源: data/rotation/*_rotation.json 文件，
由 compute_rotation.py 脚本按周聚合计算生成。
"""
import json
from pathlib import Path
from src.cards.base import Card
from src.cards import register


@register
class RotationCard(Card):
    """
    板块轮动热点面板。

    展示每位分析师当前最热门的 TOP 5 话题及其 Z-score。
    Z-score > 1 表示热度显著高于历史均值。

    属性:
        name="rotation"            — 唯一标识
        tab="insights"             — 属于分析洞察标签页
        endpoint="/api/rotation"   — API 路由
        refresh=600                — 每 10 分钟自动刷新
        template="rotation.html"   — Jinja2 模板

    get_data() 数据来源:
        data/rotation/{用户名}_rotation.json 文件，
        按 week 字段取最新一周的数据，按 z_score 降序取 TOP 5。

    返回结构:
        {
            "rotation": {
                "TJ_Research": [
                    {"topic": "AI半导体", "z": 3.2, "count": 15},
                    {"topic": "新能源",    "z": 2.1, "count": 8},
                    ...
                ],
                ...
            }
        }
    """

    def get_data(self, **params) -> dict:
        results = {}
        for fp in Path("data/rotation").glob("*_rotation.json"):
            username = fp.stem.replace("_rotation", "")
            d = json.loads(fp.read_text(encoding="utf-8"))
            weeks = sorted({r["week"] for r in d})
            if weeks:
                hot = sorted([r for r in d if r["week"] == weeks[-1]], key=lambda x: x["z_score"], reverse=True)[:5]
                results[username] = [{"topic": r["topic"], "z": r["z_score"], "count": r["count"]} for r in hot]
        return {"rotation": results}