"""分析师画像生成卡片。

从 pipeline_execute.py 抽出，独立为单一职责文件。
"""
from __future__ import annotations

import json
from pathlib import Path

from src.cards.base import Card
from src.cards import register


def _load_users_config() -> list[str]:
    """从 data/users.json 读取监控用户列表。"""
    fp = Path("data/users.json")
    if fp.exists():
        return json.loads(fp.read_text(encoding="utf-8"))
    return ["TJ_Research", "dearbaibabybus"]


@register
class PortraitGenerateCard(Card):
    """分析师画像生成卡片。"""

    name = "portrait_generate"
    tab = "portraits"
    endpoint = "/api/portrait_generate"
    refresh = 0

    WINDOWS = [
        ("1个月", 30, "近一月"),
        ("3个月", 90, "近三月"),
        ("6个月", 180, "近半年"),
        ("1年", 365, "近一年"),
        ("全量", 9999, "全部历史"),
    ]

    def get_data(self, **params) -> dict:
        try:
            from src.storage.database import db
            from src.storage.models import PipelineTask
            db.init_db()
            s = db.get_session()
            try:
                portrait_tasks = s.query(PipelineTask).filter(
                    PipelineTask.task_type == "portrait"
                ).order_by(PipelineTask.id.desc()).limit(20).all()
                items = [{"id": t.id, "status": t.status,
                          "payload": json.loads(t.payload) if t.payload else {},
                          "created_at": str(t.created_at)[:16] if t.created_at else ""}
                         for t in portrait_tasks]
            finally:
                s.close()
        except Exception:
            items = []
        return {"tasks": items, "users": _load_users_config()}

    def _render_html(self, data: dict) -> str:
        users = data.get("users", [])
        pending = [t for t in data.get("tasks", []) if t["status"] == "pending"]
        done = [t for t in data.get("tasks", []) if t["status"] == "done"]
        user_opts = "".join(f'<option value="{u}">{u}</option>' for u in users)
        window_btns = "".join(
            f'<button class="btn pg-win-btn" data-action="select-window" data-label="{label}" id="pg_win_{label}" style="font-size:10px;padding:3px 8px">{label}({desc})</button>'
            for label, days, desc in self.WINDOWS
        )
        return f'''<div class="card-title">画像生成</div>
<div class="mb-sm"><span class="tag tag-ok">已完成: {len(done)}</span> <span class="tag tag-warn">待处理: {len(pending)}</span></div>

<div class="flex mb-sm" style="gap:6px">
  <select id="pg_user" style="flex:1">{user_opts}</select>
</div>

<div class="mb-sm"><span class="text-secondary" style="font-size:11px">时间窗口</span></div>
<div class="flex mb-sm" style="gap:4px;flex-wrap:wrap" id="pg_windows">{window_btns}</div>

<div class="flex mb-sm" style="gap:6px">
  <input id="pg_from" type="date" style="flex:1;font-size:11px;padding:4px 6px" placeholder="开始日期" />
  <input id="pg_to" type="date" style="flex:1;font-size:11px;padding:4px 6px" placeholder="结束日期" />
</div>

<div class="flex mb-sm" style="gap:6px">
  <input id="pg_label" placeholder="画像标签（可选）" style="flex:1;font-size:11px;padding:4px 6px" />
  <button class="btn btn-primary" data-action="gen-portrait" data-card="portrait_generate" style="font-size:11px;padding:4px 12px">生成画像</button>
</div>
<input type="hidden" id="pg_window" value="" />
<span id="pg_status" class="text-secondary" style="font-size:10px"></span>

<style>
.pg-win-btn {{ border:0.5px solid var(--border-secondary); }}
.pg-win-btn.selected {{ border-color: var(--text-primary); font-weight:500; }}
</style>'''
