"""API 采集状态 + 推文分析"""
import json
from pathlib import Path
from collections import Counter
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
        # 从 DB 拿每个用户的推文数
        user_counts = {}
        try:
            from src.storage.database import db
            db.init_db()
            s = db.get_session()
            for u in users:
                cnt = s.execute("SELECT COUNT(*) FROM tweets t JOIN users u ON t.user_id=u.id WHERE u.username=?", (u,)).fetchone()[0]
                user_counts[u] = cnt
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


@register
class PipelineCard(Card):
    name = "pipeline"
    tab = "pipeline"
    endpoint = "/api/pipeline_tasks"
    refresh = 10

    def get_data(self, **params) -> dict:
        try:
            from src.storage.database import db
            from src.storage.models import PipelineTask
            db.init_db()
            s = db.get_session()
            tasks = s.query(PipelineTask).order_by(PipelineTask.id.desc()).limit(50).all()
            task_list = [{"id": t.id, "task_type": t.task_type, "status": t.status,
                          "created_at": str(t.created_at)[:16] if t.created_at else ""} for t in tasks]
            s.close()
            return {"task_list": task_list, "total": len(task_list), "page": "pipeline"}
        except Exception:
            return {"task_list": [], "total": 0, "page": "pipeline"}

    def _render_html(self, data: dict) -> str:
        tasks = data.get("task_list", [])
        total = data.get("total", 0)
        if not tasks:
            return '<div class="card-title">推文分析</div><div class="text-secondary">暂无待处理任务。启动实时 API 采集后会自动生成。</div>'
        type_labels = {"filter":"过滤筛选","analyze":"推文分析","fetch_price":"股价拉取","fetch_crypto":"加密货币","portrait":"画像生成","clean":"数据清洗"}
        status_labels = {"pending":"待处理","running":"执行中","done":"已完成","failed":"失败","skipped":"已跳过"}
        stats = Counter(type_labels.get(t.get("task_type", ""), t.get("task_type", "?")) for t in tasks)
        stat_html = " ".join(f'<span class="tag tag-ok">{k}: {v}</span>' for k, v in stats.most_common(4))
        rows = "".join(
            f'<tr><td><span style="font-weight:500">#{t.get("id","?")}</span></td>'
            f'<td>{type_labels.get(t.get("task_type",""), t.get("task_type","?"))}</td>'
            f'<td><span class="tag {"tag-warn" if t.get("status")=="pending" else "tag-ok"}">{status_labels.get(t.get("status",""), t.get("status","?"))}</span></td>'
            f'<td style="font-size:11px">{t.get("created_at","")}</td></tr>'
            for t in tasks[:15]
        )
        return f'<div class="card-title">推文分析</div><div class="mb-sm">{stat_html} <span class="text-secondary" style="font-size:11px">共 {total} 个</span></div><table class="data"><tr><th>ID</th><th>类型</th><th>状态</th><th>时间</th></tr>{rows}</table>'
