"""#12 关联网络 — 投资者信源推荐"""
import json
from pathlib import Path
from src.cards.base import Card
from src.cards import register


@register
class NetworkCard(Card):
    name = "network"
    template = "network.html"
    tab = "insights"
    endpoint = "/api/network"
    refresh = 3600

    def get_data(self, **params) -> dict:
        fp = Path("data/network/investor_network.json")
        if not fp.exists():
            return {"recs": [], "edges": 0, "nodes": 0}
        d = json.loads(fp.read_text(encoding="utf-8"))
        return {"recs": d.get("recommendations", [])[:5],
                "edges": len(d.get("edges", [])),
                "nodes": len(d.get("nodes", []))}