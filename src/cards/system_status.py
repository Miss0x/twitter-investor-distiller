"""系统状态 — DB/画像/信号统计"""
import json
from pathlib import Path
from src.cards.base import Card
from src.cards import register


@register
class SystemStatusCard(Card):
    name = "system_status"; tab = "dashboard"; endpoint = "/api/system_status"; refresh = 60

    def get_data(self, **params) -> dict:
        from src.storage.database import db
        from src.storage.models import Tweet
        db.init_db(); s = db.get_session()
        tweets = s.query(Tweet).count(); s.close()
        pipeline = len(list(Path("data/pipeline").glob("*_analyzed_cleaned.json")))
        portraits = len(list(Path("data/pipeline").glob("*portrait.md")))
        signals = 0
        for fp in Path("data/pipeline").glob("*_analyzed_cleaned.json"):
            for r in json.loads(fp.read_text(encoding="utf-8")):
                if r.get("signal_score"):
                    signals += 1
        return {"tweets": tweets, "analyzed": pipeline, "portraits": portraits, "signals": signals}

    def _render_html(self, data: dict) -> str:
        items = [("数据库", f'{data["tweets"]}条'), ("画像", f'{data["portraits"]}份'),
                 ("信号", f'{data["signals"]}条'), ("分析文件", f'{data["analyzed"]}个')]
        rows = "".join(
            f'<div class="flex-between" style="font-size:12px;margin-bottom:4px">'
            f'<span class="text-secondary">{k}</span><span>{v}</span></div>'
            for k, v in items
        )
        return f'<div class="card-title">系统状态</div>{rows}'
