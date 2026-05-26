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
            "cursors": {k.replace("cursor_", ""): v[:20] + "..." for k, v in st.items() if k.startswith("cursor_")},
        }

    def _render_html(self, data: dict) -> str:
        total = data["total_fetched"]
        users = data["users"]
        user_counts = data.get("user_counts", {})
        updated = data["last_updated"]
        rows = "".join(
            f'<tr><td style="font-weight:500">{u}</td>'
            f'<td style="text-align:right">{user_counts.get(u, "?")}</td>'
            f'<td>{data["cursors"].get(u, "首页")}</td>'
            f'<td><span class="tag tag-ok">twitterapi.io</span></td></tr>'
            for u in users
        )
        return f'''<div class="card-title">API 采集状态</div>
<div class="grid grid-3 mb-sm">
  <div class="metric"><div class="metric-label">累计拉取</div><div class="metric-value">{total}</div><div class="metric-sub">条推文</div></div>
  <div class="metric"><div class="metric-label">监控用户</div><div class="metric-value">{len(users)}</div><div class="metric-sub">轮转采集</div></div>
  <div class="metric"><div class="metric-label">上次更新</div><div class="metric-value" style="font-size:13px">{updated}</div><div class="metric-sub">120s 间隔</div></div>
</div>
<table class="data"><tr><th>用户</th><th style="text-align:right">推文数</th><th>进度游标</th><th>来源</th></tr>{rows}</table>

<!-- 新增监控用户 -->
<div class="flex mt-sm" style="gap:4px">
  <input id="um_user" placeholder="输入 X 用户名（如 elonmusk）" style="flex:1;font-size:11px;padding:4px 6px" />
  <button class="btn btn-primary" onclick="addTrackedUser()" style="font-size:11px;padding:4px 10px">验证并添加</button>
</div>
<span id="um_status" class="text-secondary" style="font-size:10px"></span>
<div class="text-secondary mt-sm" style="font-size:11px">主路径: twitterapi.io | 备灾: 浏览器爬虫</div>'''
