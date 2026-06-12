"""独立管理后台 — 经典侧边栏布局

运行于独立端口，公网用户不可见。
布局：登录页 → 左侧功能列表 + 右侧内容区 + 顶部用户栏
"""

from __future__ import annotations

import hashlib
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI(title="", docs_url=None, redoc_url=None, openapi_url=None)

# ═══════════════════════════════════════════════════
# 简易会话管理（单管理员场景）
# ═══════════════════════════════════════════════════

ADMIN_CREDENTIALS = {"admin": "admin123"}  # 第一版写死，后续改为数据库
_sessions: dict[str, str] = {}


def _session_id() -> str:
    return hashlib.sha256(str(random.getrandbits(256)).encode()).hexdigest()[:32]


def _check_login(request: Request) -> str | None:
    token = request.cookies.get("admin_token", "")
    return _sessions.get(token)


# ═══════════════════════════════════════════════════
# CSS — 经典侧边栏管理后台主题
# ═══════════════════════════════════════════════════

CSS = r"""
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#f5f6fa;--card:#fff;--sidebar:#1e293b;--sidebar-hover:#334155;
  --sidebar-active:#3b82f6;--text:#1e293b;--text-sidebar:#cbd5e1;
  --muted:#64748b;--border:#e2e8f0;--accent:#3b82f6;--green:#10b981;
  --red:#ef4444;--orange:#f59e0b;--radius:8px;--font:system-ui,-apple-system,sans-serif;
}
body{font-family:var(--font);font-size:14px;color:var(--text);background:var(--bg);line-height:1.6}
a{color:var(--accent);text-decoration:none}

/* ── 登录页 ── */
.login-page{display:flex;align-items:center;justify-content:center;min-height:100vh;background:linear-gradient(135deg,#0f172a 0%,#1e293b 50%,#0f172a 100%)}
.login-box{background:var(--card);border-radius:12px;padding:40px 36px;width:380px;max-width:90vw;box-shadow:0 20px 60px rgba(0,0,0,.3)}
.login-box h1{font-size:22px;font-weight:700;margin-bottom:4px;text-align:center}
.login-box .sub{font-size:13px;color:var(--muted);text-align:center;margin-bottom:28px}
.login-box .field{margin-bottom:18px}
.login-box label{display:block;font-size:13px;font-weight:500;margin-bottom:6px;color:var(--text)}
.login-box input{width:100%;padding:10px 12px;border:1px solid var(--border);border-radius:var(--radius);font-size:14px;font-family:var(--font);transition:border-color .15s}
.login-box input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(59,130,246,.15)}
.login-box .btn{width:100%;padding:11px;background:var(--accent);color:#fff;border:none;border-radius:var(--radius);font-size:14px;font-weight:600;cursor:pointer;transition:background .15s}
.login-box .btn:hover{background:#2563eb}
.login-box .error{color:var(--red);font-size:12px;text-align:center;margin-top:12px}
.login-box .captcha-row{display:flex;gap:10px}
.login-box .captcha-row input{flex:1}
.login-box .captcha-box{background:#f1f5f9;padding:8px 14px;border-radius:var(--radius);font-family:monospace;font-size:18px;letter-spacing:4px;font-weight:700;color:#334155;cursor:pointer;user-select:none;line-height:1.4;min-width:90px;text-align:center}

/* ── 管理后台布局 ── */
.layout{display:flex;min-height:100vh}
.sidebar{width:220px;background:var(--sidebar);display:flex;flex-direction:column;position:fixed;top:0;left:0;bottom:0;z-index:10}
.sidebar .brand{padding:20px 20px 16px;font-size:15px;font-weight:700;color:#fff;border-bottom:1px solid rgba(255,255,255,.08);display:flex;align-items:center;gap:8px}
.sidebar .brand .dot{width:8px;height:8px;border-radius:50%;background:var(--green)}
.sidebar nav{flex:1;padding:12px 8px;overflow-y:auto}
.sidebar nav a{display:flex;align-items:center;gap:10px;padding:10px 14px;border-radius:var(--radius);color:var(--text-sidebar);font-size:13px;margin-bottom:2px;transition:all .15s;font-weight:400}
.sidebar nav a:hover{background:var(--sidebar-hover);color:#fff}
.sidebar nav a.active{background:var(--sidebar-active);color:#fff;font-weight:500}
.sidebar nav a .icon{font-size:16px;width:20px;text-align:center;flex-shrink:0}
.main{margin-left:220px;flex:1;min-width:0;display:flex;flex-direction:column}
.topbar{display:flex;align-items:center;justify-content:space-between;padding:12px 24px;background:var(--card);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:5}
.topbar .title{font-weight:600;font-size:15px}
.topbar .user{display:flex;align-items:center;gap:12px;font-size:13px}
.topbar .user .avatar{width:32px;height:32px;border-radius:50%;background:var(--accent);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px}
.topbar .logout{color:var(--muted);cursor:pointer;font-size:12px;padding:4px 10px;border:1px solid var(--border);border-radius:6px;background:none;transition:all .15s}
.topbar .logout:hover{color:var(--red);border-color:var(--red)}
.content{padding:24px;flex:1}

/* ── 组件 ── */
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:20px;margin-bottom:20px}
.card h2{font-size:16px;font-weight:600;margin-bottom:16px}
.card h3{font-size:14px;font-weight:600;margin-bottom:12px}
.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px}
.grid2{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}
.stat{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:18px}
.stat .label{font-size:12px;color:var(--muted);letter-spacing:.02em}
.stat .value{font-size:28px;font-weight:700;margin-top:4px;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.stat .sub{font-size:11px;color:var(--muted);margin-top:4px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;padding:10px 12px;color:var(--muted);font-weight:500;font-size:11px;border-bottom:2px solid var(--border);letter-spacing:.02em;text-transform:uppercase}
td{padding:10px 12px;border-bottom:1px solid var(--border)}
tr:hover{background:#f8fafc}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:500}
.badge-success{background:#d1fae5;color:#065f46}
.badge-danger{background:#fee2e2;color:#991b1b}
.badge-info{background:#dbeafe;color:#1e40af}
.badge-warning{background:#fef3c7;color:#92400e}
.btn{padding:7px 16px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);cursor:pointer;font-size:13px;font-family:var(--font);transition:all .15s;font-weight:500}
.btn:hover{background:#f1f5f9}
.btn-primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.btn-primary:hover{background:#2563eb}
.btn-danger{color:var(--red);border-color:#fecaca}
.btn-danger:hover{background:#fef2f2}
.bar-track{height:22px;background:#f1f5f9;border-radius:4px;overflow:hidden;margin-top:4px}
.bar-fill{height:100%;background:var(--accent);border-radius:4px;transition:width .3s}
.flex-between{display:flex;justify-content:space-between;align-items:center}
.text-muted{color:var(--muted);font-size:12px}
.mt{margin-top:16px}.mb{margin-bottom:16px}
@media(max-width:768px){.sidebar{width:56px}.sidebar .brand{font-size:0;padding:16px 12px}.sidebar nav a{justify-content:center;padding:10px}.sidebar nav a .label{display:none}.main{margin-left:56px}.grid4{grid-template-columns:repeat(2,1fr)}.grid2{grid-template-columns:1fr}}
"""


# ═══════════════════════════════════════════════════
# 模板渲染工具
# ═══════════════════════════════════════════════════

def _base(section: str, title: str, body: str) -> str:
    nav_items = [
        ("/dashboard", "📊", "概览", "dashboard"),
        ("/users", "👥", "用户管理", "users"),
        ("/activity", "📋", "活动日志", "activity"),
        ("/bans", "🚫", "封禁管理", "bans"),
    ]
    nav_html = "".join(
        f'<a href="{href}" class="{"active" if sec == section else ""}"><span class="icon">{icon}</span><span class="label">{label}</span></a>'
        for href, icon, label, sec in nav_items
    )
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>管理后台 · {title}</title><style>{CSS}</style></head><body>
<div class="layout">
<aside class="sidebar"><div class="brand"><span class="dot"></span>管理后台</div><nav>{nav_html}</nav></aside>
<div class="main"><div class="topbar"><span class="title">{title}</span><div class="user"><span class="avatar">A</span><span>admin</span><a class="logout" href="/logout">登出</a></div></div><div class="content">{body}</div></div></div></body></html>"""


# ═══════════════════════════════════════════════════
# 路由
# ═══════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if not _check_login(request):
        return _login_page()
    return RedirectResponse("/dashboard")


def _login_page(error: str = "") -> HTMLResponse:
    a, b = random.randint(1, 20), random.randint(1, 20)
    captcha_answer = str(a + b)
    captcha_token = hashlib.sha256(captcha_answer.encode()).hexdigest()[:16]
    _sessions[f"captcha_{captcha_token}"] = captcha_answer

    error_html = f'<div class="error">{error}</div>' if error else ""
    return HTMLResponse(f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>管理后台 · 登录</title><style>{CSS}</style></head><body>
<div class="login-page"><div class="login-box">
<h1>管理后台</h1><div class="sub">请输入管理员账号登录</div>
<form method="post" action="/login">
<div class="field"><label>账号</label><input name="username" placeholder="管理员账号" required autofocus></div>
<div class="field"><label>密码</label><input name="password" type="password" placeholder="管理员密码" required></div>
<div class="field"><label>验证码：{a} + {b} = ?</label><div class="captcha-row"><input name="captcha" placeholder="计算结果" required><span class="captcha-box" onclick="location.reload()">{a} + {b}</span></div></div>
<input type="hidden" name="captcha_token" value="{captcha_token}">
{error_html}
<button class="btn" style="margin-top:8px">登录</button>
</form></div></div></body></html>""")


@app.post("/login")
async def login(request: Request, response: Response):
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")
    captcha_input = form.get("captcha", "")
    captcha_token = form.get("captcha_token", "")

    expected = _sessions.pop(f"captcha_{captcha_token}", None)
    if expected is None or captcha_input.strip() != expected:
        return _login_page("验证码错误，请重新计算")

    if username not in ADMIN_CREDENTIALS or ADMIN_CREDENTIALS[username] != password:
        return _login_page("账号或密码错误")

    token = _session_id()
    _sessions[token] = username
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie("admin_token", token, httponly=True, samesite="lax", max_age=7200)
    return response


@app.get("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("admin_token", "")
    _sessions.pop(token, None)
    response = RedirectResponse("/")
    response.delete_cookie("admin_token")
    return response


# ── 概览 ──

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not _check_login(request):
        return _login_page()
    from src.admin.activity import ActivityTracker
    stats = ActivityTracker().stats(days=7)
    total = stats.get("total_events", 0) or 1
    hourly = stats.get("hourly_activity", {})
    peak_hour = max(hourly.items(), key=lambda x: x[1]) if hourly else ("-", 0)

    action_labels = {
        "page_view": "浏览", "config_change": "修改配置", "task_execute": "执行任务",
        "task_seed": "扫描任务", "chat_query": "AI 问答",
        "observation_add": "添加观察", "observation_remove": "移除观察",
    }
    bars = ""
    for k, v in sorted(stats["actions_by_type"].items(), key=lambda x: -x[1])[:6]:
        pct = min(round(v / total * 100, 1), 100)
        bars += f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:6px'><span style='font-size:12px;color:var(--muted);width:66px;text-align:right'>{action_labels.get(k,k)}</span><div style='flex:1' class='bar-track'><div class='bar-fill' style='width:{pct}%'></div></div><span style='font-size:11px;color:var(--muted);width:40px'>{v}</span></div>"

    events = ""
    for e in ActivityTracker().query(limit=8):
        al = action_labels.get(e.get("action", ""), e.get("action", ""))
        ts = e.get("timestamp", "")[-8:] or ""
        events += f"<tr><td>{al}</td><td style='color:var(--muted)'>{e.get('path','')}</td><td>{e.get('ip_prefix','')}</td><td style='color:var(--muted)'>{ts}</td></tr>"

    return HTMLResponse(_base("dashboard", "系统概览", f"""
<div class="grid4">
<div class="stat"><div class="label">今日操作</div><div class="value">{total}</div><div class="sub">过去 7 天累计</div></div>
<div class="stat"><div class="label">活跃来源</div><div class="value">{stats['unique_ip_prefixes']}</div><div class="sub">独立网络前缀</div></div>
<div class="stat"><div class="label">高峰时段</div><div class="value" style="font-size:22px">{peak_hour[0]}:00</div><div class="sub">UTC 时间</div></div>
<div class="stat"><div class="label">数据窗口</div><div class="value" style="font-size:22px">7 天</div><div class="sub">最近统计区间</div></div>
</div>
<div class="grid2">
<div class="card"><h2>操作类型分布</h2>{bars or '<span class="text-muted">暂无数据</span>'}</div>
<div class="card"><h2>最近活动记录</h2><table><thead><tr><th>操作</th><th>路径</th><th>来源</th><th>时间</th></tr></thead><tbody>{events or '<tr><td colspan="4" class="text-muted">暂无记录</td></tr>'}</tbody></table></div>
</div>"""))


# ── 用户管理 ──

@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    if not _check_login(request):
        return _login_page()
    from src.admin.auth_models import User
    from src.storage.database import db
    session = db.get_session()
    users = session.query(User).order_by(User.id.desc()).all()
    session.close()
    rows = ""
    for u in users:
        rows += f"""<tr>
<td>{u.id}</td><td><b>{u.username}</b></td><td style="color:var(--muted)">{u.email[:3] + "****"}</td>
<td>{'<span class="badge badge-info">管理员</span>' if u.is_superuser else ''}</td>
<td><span class="badge {'badge-success' if u.is_active else 'badge-danger'}">{'正常' if u.is_active else '已停用'}</span></td>
<td><button class="btn {'btn-danger' if u.is_active else 'btn-primary'}" onclick="toggleUser({u.id})">{'停用' if u.is_active else '启用'}</button></td>
</tr>"""
    return HTMLResponse(_base("users", "用户管理", f"""<div class="card"><div class="flex-between mb"><h2 style="margin:0">用户列表</h2></div>
<table><thead><tr><th>ID</th><th>用户名</th><th>邮箱</th><th>角色</th><th>状态</th><th>操作</th></tr></thead><tbody>{rows or '<tr><td colspan="6" class="text-muted">暂无用户</td></tr>'}</tbody></table></div>
<script>async function toggleUser(id){{var r=await fetch('/users/toggle',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{user_id:id}})}});if(r.ok)location.reload()}}</script>"""))


# ── 活动日志 ──

@app.get("/activity", response_class=HTMLResponse)
async def activity_page(request: Request):
    if not _check_login(request):
        return _login_page()
    from src.admin.activity import ActivityTracker
    action_labels = {"page_view":"浏览","config_change":"修改配置","task_execute":"执行任务","task_seed":"扫描任务","chat_query":"AI 问答","observation_add":"添加观察","observation_remove":"移除观察","governance_acknowledge":"接受风险","governance_revoke":"撤销接受"}
    rows = ""
    for e in ActivityTracker().query(limit=100):
        al = action_labels.get(e.get("action",""), e.get("action",""))
        ts = e.get("timestamp","") or ""
        rows += f"<tr><td><span class='badge badge-info'>{al}</span></td><td style='color:var(--muted)'>{e.get('path','')}</td><td>{e.get('ip_prefix','')}</td><td style='color:var(--muted);font-size:12px'>{ts}</td></tr>"
    return HTMLResponse(_base("activity", "活动日志", f"""<div class="card"><h2>用户操作记录</h2><table><thead><tr><th>操作</th><th>路径</th><th>来源 IP 前缀</th><th>时间</th></tr></thead><tbody>{rows or '<tr><td colspan="4" class="text-muted">暂无记录</td></tr>'}</tbody></table></div>"""))


# ── 封禁管理 ──

@app.get("/bans", response_class=HTMLResponse)
async def bans_page(request: Request):
    if not _check_login(request):
        return _login_page()
    from src.admin.access_control import AccessControl
    ac = AccessControl()
    suspended = ac.list_suspended()
    rows = ""
    for s in suspended:
        rows += f"""<tr><td>{s.get('identifier','')}</td><td style="color:var(--muted)">{s.get('reason','')}</td><td style="font-size:12px;color:var(--muted)">{s.get('suspended_at','')[:16]}</td>
<td><button class="btn btn-primary" onclick="unsuspend('{s.get('identifier','')}')">解除</button></td></tr>"""
    return HTMLResponse(_base("bans", "封禁管理", f"""<div class="card"><div class="flex-between mb"><h2 style="margin:0">封禁列表</h2></div>
<table><thead><tr><th>用户名/IP 前缀</th><th>原因</th><th>封禁时间</th><th>操作</th></tr></thead><tbody>{rows or '<tr><td colspan="4" class="text-muted">暂无封禁记录</td></tr>'}</tbody></table></div>
<div class="card mt"><h2>新增封禁</h2>
<div style="display:flex;gap:10px"><input id="ban-ident" placeholder="用户名或 IP 前缀 (如 192.168)" style="flex:1;padding:10px;border:1px solid var(--border);border-radius:var(--radius);font-size:14px"><input id="ban-reason" placeholder="封禁原因" style="flex:1;padding:10px;border:1px solid var(--border);border-radius:var(--radius);font-size:14px"><button class="btn btn-danger" onclick="doSuspend()">封禁</button></div></div>
<script>
async function doSuspend(){{var i=document.getElementById('ban-ident').value.trim();var r=document.getElementById('ban-reason').value.trim();if(!i)return;await fetch('/suspend',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{identifier:i,reason:r}})}});location.reload()}}
async function unsuspend(id){{await fetch('/unsuspend',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{identifier:id}})}});location.reload()}}
</script>"""))


# ═══════════════════════════════════════════════════
# API 端点
# ═══════════════════════════════════════════════════

@app.get("/stats")
async def stats_api(days: int = 7):
    from src.admin.activity import ActivityTracker
    return ActivityTracker().stats(days=days)


@app.post("/users/toggle")
async def toggle_user(payload: dict):
    from src.admin.auth_models import User
    from src.storage.database import db
    uid = int(payload.get("user_id") or 0)
    session = db.get_session()
    try:
        u = session.query(User).filter(User.id == uid).first()
        if not u: return {"ok": False}
        u.is_active = not u.is_active
        session.commit()
        return {"ok": True}
    finally:
        session.close()


@app.post("/suspend")
async def suspend(payload: dict):
    from src.admin.access_control import AccessControl
    return AccessControl().suspend(str(payload.get("identifier","")), str(payload.get("reason","")))


@app.post("/unsuspend")
async def unsuspend(payload: dict):
    from src.admin.access_control import AccessControl
    return AccessControl().unsuspend(str(payload.get("identifier","")))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")
