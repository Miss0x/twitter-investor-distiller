"""#4 共识面板 — 多分析师信号共识 TOP"""
import json
from pathlib import Path
from src.cards.base import Card
from src.cards import register


@register
class ConsensusCard(Card):
    name = "consensus"; tab = "insights"; endpoint = "/api/consensus"; refresh = 600

    def get_data(self, **params) -> dict:
        results = []
        for fp in Path("data/consensus").glob("*_consensus.json"):
            entries = json.loads(fp.read_text(encoding="utf-8"))
            if entries:
                e = entries[-1]; e["ticker"] = fp.stem.replace("_consensus", "")
                results.append(e)
        results.sort(key=lambda x: x.get("consensus_score", 0), reverse=True)
        multi = sum(1 for r in results if len(r.get("analysts_in_window", [])) >= 2)
        return {"top": results[:10], "total": len(results), "multi": multi}

    def _render_html(self, data: dict) -> str:
        rows = "".join(
            f'<tr><td style="font-weight:500">{r["ticker"]}</td>'
            f'<td style="text-align:right;font-weight:500;color:var(--text-success)">{r["consensus_score"]:.0f}</td>'
            f'<td style="text-align:right;font-size:11px">{"🔥" if len(r.get("analysts_in_window",[]))>=2 else ""} {r.get("signal_count",0)}条</td></tr>'
            for r in data["top"][:5]
        )
        return f'<div class="card-title">共识 TOP 5</div><table class="data"><tr><th>股票</th><th style="text-align:right">得分</th><th style="text-align:right">信号</th></tr>{rows}</table><div class="text-secondary mt-sm">{data["total"]}只覆盖, {data["multi"]}只双人</div>'
