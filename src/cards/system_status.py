"""系统状态 — DB/画像/信号统计"""
import json
from pathlib import Path
from src.cards.base import Card
from src.cards import register


@register
class SystemStatusCard(Card):
    name = "system_status"; tab = "dashboard"; endpoint = "/api/system_status"; refresh = 60
    template = "system_status.html"

    def get_data(self, **params) -> dict:
        from src.storage.database import db
        from src.storage.models import Tweet
        db.init_db(); s = db.get_session()
        tweets = s.query(Tweet).count(); s.close()
        analyzed_files = list(Path("data/pipeline").glob("*_analyzed_cleaned.json"))
        pipeline = len(analyzed_files)
        portraits = len(list(Path("data/pipeline").glob("*portrait.md")))
        signals = 0
        for fp in analyzed_files:
            for r in json.loads(fp.read_text(encoding="utf-8")):
                if r.get("signal_score"):
                    signals += 1
        return {"tweets": tweets, "analyzed": pipeline, "portraits": portraits, "signals": signals}

