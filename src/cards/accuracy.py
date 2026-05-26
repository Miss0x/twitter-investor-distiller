"""#2 准确率面板"""
import json
from pathlib import Path
from src.cards.base import Card
from src.cards import register


@register
class AccuracyCard(Card):
    name = "accuracy"
    template = "accuracy.html"
    tab = "dashboard"
    endpoint = "/api/accuracy"
    refresh = 300

    def get_data(self, **params) -> dict:
        result = {}
        for fp in Path("data/accuracy").glob("*_accuracy.json"):
            username = fp.stem.replace("_accuracy", "")
            d = json.loads(fp.read_text(encoding="utf-8"))
            r30 = d.get("returns_30d", {})
            result[username] = {
                "count": r30.get("count", 0),
                "win_rate": round(r30.get("win_rate", 0) * 100),
                "avg_return": round(r30.get("avg_return", 0) * 100, 1),
                "sharpe": r30.get("sharpe"),
            }
        return {"analysts": result}