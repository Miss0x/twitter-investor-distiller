"""独立管理后台 — 经典侧边栏布局

运行于独立端口，公网用户不可见。
布局：登录页 → 左侧功能列表 + 右侧内容区 + 顶部用户栏
"""

from __future__ import annotations

import html
import hashlib
import os
import secrets
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI(title="", docs_url=None, redoc_url=None, openapi_url=None)

# ═══════════════════════════════════════════════════
# 会话与认证
# ═══════════════════════════════════════════════════

_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
_PASSWORD_SALT = secrets.token_hex(16)


def _hash_password(pw: str) -> str:
    return hashlib.sha256((_PASSWORD_SALT + pw).encode()).hexdigest()


def _verify_password(pw: str, stored: str) -> bool:
    return secrets.compare_digest(_hash_password(pw), stored)


_ADMIN_HASH = _hash_password(_ADMIN_PASSWORD)

_sessions: dict[str, tuple[str, float]] = {}  # token → (username, last_seen_ts)
_captchas: dict[str, tuple[str, float]] = {}   # token → (answer, created_ts)
_failures: dict[str, list[float]] = {}          # ip → [fail_timestamps]

SESSION_MAX_AGE = 7200  # 2 小时
CAPTCHA_MAX_AGE = 300   # 5 分钟
MAX_FAILURES = 5        # 5 次失败锁 15 分钟
FAILURE_WINDOW = 900    # 15 分钟窗口


def _session_id() -> str:
    return secrets.token_hex(32)


def _check_login(request: Request) -> str | None:
    """验证登录状态，返回用户名或 None。同时清理过期 token。"""
    token = request.cookies.get("admin_token", "")
    entry = _sessions.get(token)
    if entry is None:
        return None
    username, last_seen = entry
    if time.time() - last_seen > SESSION_MAX_AGE:
        _sessions.pop(token, None)
        return None
    _sessions[token] = (username, time.time())  # 刷新 last_seen
    # 清理过期 session
    now = time.time()
    expired = [t for t, (_, ts) in _sessions.items() if now - ts > SESSION_MAX_AGE]
    for t in expired:
        _sessions.pop(t, None)
    return username


def _check_login_or_401(request: Request) -> str:
    """验证登录，未登录返回 401。"""
    username = _check_login(request)
    if username is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return username


def _check_rate_limit(ip: str) -> str | None:
    """检查登录频率限制，返回错误信息或 None。"""
    now = time.time()
    stamps = [t for t in _failures.get(ip, []) if now - t < FAILURE_WINDOW]
    _failures[ip] = stamps
    if len(stamps) >= MAX_FAILURES:
        return f"登录失败次数过多，请 {int((FAILURE_WINDOW - (now - stamps[0])) / 60)} 分钟后再试"
    return None


def _escape(text: str) -> str:
    return html.escape(str(text))


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
<div class="main"><div class="topbar"><span class="title">{title}</span><div class="user"><span class="avatar">A</span><span>admin</span><form method="post" action="/logout" style="display:inline"><button class="logout" type="submit">登出</button></form></div></div><div class="content">{body}</div></div></div></body></html>"""


# ═══════════════════════════════════════════════════
# 路由
# ═══════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if not _check_login(request):
        return _login_page()
    return RedirectResponse("/dashboard")


def _login_page(error: str = "") -> HTMLResponse:
    # 清理过期 captcha
    now = time.time()
    expired = [t for t, (_, ts) in _captchas.items() if now - ts > CAPTCHA_MAX_AGE]
    for t in expired:
        _captchas.pop(t, None)

    a, b = secrets.randbelow(20) + 1, secrets.randbelow(20) + 1
    captcha_answer = str(a + b)
    captcha_token = secrets.token_hex(16)
    _captchas[captcha_token] = (captcha_answer, now)

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
    client_ip = request.client.host if request.client else "unknown"

    # 频率检查
    rate_error = _check_rate_limit(client_ip)
    if rate_error:
        return _login_page(rate_error)

    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")
    captcha_input = form.get("captcha", "")
    captcha_token = form.get("captcha_token", "")

    # 验证验证码
    expected_entry = _captchas.pop(captcha_token, None)
    if expected_entry is None or captcha_input.strip() != expected_entry[0]:
        return _login_page("验证码错误，请重新计算")

    # 验证密码（恒定时间比较，防时序攻击）
    if username != "admin" or not _verify_password(password, _ADMIN_HASH):
        stamps = _failures.get(client_ip, [])
        stamps.append(time.time())
        _failures[client_ip] = stamps
        return _login_page("账号或密码错误")

    token = _session_id()
    _sessions[token] = (username, time.time())
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie("admin_token", token, httponly=True, samesite="strict", max_age=SESSION_MAX_AGE)
    return response


@app.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("admin_token", "")
    _sessions.pop(token, None)
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("admin_token")
    return response


# ── 概览 ──

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    _check_login_or_401(request)
    try:
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
            bars += f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:6px'><span style='font-size:12px;color:var(--muted);width:66px;text-align:right'>{_escape(action_labels.get(k,k))}</span><div style='flex:1' class='bar-track'><div class='bar-fill' style='width:{pct}%'></div></div><span style='font-size:11px;color:var(--muted);width:40px'>{v}</span></div>"

        events = ""
        for e in ActivityTracker().query(limit=8):
            al = action_labels.get(e.get("action", ""), e.get("action", ""))
            ts = e.get("timestamp", "")[-8:] or ""
            events += f"<tr><td>{_escape(al)}</td><td style='color:var(--muted)'>{_escape(e.get('path',''))}</td><td>{_escape(e.get('ip_prefix',''))}</td><td style='color:var(--muted)'>{_escape(ts)}</td></tr>"

        return HTMLResponse(_base("dashboard", "系统概览", f"""
<div class="grid4">
<div class="stat"><div class="label">今日操作</div><div class="value">{total}</div><div class="sub">过去 7 天累计</div></div>
<div class="stat"><div class="label">活跃来源</div><div class="value">{stats['unique_ip_prefixes']}</div><div class="sub">独立网络前缀</div></div>
<div class="stat"><div class="label">高峰时段</div><div class="value" style="font-size:22px">{_escape(peak_hour[0])}:00</div><div class="sub">UTC 时间</div></div>
<div class="stat"><div class="label">数据窗口</div><div class="value" style="font-size:22px">7 天</div><div class="sub">最近统计区间</div></div>
</div>
<div class="grid2">
<div class="card"><h2>操作类型分布</h2>{bars or '<span class="text-muted">暂无数据</span>'}</div>
<div class="card"><h2>最近活动记录</h2><table><thead><tr><th>操作</th><th>路径</th><th>来源</th><th>时间</th></tr></thead><tbody>{events or '<tr><td colspan="4" class="text-muted">暂无记录</td></tr>'}</tbody></table></div>
</div>"""))
    except Exception as exc:
        return HTMLResponse(_base("dashboard", "系统概览", f'<div class="card"><span class="text-muted">加载统计数据失败: {_escape(str(exc))}</span></div>'))


# ── 用户管理 ──

@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    _check_login_or_401(request)
    try:
        from src.admin.auth_models import User
        from src.storage.database import db
        session = db.get_session()
        users = session.query(User).order_by(User.id.desc()).all()
        session.close()
        rows = ""
        for u in users:
            rows += f"""<tr>
<td>{u.id}</td><td><b>{_escape(u.username)}</b></td><td style="color:var(--muted)">{_escape(u.email[:3])}****</td>
<td>{'<span class="badge badge-info">管理员</span>' if u.is_superuser else ''}</td>
<td><span class="badge {'badge-success' if u.is_active else 'badge-danger'}">{'正常' if u.is_active else '已停用'}</span></td>
<td><button class="btn {'btn-danger' if u.is_active else 'btn-primary'}" onclick="toggleUser({u.id})">{'停用' if u.is_active else '启用'}</button></td>
</tr>"""
        return HTMLResponse(_base("users", "用户管理", f"""<div class="card"><div class="flex-between mb"><h2 style="margin:0">用户列表</h2></div>
<table><thead><tr><th>ID</th><th>用户名</th><th>邮箱</th><th>角色</th><th>状态</th><th>操作</th></tr></thead><tbody>{rows or '<tr><td colspan="6" class="text-muted">暂无用户</td></tr>'}</tbody></table></div>
<script>async function toggleUser(id){{var r=await fetch('/users/toggle',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{user_id:id}})}});if(r.ok)location.reload()}}</script>"""))
    except Exception as exc:
        return HTMLResponse(_base("users", "用户管理", f'<div class="card"><span class="text-muted">加载失败: {_escape(str(exc))}</span></div>'))


# ── 活动日志 ──

@app.get("/activity", response_class=HTMLResponse)
async def activity_page(request: Request):
    _check_login_or_401(request)
    try:
        from src.admin.activity import ActivityTracker
        action_labels = {"page_view":"浏览","config_change":"修改配置","task_execute":"执行任务","task_seed":"扫描任务","chat_query":"AI 问答","observation_add":"添加观察","observation_remove":"移除观察","governance_acknowledge":"接受风险","governance_revoke":"撤销接受"}
        rows = ""
        for e in ActivityTracker().query(limit=100):
            al = action_labels.get(e.get("action",""), e.get("action",""))
            ts = e.get("timestamp","") or ""
            rows += f"<tr><td><span class='badge badge-info'>{_escape(al)}</span></td><td style='color:var(--muted)'>{_escape(e.get('path',''))}</td><td>{_escape(e.get('ip_prefix',''))}</td><td style='color:var(--muted);font-size:12px'>{_escape(ts)}</td></tr>"
        return HTMLResponse(_base("activity", "活动日志", f"""<div class="card"><h2>用户操作记录</h2><table><thead><tr><th>操作</th><th>路径</th><th>来源 IP 前缀</th><th>时间</th></tr></thead><tbody>{rows or '<tr><td colspan="4" class="text-muted">暂无记录</td></tr>'}</tbody></table></div>"""))
    except Exception as exc:
        return HTMLResponse(_base("activity", "活动日志", f'<div class="card"><span class="text-muted">加载失败: {_escape(str(exc))}</span></div>'))




# ── 封禁管理 ──

@app.get("/bans", response_class=HTMLResponse)
async def bans_page(request: Request):
    _check_login_or_401(request)
    try:
        from src.admin.access_control import AccessControl
        ac = AccessControl()
        suspended = ac.list_suspended()
        rows = ""
        for s in suspended:
            ident = _escape(s.get('identifier',''))
            reason = _escape(s.get('reason',''))
            ts = _escape((s.get('suspended_at','') or '')[:16])
            rows += f"""<tr><td>{ident}</td><td style="color:var(--muted)">{reason}</td><td style="font-size:12px;color:var(--muted)">{ts}</td>
<td><button class="btn btn-primary" onclick="unsuspend('{ident}')">解除</button></td></tr>"""
        return HTMLResponse(_base("bans", "封禁管理", f"""<div class="card"><div class="flex-between mb"><h2 style="margin:0">封禁列表</h2></div>
<table><thead><tr><th>用户名/IP 前缀</th><th>原因</th><th>封禁时间</th><th>操作</th></tr></thead><tbody>{rows or '<tr><td colspan="4" class="text-muted">暂无封禁记录</td></tr>'}</tbody></table></div>
<div class="card mt"><h2>新增封禁</h2>
<div style="display:flex;gap:10px"><input id="ban-ident" placeholder="用户名或 IP 前缀 (如 192.168)" style="flex:1;padding:10px;border:1px solid var(--border);border-radius:var(--radius);font-size:14px"><input id="ban-reason" placeholder="封禁原因" style="flex:1;padding:10px;border:1px solid var(--border);border-radius:var(--radius);font-size:14px"><button class="btn btn-danger" onclick="doSuspend()">封禁</button></div></div>
<script>
async function doSuspend(){{var i=document.getElementById('ban-ident').value.trim();var r=document.getElementById('ban-reason').value.trim();if(!i)return;await fetch('/suspend',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{identifier:i,reason:r}})}});location.reload()}}
async function unsuspend(id){{await fetch('/unsuspend',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{identifier:id}})}});location.reload()}}
</script>"""))
    except Exception as exc:
        return HTMLResponse(_base("bans", "封禁管理", f'<div class="card"><span class="text-muted">加载失败: {_escape(str(exc))}</span></div>'))


# ═══════════════════════════════════════════════════
# API 端点（全部需要登录）
# ═══════════════════════════════════════════════════

@app.get("/stats")
async def stats_api(request: Request, days: int = 7):
    _check_login_or_401(request)
    from src.admin.activity import ActivityTracker
    return ActivityTracker().stats(days=days)


@app.post("/users/toggle")
async def toggle_user(request: Request, payload: dict):
    _check_login_or_401(request)
    from src.admin.auth_models import User
    from src.storage.database import db
    uid = int(payload.get("user_id") or 0)
    session = db.get_session()
    try:
        u = session.query(User).filter(User.id == uid).first()
        if not u:
            return {"ok": False}
        u.is_active = not u.is_active
        session.commit()
        return {"ok": True}
    finally:
        session.close()


@app.post("/suspend")
async def suspend(request: Request, payload: dict):
    _check_login_or_401(request)
    from src.admin.access_control import AccessControl
    return AccessControl().suspend(str(payload.get("identifier","")), str(payload.get("reason","")))


@app.post("/unsuspend")
async def unsuspend(request: Request, payload: dict):
    _check_login_or_401(request)
    from src.admin.access_control import AccessControl
    return AccessControl().unsuspend(str(payload.get("identifier","")))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")
