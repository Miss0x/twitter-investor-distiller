"""爬虫任务管理 — 任务列表 + 新建 + 详情 + 控制 + 日志 + 推文"""
import requests
from src.cards.base import Card
from src.cards import register

API_BASE = "http://localhost:8000"


@register
class JobManagementCard(Card):
    name = "job_management"
    tab = "dashboard"
    endpoint = "/api/job_management"
    template = "job_management.html"
    refresh = 10

    def get_data(self, **params) -> dict:
        try:
            r = requests.get(f"{API_BASE}/jobs", timeout=5)
            jobs = r.json()
        except Exception:
            jobs = []
        return {"jobs": jobs, "selected_id": params.get("selected_id")}


@register
class PipelineCard(Card):
    name = "pipeline"
    tab = "pipeline"
    endpoint = "/api/pipeline_tasks"
    template = "pipeline.html"
    refresh = 10

    def get_data(self, **params) -> dict:
        try:
            r = requests.get(f"{API_BASE}/pipeline/tasks", timeout=5)
            tasks = r.json()
        except Exception:
            tasks = []
        task_types = list({t.get("task_type", "") for t in tasks if t.get("task_type")})
        return {"tasks": tasks, "task_types": sorted(task_types), "page": "pipeline"}
