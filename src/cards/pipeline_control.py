"""API 采集状态"""
import json
from pathlib import Path
from src.cards.base import Card
from src.cards import register


@register
class ApiStatusCard(Card):
    name = "api_status"
    tab = "dashboard"
    endpoint = "/api/api_status"
    refresh = 30
    template = "api_status.html"

    def get_data(self, **params) -> dict:
        state = Path("data/auto_scheduler_state.json")
        st = json.loads(state.read_text()) if state.exists() else {}
        users_fp = Path("data/users.json")
        users = json.loads(users_fp.read_text(encoding="utf-8")) if users_fp.exists() else ["TJ_Research", "dearbaibabybus"]
        # 从 DB 拿每个用户的推文数（单查询）
        user_counts = {}
        try:
            from src.storage.database import db
            db.init_db()
            s = db.get_session()
            placeholders = ",".join(["?"] * len(users))
            rows = s.execute(
                f"SELECT u.username, COUNT(*) FROM tweets t JOIN users u ON t.user_id=u.id WHERE u.username IN ({placeholders}) GROUP BY u.username",
                tuple(users)
            ).fetchall()
            user_counts = {row[0]: row[1] for row in rows}
            s.close()
        except:
            pass
        return {
            "users": users,
            "user_counts": user_counts,
            "total_fetched": st.get("total_fetched", 0),
            "last_updated": st.get("updated", "未开始"),
            "rate_limited": st.get("rate_limited", ""),
            "cursors": {k.replace("cursor_", ""): v[:20] + "..." for k, v in st.items() if k.startswith("cursor_")},
        }


