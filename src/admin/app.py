"""独立管理后台 — 完全隔离的安全站点

运行于独立端口，不在公网 Dashboard 暴露任何入口。
提供：用户管理、活动监控、封禁管理、系统配置。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(title="Admin Panel — 管理后台", docs_url=None, redoc_url=None)

# 隐藏服务器信息
app.swagger_ui_oauth2_redirect_url = None


# ═══════════════════════════════════════════════════
# 响应式 CSS — 独立于主站主题
# ═══════════════════════════════════════════════════

ADMIN_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0a0a0b;--card:#141416;--border:hsl(0 0% 100% / .08);
  --text:#e4e4e7;--muted:#78787d;--dim:#505055;
  --accent:hsl(219 100% 44%);--green:hsl(160 100% 36%);
  --red:hsl(0 100% 69%);--orange:hsl(36 100% 50%);
  --font:system-ui,-apple-system,sans-serif;
  --radius:8px;--radius-lg:12px;
  --ease:cubic-bezier(.16,1,.3,1);
}
body{font-family:var(--font);font-size:13px;color:var(--text);background:var(--bg);line-height:1.6}
h1{font-size:20px;font-weight:600;margin-bottom:8px}
h2{font-size:16px;font-weight:600;margin:24px 0 12px}
h3{font-size:14px;font-weight:600;margin-bottom:8px}
a{color:var(--accent);text-decoration:none}
.container{max-width:1100px;margin:0 auto;padding:32px 24px}
header{border-bottom:1px solid var(--border);padding:14px 24px;display:flex;justify-content:space-between;align-items:center;background:var(--card)}
header .brand{font-weight:700;font-size:15px;letter-spacing:-.01em;display:flex;align-items:center;gap:8px}
header .brand .dot{width:8px;height:8px;border-radius:50%;background:var(--green)}
header nav{display:flex;gap:4px}
header nav a{padding:6px 14px;border-radius:6px;font-size:13px;color:var(--muted);transition:all .15s}
header nav a:hover{color:var(--text);background:hsl(0 0% 100% / .05)}
header nav a.active{color:var(--text);background:hsl(0 0% 100% / .08);font-weight:500}
.grid2{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}
.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:20px}
.metric{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:14px}
.metric .label{font-size:11px;color:var(--muted);letter-spacing:.02em}
.metric .value{font-size:26px;font-weight:600;margin-top:2px;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.metric .sub{font-size:11px;color:var(--dim);margin-top:2px}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;padding:8px 12px;color:var(--muted);font-weight:500;font-size:11px;border-bottom:1px solid var(--border);letter-spacing:.02em}
td{padding:8px 12px;border-bottom:1px solid hsl(0 0% 100% / .04)}
tr:hover{background:hsl(0 0% 100% / .02)}
.btn{padding:6px 14px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);cursor:pointer;font-size:12px;font-family:var(--font);transition:all .15s}
.btn:hover{background:hsl(0 0% 100% / .06)}
.btn-danger{border-color:hsl(0 100% 69% / .25);color:var(--red)}
.btn-danger:hover{background:hsl(0 100% 69% / .08)}
.btn-green{border-color:hsl(160 100% 36% / .25);color:var(--green)}
.tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:500}
.tag-active{background:hsl(160 100% 36% / .12);color:var(--green)}
.tag-inactive{background:hsl(0 100% 69% / .1);color:var(--red)}
.tag-super{background:hsl(219 100% 44% / .12);color:var(--accent)}
.bar-track{height:20px;background:hsl(0 0% 100% / .04);border-radius:4px;overflow:hidden;margin-top:4px}
.bar-fill{height:100%;background:var(--accent);border-radius:4px;transition:width .3s var(--ease)}
.status-dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:6px}
.status-dot.on{background:var(--green)}
.status-dot.off{background:var(--dim)}
@media(max-width:768px){.grid4{grid-template-columns:repeat(2,1fr)}.grid2{grid-template-columns:1fr}}
"""


# ═══════════════════════════════════════════════════
# 主页面
# ═══════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def admin_index():
    from src.admin.activity import ActivityTracker
    stats = ActivityTracker().stats(days=7)

    action_labels = {
        "page_view": "浏览", "config_change": "修改配置", "task_execute": "执行任务",
        "task_seed": "扫描任务", "governance_acknowledge": "接受风险",
        "governance_revoke": "撤销接受", "chat_query": "AI 问答",
        "observation_add": "添加观察", "observation_remove": "移除观察",
    }
    actions_html = ""
    total = stats.get("total_events", 0) or 1
    for k, v in sorted(stats["actions_by_type"].items(), key=lambda x: -x[1])[:8]:
        pct = min(round(v / total * 100, 1), 100)
        label = action_labels.get(k, k)
        actions_html += f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px"><span style="font-size:11px;color:var(--muted);width:80px;text-align:right">{label}</span><div style="flex:1" class="bar-track"><div class="bar-fill" style="width:{pct}%"></div></div><span style="font-size:11px;color:var(--dim);width:40px">{v}</span></div>'

    recent = ""
    for e in ActivityTracker().query(limit=15):
        al = action_labels.get(e.get("action", ""), e.get("action", ""))
        ts = e.get("timestamp", "")[-8:] or ""
        recent += f'<tr><td>{al}</td><td style="color:var(--dim)">{e.get("path","")}</td><td style="color:var(--muted)">{e.get("ip_prefix","")}</td><td style="color:var(--dim)">{ts}</td></tr>'

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>管理后台</title><style>{ADMIN_CSS}</style></head><body>
<header><div class="brand"><span class="dot"></span>管理后台</div><nav><a href="/" class="active">概览</a><a href="/users">用户</a></nav></header>
<div class="container">
<h1>系统概览</h1>
<div class="grid4" style="margin-bottom:24px">
<div class="metric"><div class="label">今日操作</div><div class="value">{stats['total_events']}</div><div class="sub">过去 7 天累计</div></div>
<div class="metric"><div class="label">活跃来源</div><div class="value">{stats['unique_ip_prefixes']}</div><div class="sub">独立网络前缀</div></div>
<div class="metric"><div class="label">标签热度 Top</div><div class="value" style="font-size:18px">{', '.join(list(stats['tabs_by_usage'].keys())[:2]) or '—'}</div><div class="sub">浏览最多标签</div></div>
<div class="metric"><div class="label">数据日期</div><div class="value" style="font-size:18px">7 天</div><div class="sub">最近统计窗口</div></div>
</div>
<div class="grid2">
<div class="card"><h3>操作类型分布</h3>{actions_html or '<span style="color:var(--dim)">暂无数据</span>'}</div>
<div class="card"><h3>最近活动</h3><table><thead><tr><th>操作</th><th>路径</th><th>来源</th><th>时间</th></tr></thead><tbody>{recent or '<tr><td colspan="4" style="color:var(--dim)">暂无记录</td></tr>'}</tbody></table></div>
</div>
</div>
</body></html>"""


# ═══════════════════════════════════════════════════
# 用户管理页面
# ═══════════════════════════════════════════════════

@app.get("/users", response_class=HTMLResponse)
async def admin_users():
    from src.admin.auth_models import User
    from src.storage.database import db

    session = db.get_session()
    users = session.query(User).order_by(User.id.desc()).all()
    session.close()

    rows = ""
    for u in users:
        status_class = "tag-active" if u.is_active else "tag-inactive"
        status_text = "正常" if u.is_active else "已停用"
        super_class = "" if not u.is_superuser else '<span class="tag tag-super">管理员</span>'
        email = u.email[:3] + "****"
        rows += f"""<tr>
<td>{u.id}</td><td>{u.username}</td><td style="color:var(--dim)">{email}</td>
<td>{super_class} <span class="tag {status_class}">{status_text}</span></td>
<td>
<button class="btn {'btn-danger' if u.is_active else 'btn-green'}" onclick="toggleUser({u.id})">{'停用' if u.is_active else '启用'}</button>
</td></tr>"""

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>管理后台 · 用户</title><style>{ADMIN_CSS}</style></head><body>
<header><div class="brand"><span class="dot"></span>管理后台</div><nav><a href="/">概览</a><a href="/users" class="active">用户</a></nav></header>
<div class="container">
<h1>用户管理</h1>
<div class="card"><table><thead><tr><th>ID</th><th>用户名</th><th>邮箱</th><th>状态</th><th>操作</th></tr></thead><tbody>{rows}</tbody></table></div>
</div>
<script>
async function toggleUser(id) {{
  var res = await fetch('/admin/users/toggle', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{user_id:id}})}});
  var data = await res.json();
  if(data && data.ok) location.reload();
}}
</script>
</body></html>"""


# ═══════════════════════════════════════════════════
# API 端点（复用主站 admin 模块）
# ═══════════════════════════════════════════════════

@app.get("/stats")
async def admin_stats_api(days: int = 7):
    from src.admin.activity import ActivityTracker
    return ActivityTracker().stats(days=days)


@app.get("/activity")
async def admin_activity_api(limit: int = 200):
    from src.admin.activity import ActivityTracker
    return ActivityTracker().query(limit=min(limit, 500))


@app.post("/users/toggle")
async def admin_toggle_user(payload: dict):
    from src.admin.auth_models import User
    from src.storage.database import db
    user_id = int(payload.get("user_id") or 0)
    session = db.get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return {"ok": False, "error": "用户不存在"}
        user.is_active = not user.is_active
        session.commit()
        return {"ok": True, "is_active": user.is_active}
    finally:
        session.close()


@app.post("/suspend")
async def admin_suspend(payload: dict):
    from src.admin.access_control import AccessControl
    ac = AccessControl()
    return ac.suspend(str(payload.get("identifier", "")), str(payload.get("reason", "")))


@app.post("/unsuspend")
async def admin_unsuspend(payload: dict):
    from src.admin.access_control import AccessControl
    return AccessControl().unsuspend(str(payload.get("identifier", "")))


@app.get("/suspended")
async def admin_suspended():
    from src.admin.access_control import AccessControl
    return AccessControl().list_suspended()


# ═══════════════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")
