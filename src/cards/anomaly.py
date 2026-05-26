"""#10 异常检测 — KL 散度异常窗口"""
import json
from pathlib import Path
from src.cards.base import Card
from src.cards import register


@register
class AnomalyCard(Card):
    name = "anomaly"; tab = "insights"; endpoint = "/api/anomaly"; refresh = 600

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

    def _render_html(self, data: dict) -> str:
        items = []
        for tag, info in data["anomalies"].items():
            kls = " / ".join(f'{a["kl"]:.2f}' for a in info["recent"][:3])
            items.append(
                f'<div class="flex-between" style="font-size:12px;margin-bottom:6px">'
                f'<span class="text-secondary">{tag}</span>'
                f'<span style="color:var(--text-warning);font-size:11px">KL {kls}</span></div>'
            )
        return f'<div class="card-title">异常检测</div>{"".join(items[:6]) or "<div class=\"text-secondary\">无异常</div>"}'
