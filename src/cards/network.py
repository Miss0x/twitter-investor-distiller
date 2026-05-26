"""#12 关联网络 — 投资者信源推荐"""
import json
from pathlib import Path
from src.cards.base import Card
from src.cards import register


@register
class NetworkCard(Card):
    name = "network"; tab = "insights"; endpoint = "/api/network"; refresh = 3600

    def get_data(self, **params) -> dict:
        fp = Path("data/network/investor_network.json")
        if not fp.exists():
            return {"recs": [], "edges": 0, "nodes": 0}
        d = json.loads(fp.read_text(encoding="utf-8"))
        return {"recs": d.get("recommendations", [])[:5],
                "edges": len(d.get("edges", [])),
                "nodes": len(d.get("nodes", []))}

    def _render_html(self, data: dict) -> str:
        rows = "".join(
            f'<div class="flex-between" style="font-size:12px;margin-bottom:4px">'
            f'<span style="font-weight:500">{r["user"]}</span>'
            f'<span class="text-secondary">被引 {r["in_degree"]}次</span></div>'
            for r in data["recs"]
        )
        return f'<div class="card-title">信源推荐</div>{rows}<div class="text-secondary mt-sm">{data["nodes"]}节点, {data["edges"]}边</div>'
