"""爬虫任务管理 + 流水线控制"""
import requests
from src.cards.base import Card
from src.cards import register

API_BASE = "http://localhost:8000"


@register
class JobManagementCard(Card):
    name = "job_management"
    tab = "dashboard"
    endpoint = "/api/job_management"
    refresh = 10

    def get_data(self, **params) -> dict:
        try:
            r = requests.get(f"{API_BASE}/jobs", timeout=5)
            jobs = r.json()
        except Exception:
            jobs = []
        return {"jobs": jobs, "selected_id": params.get("selected_id")}

    def _render_html(self, data: dict) -> str:
        jobs = data.get("jobs", [])
        if not jobs:
            return '<div class="card-title">爬虫任务</div><div class="text-secondary">无任务</div>'
        rows = "".join(
            f'<tr><td style="font-weight:500">#{j.get("id","?")}</td>'
            f'<td>{j.get("username","?")}</td>'
            f'<td>{j.get("status","?")}</td>'
            f'<td>{j.get("progress","?")}</td></tr>'
            for j in jobs[:10]
        )
        return f'<div class="card-title">爬虫任务</div><table class="data"><tr><th>ID</th><th>用户</th><th>状态</th><th>进度</th></tr>{rows}</table>'


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
