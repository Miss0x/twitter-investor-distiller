"""#10 异常检测 — KL 散度异常窗口"""
import json
from pathlib import Path
from src.cards.base import Card
from src.cards import register


@register
class AnomalyCard(Card):
    name = "anomaly"
    template = "anomaly.html"; tab = "insights"; endpoint = "/api/anomaly"; refresh = 600

    def get_data(self, **params) -> dict:
        results = {}
        for fp in Path("data/anomaly").glob("*_anomaly.json"):
            tag = fp.stem.replace("_anomaly", "")
            d = json.loads(fp.read_text(encoding="utf-8"))
            anoms = [r for r in d if r["anomaly"]]
            if anoms:
                results[tag] = {"count": len(anoms), "total": len(d),
                                "recent": [{"kl": a["kl_avg"], "topics": a["topics"][:3]} for a in anoms[-3:]]}
        return {"anomalies": results}