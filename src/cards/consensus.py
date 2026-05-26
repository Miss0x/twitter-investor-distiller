"""#4 共识面板 — 多分析师信号共识 TOP"""
import json
from pathlib import Path
from src.cards.base import Card
from src.cards import register


@register
class ConsensusCard(Card):
    name = "consensus"
    template = "consensus.html"; tab = "insights"; endpoint = "/api/consensus"; refresh = 600

    def get_data(self, **params) -> dict:
        results = []
        for fp in Path("data/consensus").glob("*_consensus.json"):
            entries = json.loads(fp.read_text(encoding="utf-8"))
            if entries:
                e = {**entries[-1], "ticker": fp.stem.replace("_consensus", "")}
                results.append(e)
        results.sort(key=lambda x: x.get("consensus_score", 0), reverse=True)
        multi = sum(1 for r in results if len(r.get("analysts_in_window", [])) >= 2)
        return {"top": results[:10], "total": len(results), "multi": multi}
