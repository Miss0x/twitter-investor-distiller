"""#2 准确率面板"""
import json
from pathlib import Path
from src.cards.base import Card
from src.cards import register


@register
class AccuracyCard(Card):
    name = "accuracy"
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

    def _render_html(self, data: dict) -> str:
        analysts = data.get("analysts", {})
        rows = "".join(
            f'<div style="font-size:12px;margin-bottom:6px"><b>{u}</b>: 胜率 {a["win_rate"]}%, '
            f'夏普 {a.get("sharpe", "?")}, {a["count"]}条信号</div>'
            for u, a in analysts.items()
        )
        return f'<div class="card-title">准确率 (30日)</div>{rows}'
