"""API 采集状态 + 流水线控制"""
import json
from pathlib import Path
import requests
from src.cards.base import Card
from src.cards import register

API_BASE = "http://localhost:8000"


@register
class ApiStatusCard(Card):
    name = "api_status"
    tab = "dashboard"
    endpoint = "/api/api_status"
    refresh = 30

    def get_data(self, **params) -> dict:
        state = Path("data/auto_scheduler_state.json")
        st = json.loads(state.read_text()) if state.exists() else {}
        return {
            "users": ["TJ_Research", "dearbaibabybus"],
            "total_fetched": st.get("total_fetched", 0),
            "last_updated": st.get("updated", "未开始"),
            "cursors": {k.replace("cursor_", ""): v[:20] + "..." for k, v in st.items() if k.startswith("cursor_")},
        }

    def _render_html(self, data: dict) -> str:
        total = data["total_fetched"]
        users = data["users"]
        updated = data["last_updated"]
        rows = "".join(
            f'<tr><td style="font-weight:500">{u}</td>'
            f'<td>{data["cursors"].get(u, "首页")}</td>'
            f'<td><span class="tag tag-ok">twitterapi.io</span></td></tr>'
            for u in users
        )
        return f'''<div class="card-title">API 采集状态</div>
<div class="grid grid-3 mb-sm">
  <div class="metric"><div class="metric-label">累计拉取</div><div class="metric-value">{total}</div><div class="metric-sub">条推文</div></div>
  <div class="metric"><div class="metric-label">监控用户</div><div class="metric-value">{len(users)}</div><div class="metric-sub">轮转采集</div></div>
  <div class="metric"><div class="metric-label">上次更新</div><div class="metric-value" style="font-size:13px">{updated}</div><div class="metric-sub">60s 间隔</div></div>
</div>
<table class="data"><tr><th>用户</th><th>进度游标</th><th>来源</th></tr>{rows}</table>
<div class="text-secondary mt-sm" style="font-size:11px">主路径: twitterapi.io | 备灾: 浏览器爬虫</div>'''


@register
class PipelineCard(Card):
    name = "pipeline"
    tab = "pipeline"
    endpoint = "/api/pipeline_tasks"
    refresh = 10

    def get_data(self, **params) -> dict:
        try:
            r = requests.get(f"{API_BASE}/pipeline/tasks", timeout=5)
            tasks = r.json()
        except Exception:
            tasks = []
        return {"tasks": tasks, "page": "pipeline"}

    def _render_html(self, data: dict) -> str:
        tasks = data.get("tasks", [])
        if not tasks:
            return '<div class="card-title">分析流水线</div><div class="text-secondary">无任务</div>'
        rows = "".join(
            f'<tr><td>#{t.get("id","?")}</td>'
            f'<td>{t.get("task_type","?")}</td>'
            f'<td>{t.get("status","?")}</td></tr>'
            for t in tasks[:20]
        )
        return f'<div class="card-title">分析流水线</div><table class="data"><tr><th>ID</th><th>类型</th><th>状态</th></tr>{rows}</table>'
