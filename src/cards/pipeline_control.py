"""
API 采集状态卡片（Pipeline Control）
=====================================

监控 Twitter API 自动采集的后台调度状态，
包括各用户的推文计数、限流状态、采集游标等信息。
"""
import json
from pathlib import Path
from src.cards.base import Card
from src.cards import register


@register
class ApiStatusCard(Card):
    """
    API 采集状态卡片。

    展示 Twitter API 自动调度器的运行状态和各用户数据采集进度。

    属性:
        name="api_status"         — 唯一标识
        tab="dashboard"           — 属于主仪表盘标签页
        endpoint="/api/api_status" — API 路由
        refresh=30                — 每 30 秒自动刷新
        template="api_status.html" — Jinja2 模板

    get_data() 数据来源:
        - data/auto_scheduler_state.json: 调度器状态（总拉取数、最后更新时间、限流标记）
        - data/users.json: 监控用户列表
        - DB tweets JOIN users 表: 各用户的推文计数

    返回结构:
        {
            "users": ["TJ_Research", ...],          # 监控用户列表
            "user_counts": {"TJ_Research": 500, ...}, # 各用户推文数
            "total_fetched": int,                     # 累计拉取总数
            "last_updated": str,                      # 最后更新时间
            "rate_limited": str,                      # 限流标记（空=正常）
            "cursors": {"TJ_Research": "...", ...}    # 各用户采集游标（截断显示）
        }
    """
    name = "api_status"
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
        except Exception:
            pass
        return {
            "users": users,
            "user_counts": user_counts,
            "total_fetched": st.get("total_fetched", 0),
            "last_updated": st.get("updated", "未开始"),
            "rate_limited": st.get("rate_limited", ""),
            "cursors": {k.replace("cursor_", ""): v[:20] + "..." for k, v in st.items() if k.startswith("cursor_")},
        }


