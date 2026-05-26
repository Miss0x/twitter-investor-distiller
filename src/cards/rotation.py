"""#8 板块轮动 — 分析师话题 Z-score 热点"""
import json
from pathlib import Path
from src.cards.base import Card
from src.cards import register


@register
class RotationCard(Card):
    name = "rotation"
    template = "rotation.html"; tab = "insights"; endpoint = "/api/rotation"; refresh = 600

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