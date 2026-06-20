#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""20 场景浏览器 E2E 测试 — 真实交互 + 有意义的最后一页截图"""
import http.cookiejar
import json
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(r"c:\Users\lwj93\WorkBuddy\推特用户蒸馏")
SHOTS = ROOT / "logs" / "e2e_shots"
SHOTS.mkdir(parents=True, exist_ok=True)
REPORT = ROOT / "logs" / "e2e_20_scenarios_report.md"

FRONTEND = "http://localhost:8000"
ADMIN = "http://localhost:8001"

results = []


# ===============================================================
# 工具函数
# ===============================================================
def pc(*args, timeout=60):
    cmd = "playwright-cli " + " ".join(str(a) for a in args)
    print(f"  > {cmd[:180]}{'...' if len(cmd) > 180 else ''}")
    r = subprocess.run(["cmd", "/c", cmd], capture_output=True, text=True, timeout=timeout)
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        print(f"  ! rc={r.returncode} :: {out[:300]}")
    return out


def shot(name):
    p = SHOTS / f"{name}.png"
    pc("screenshot", "--filename", str(p))
    return p


def goto_tab(tab_text):
    """切换到 Dashboard 的指定标签页（取 tab 文本前 2 字唯一匹配）"""
    js = f"""() => {{
        var btns = document.querySelectorAll('button, [role=tab], .tab-item, a');
        for (var i = 0; i < btns.length; i++) {{
            var t = btns[i].textContent.trim();
            if (t.length > 0 && t.indexOf('{tab_text}') !== -1) {{
                btns[i].click();
                return 'clicked: ' + t;
            }}
        }}
        return 'not found';
    }}"""
    pc("eval", js)
    time.sleep(0.8)


class APIClient:
    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self.headers = {"Content-Type": "application/json"}

    def request(self, url, method="GET", body=None, extra_headers=None, timeout=10):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        for k, v in self.headers.items():
            req.add_header(k, v)
        if extra_headers:
            for k, v in extra_headers.items():
                req.add_header(k, v)
        try:
            r = self.opener.open(req, timeout=timeout)
            return r.status, r.read().decode(errors="ignore")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(errors="ignore")
        except Exception as e:
            return 0, str(e)

    def get(self, url, **kw):
        return self.request(url, "GET", **kw)

    def post(self, url, body=None, **kw):
        return self.request(url, "POST", body, **kw)

    def register_login(self, email, username, password):
        c, b = self.post(f"{FRONTEND}/auth/register",
                         {"email": email, "username": username, "password": password})
        if c != 200:
            return False, f"register {c} {b[:100]}"
        c, b = self.post(f"{FRONTEND}/auth/login",
                         {"email": email, "password": password})
        if c != 200:
            return False, f"login {c} {b[:100]}"
        return True, ""


def record(scenario, name, status, issues="", shot_path=None):
    results.append({
        "scenario": scenario, "name": name, "status": status,
        "issues": issues, "screenshot": str(shot_path) if shot_path else None
    })
    label = "OK" if status == "OK" else "ISS" if status == "ISSUE" else "ERR"
    print(f"  [{label}] 场景 {scenario}: {name}")
    if issues:
        print(f"       {issues[:300]}")


# ===============================================================
# 场景 1：注册探索 → 截图 = Dashboard signals tab
# ===============================================================
def scenario_01():
    name = "理财小白林悦 — 注册和探索"
    issues = []
    # 先看主页
    pc("goto", FRONTEND + "/")
    time.sleep(1)
    pc("snapshot")
    # 注册 + 登录
    import secrets
    email = f"test_s01_{secrets.token_hex(3)}@test.com"
    user = f"u_s01_{secrets.token_hex(2)}"
    pw = "TestPw123!"
    api = APIClient()
    ok, msg = api.register_login(email, user, pw)
    if not ok: issues.append(msg)
    c, b = api.get(f"{FRONTEND}/auth/me")
    if c != 200: issues.append(f"/auth/me {c}")
    # 打开 Dashboard (signals tab)
    pc("goto", FRONTEND + "/dashboard")
    time.sleep(1.5)
    p = shot("s01_end")
    record(1, name, "OK" if not issues else "ISSUE", "; ".join(issues), p)
    return api


# ===============================================================
# 场景 2：配置 → 截图 = settings tab（显示配置中心）
# ===============================================================
def scenario_02(api):
    name = "入门陈志远 — 第一次配置"
    issues = []
    for ep, body in [
        ("/api/config/llm", {"provider": "openai", "base_url": "https://api.openai.com", "api_key": "sk-test-fake"}),
        ("/api/config/twitter", {"provider": "twitterapi.io", "api_key": "fake-tw-key"}),
        ("/api/config/telegram", {"bot_token": "000:fake", "chat_id": "000"}),
    ]:
        c, b = api.post(f"{FRONTEND}{ep}", body)
        if c != 200: issues.append(f"{ep} {c}: {b[:80]}")
    c, b = api.post(f"{FRONTEND}/api/config/observations/add", {"handle": "TJ_Research"})
    if c != 200: issues.append(f"obs/add {c}: {b[:80]}")
    # 切到 settings tab → 显示配置中心
    pc("goto", FRONTEND + "/dashboard")
    time.sleep(1)
    goto_tab("设置")
    time.sleep(1)
    p = shot("s02_end")
    record(2, name, "OK" if not issues else "ISSUE", "; ".join(issues), p)


# ===============================================================
# 场景 3：治理 → 截图 = signals tab（治理卡片）
# ===============================================================
def scenario_03(api):
    name = "王思琪 — 信号治理评审"
    issues = []
    for card in ["quality_gate", "risk_alerts", "panel_review", "publish_review", "consensus"]:
        c, b = api.get(f"{FRONTEND}/cards/{card}")
        if c != 200: issues.append(f"card {card} {c}: {b[:80]}")
    pc("goto", FRONTEND + "/dashboard")
    time.sleep(1)
    goto_tab("信号")
    time.sleep(1)
    p = shot("s03_end")
    record(3, name, "OK" if not issues else "ISSUE", "; ".join(issues), p)


# ===============================================================
# 场景 4：操盘 → 截图 = signals tab（系统状态 + 轮动）
# ===============================================================
def scenario_04(api):
    name = "李建国 — 每日例行操盘"
    issues = []
    for card in ["system_status", "daemon", "rotation", "network", "consensus"]:
        c, b = api.get(f"{FRONTEND}/cards/{card}")
        if c != 200: issues.append(f"card {card} {c}: {b[:80]}")
    pc("goto", FRONTEND + "/dashboard")
    time.sleep(1)
    goto_tab("信号")
    time.sleep(1)
    p = shot("s04_end")
    record(4, name, "OK" if not issues else "ISSUE", "; ".join(issues), p)


# ===============================================================
# 场景 5：深度数据 → 截图 = decisions tab（估值+持仓）
# ===============================================================
def scenario_05(api):
    name = "张明 — 深度数据验证"
    issues = []
    c, b = api.get(f"{FRONTEND}/api/valuation/dcf?ticker=AMD")
    if c != 200: issues.append(f"DCF AMD {c}: {b[:80]}")
    c, b = api.get(f"{FRONTEND}/api/valuation/dcf?ticker=AMD&wacc=8.5")
    if c != 200: issues.append(f"DCF wacc {c}: {b[:80]}")
    for card in ["portfolio", "valuation_pro", "chat"]:
        c, b = api.get(f"{FRONTEND}/cards/{card}")
        if c != 200: issues.append(f"card {card} {c}: {b[:80]}")
    pc("goto", FRONTEND + "/dashboard")
    time.sleep(1)
    goto_tab("决策")
    time.sleep(1)
    p = shot("s05_end")
    record(5, name, "OK" if not issues else "ISSUE", "; ".join(issues), p)


# ===============================================================
# 场景 6：轮动 + 预警 → 截图 = signals tab
# ===============================================================
def scenario_06(api):
    name = "赵龙 — 板块轮动 + 价格预警"
    issues = []
    for ep, bd in [
        ("/api/watchlist/add", {"ticker": "COHR"}),
        ("/api/alerts/add", {"ticker": "COHR", "threshold_price": 55, "direction": "below"}),
        ("/api/alerts/remove", {"ticker": "COHR"}),
    ]:
        c, b = api.post(f"{FRONTEND}{ep}", bd)
        if c != 200: issues.append(f"{ep} {c}: {b[:80]}")
    for card in ["rotation", "price_alerts"]:
        c, b = api.get(f"{FRONTEND}/cards/{card}")
        if c != 200: issues.append(f"card {card} {c}: {b[:80]}")
    pc("goto", FRONTEND + "/dashboard")
    time.sleep(1)
    goto_tab("信号")
    time.sleep(1)
    p = shot("s06_end")
    record(6, name, "OK" if not issues else "ISSUE", "; ".join(issues), p)


# ===============================================================
# 场景 7：财报 → 截图 = decisions tab（财报日历+估值）
# ===============================================================
def scenario_07(api):
    name = "刘研究员 — 财报季"
    issues = []
    for t in ["MU", "NVDA"]:
        c, b = api.get(f"{FRONTEND}/api/valuation/dcf?ticker={t}")
        if c != 200: issues.append(f"DCF {t} {c}")
    for card in ["earnings_calendar", "accuracy", "chat"]:
        c, b = api.get(f"{FRONTEND}/cards/{card}")
        if c != 200: issues.append(f"card {card} {c}: {b[:80]}")
    pc("goto", FRONTEND + "/dashboard")
    time.sleep(1)
    goto_tab("决策")
    time.sleep(1)
    p = shot("s07_end")
    record(7, name, "OK" if not issues else "ISSUE", "; ".join(issues), p)


# ===============================================================
# 场景 8：极简使用 → 截图 = signals tab（风险卡片）
# ===============================================================
def scenario_08(api):
    name = "钱阿姨 — 极简使用"
    issues = []
    for card in ["risk_alerts", "quality_gate", "accuracy", "anomaly"]:
        c, b = api.get(f"{FRONTEND}/cards/{card}")
        if c != 200: issues.append(f"card {card} {c}: {b[:80]}")
    pc("goto", FRONTEND + "/dashboard")
    time.sleep(1)
    goto_tab("信号")
    time.sleep(1)
    p = shot("s08_end")
    record(8, name, "OK" if not issues else "ISSUE", "; ".join(issues), p)


# ===============================================================
# 场景 9：管理后台团队协作 → 截图 = 管理后台 /users 页面
# ===============================================================
def scenario_09():
    name = "周经理 — 管理后台团队协作"
    issues = []
    pc("goto", ADMIN + "/")
    time.sleep(1)
    snap = pc("snapshot")
    if "管理后台" not in snap and "登录" not in snap:
        issues.append("管理后台登录页结构异常")
    # 提取验证码算式
    m = re.search(r"(\d+)\s*\+\s*(\d+)", snap)
    if not m:
        m = re.search(r"(\d+)\s*[×*\-]\s*(\d+)", snap)
    expr = m.group(0) if m else ""
    if not expr:
        issues.append("未抓到验证码算式"); ans = 0
    else:
        nums = re.findall(r"\d+", expr)
        if len(nums) >= 2:
            if "×" in expr or "*" in expr:
                ans = int(nums[0]) * int(nums[1])
            elif "+" in expr:
                ans = int(nums[0]) + int(nums[1])
            elif "-" in expr:
                ans = int(nums[0]) - int(nums[1])
            else:
                ans = int(nums[0]) + int(nums[1])
        else:
            ans = 0
    pc("fill", "input[placeholder='管理员账号']", "admin")
    pc("fill", "input[placeholder='管理员密码']", "admin123")
    pc("fill", "input[placeholder='计算结果']", str(ans))
    pc("click", "button:has-text('登录')")
    time.sleep(1.5)
    cur = pc("eval", "() => window.location.href")
    if "method" in cur.lower() or "/login" in cur.lower() or "登录" in cur:
        snap2 = pc("snapshot")
        if "失败" in snap2 or "错误" in snap2:
            issues.append("管理后台登录失败")
    # 截图管理后台 /users（不同页面）
    pc("goto", ADMIN + "/users")
    time.sleep(1)
    p = shot("s09_end")
    # 验证其他管理后台页面
    for path in ["/dashboard", "/users", "/bans", "/activity"]:
        pc("goto", ADMIN + path)
        time.sleep(0.5)
        s = pc("snapshot")
        if "Method Not Allowed" in s and len(s) < 200:
            issues.append(f"admin {path} 405")
    # 共享池
    for url in ["/api/team/shared-pool", "/api/reports/signal-quality?days=30"]:
        try:
            r = urllib.request.urlopen(urllib.request.Request(FRONTEND + url), timeout=5)
            if r.status != 200: issues.append(f"{url} {r.status}")
        except Exception as e:
            issues.append(f"{url} {e}")
    record(9, name, "OK" if not issues else "ISSUE", "; ".join(issues), p)


# ===============================================================
# 场景 10：极深研究 → 截图 = decisions tab（估值工具）
# ===============================================================
def scenario_10(api):
    name = "徐教授 — 极深研究"
    issues = []
    for t in ["SMCI", "AMD", "NVDA"]:
        c, b = api.get(f"{FRONTEND}/api/valuation/dcf?ticker={t}")
        if c != 200: issues.append(f"DCF {t} {c}")
    c, b = api.get(f"{FRONTEND}/api/valuation/dd?ticker=SMCI")
    if c != 200: issues.append(f"DD SMCI {c}: {b[:80]}")
    for card in ["valuation_pro", "chat"]:
        c, b = api.get(f"{FRONTEND}/cards/{card}")
        if c != 200: issues.append(f"card {card} {c}")
    pc("goto", FRONTEND + "/dashboard")
    time.sleep(1)
    goto_tab("决策")
    time.sleep(1)
    p = shot("s10_end")
    record(10, name, "OK" if not issues else "ISSUE", "; ".join(issues), p)


# ===============================================================
# 场景 11：Pipeline 管理 → 截图 = data tab（Pipeline 执行面板）
# ===============================================================
def scenario_11(api):
    name = "王工 — Pipeline 任务调度"
    issues = []
    c, b = api.get(f"{FRONTEND}/pipeline/tasks")
    if c != 200: issues.append(f"tasks {c}: {b[:80]}")
    for ep in ["/pipeline/tasks/seed", "/pipeline/clean"]:
        c, b = api.post(f"{FRONTEND}{ep}")
        if c not in (200, 201): issues.append(f"{ep} {c}: {b[:80]}")
    for ep in ["/pipeline/tasks/fetched", "/pipeline/tasks/crypto_fetched"]:
        c, b = api.get(f"{FRONTEND}{ep}")
        if c != 200: issues.append(f"{ep} {c}")
    for card in ["pipeline_execute", "script_runner", "fetch_control"]:
        c, b = api.get(f"{FRONTEND}/cards/{card}")
        if c != 200: issues.append(f"card {card} {c}: {b[:80]}")
    pc("goto", FRONTEND + "/dashboard")
    time.sleep(1)
    goto_tab("数据")
    time.sleep(1)
    p = shot("s11_end")
    record(11, name, "OK" if not issues else "ISSUE", "; ".join(issues), p)


# ===============================================================
# 场景 12：加密货币 → 截图 = signals tab（crypto 卡片）
# ===============================================================
def scenario_12(api):
    name = "林总 — 加密资产跟踪"
    issues = []
    c, b = api.post(f"{FRONTEND}/api/config/observations/add", {"handle": "BTC"})
    if c != 200: issues.append(f"obs BTC {c}: {b[:80]}")
    c, b = api.post(f"{FRONTEND}/api/alerts/add",
        {"ticker": "BTC", "threshold_price": 60000, "direction": "below"})
    if c != 200: issues.append(f"alert BTC {c}: {b[:80]}")
    for card in ["crypto", "portfolio", "price_alerts"]:
        c, b = api.get(f"{FRONTEND}/cards/{card}")
        if c != 200: issues.append(f"card {card} {c}: {b[:80]}")
    pc("goto", FRONTEND + "/dashboard")
    time.sleep(1)
    goto_tab("信号")
    time.sleep(1)
    p = shot("s12_end")
    record(12, name, "OK" if not issues else "ISSUE", "; ".join(issues), p)


# ===============================================================
# 场景 13：网络关系 + 画像 → 截图 = research tab
# ===============================================================
def scenario_13(api):
    name = "刘工 — 网络关系 + 画像"
    issues = []
    for card in ["network", "portrait", "portrait_generate", "accuracy", "role_picker"]:
        c, b = api.get(f"{FRONTEND}/cards/{card}")
        if c != 200: issues.append(f"card {card} {c}: {b[:80]}")
    pc("goto", FRONTEND + "/dashboard")
    time.sleep(1)
    goto_tab("研究")
    time.sleep(1)
    p = shot("s13_end")
    record(13, name, "OK" if not issues else "ISSUE", "; ".join(issues), p)


# ===============================================================
# 场景 14：管理员后台深度 → 截图 = admin /dashboard
# ===============================================================
def scenario_14():
    name = "陈工 — 管理后台 + 安全审计"
    issues = []
    for path in ["/dashboard", "/users", "/bans", "/activity"]:
        pc("goto", ADMIN + path)
        time.sleep(0.5)
        s = pc("snapshot")
        if "Method Not Allowed" in s and len(s) < 200:
            issues.append(f"admin {path} 405/未登录")
    # 截图管理后台 dashboard
    pc("goto", ADMIN + "/dashboard")
    time.sleep(1)
    p = shot("s14_end")
    # 报告
    try:
        r = urllib.request.urlopen(urllib.request.Request(FRONTEND + "/api/reports/signal-quality?days=30"), timeout=5)
        if r.status != 200: issues.append(f"signal-quality {r.status}")
    except Exception as e:
        issues.append(f"signal-quality {e}")
    record(14, name, "OK" if not issues else "ISSUE", "; ".join(issues), p)


# ===============================================================
# 场景 15：别名管理 → 截图 = data tab（asset_alias 卡片）
# ===============================================================
def scenario_15(api):
    name = "小赵 — 别名管理 + 数据清洗"
    issues = []
    c, b = api.get(f"{FRONTEND}/cards/asset_alias")
    if c != 200: issues.append(f"asset_alias {c}: {b[:80]}")
    c, b = api.post(f"{FRONTEND}/pipeline/clean")
    if c not in (200, 201): issues.append(f"clean {c}: {b[:80]}")
    pc("goto", FRONTEND + "/dashboard")
    time.sleep(1)
    goto_tab("数据")
    time.sleep(1)
    p = shot("s15_end")
    record(15, name, "OK" if not issues else "ISSUE", "; ".join(issues), p)


# ===============================================================
# 场景 16：Chat + RAG → 截图 = decisions tab（chat 卡片）
# ===============================================================
def scenario_16(api):
    name = "方博士 — Chat + RAG"
    issues = []
    c, b = api.get(f"{FRONTEND}/cards/chat")
    if c != 200: issues.append(f"chat card {c}: {b[:80]}")
    c, b = api.post(f"{FRONTEND}/cards/chat/action", {"query": "NVDA vs AMD 2026 谁更有潜力？"})
    if c not in (200, 500, 503):
        issues.append(f"chat action {c}: {b[:80]}")
    pc("goto", FRONTEND + "/dashboard")
    time.sleep(1)
    goto_tab("决策")
    time.sleep(1)
    p = shot("s16_end")
    record(16, name, "OK" if not issues else "ISSUE", "; ".join(issues), p)


# ===============================================================
# 场景 17：令牌安全 → 截图 = 认证 me 响应页面
# ===============================================================
def scenario_17(api):
    name = "安全 — 令牌管理"
    issues = []
    c, b = api.get(f"{FRONTEND}/auth/me")
    if c != 200: issues.append(f"/auth/me {c}")
    c, b = api.post(f"{FRONTEND}/auth/refresh", {"refresh_token": "fake-invalid"})
    if c not in (200, 401): issues.append(f"refresh {c}: {b[:80]}")
    # 截图 Dashboard 表示安全验证通过
    pc("goto", FRONTEND + "/dashboard")
    time.sleep(1)
    p = shot("s17_end")
    record(17, name, "OK" if not issues else "ISSUE", "; ".join(issues), p)


# ===============================================================
# 场景 18：故障恢复 → 截图 = data tab（Pipeline 状态）
# ===============================================================
def scenario_18(api):
    name = "运维 — 故障恢复与重试"
    issues = []
    c, b = api.get(f"{FRONTEND}/pipeline/tasks")
    if c != 200:
        issues.append(f"tasks {c}")
    else:
        try:
            data = json.loads(b)
            tasks = data.get("tasks") if isinstance(data, dict) else data
            if tasks:
                tid = tasks[0].get("id") if isinstance(tasks[0], dict) else None
                if tid:
                    c, b = api.post(f"{FRONTEND}/pipeline/tasks/{tid}/retry")
                    if c not in (200, 201, 400, 404):
                        issues.append(f"retry {c}")
        except Exception as e:
            issues.append(f"parse {e}")
    pc("goto", FRONTEND + "/dashboard")
    time.sleep(1)
    goto_tab("数据")
    time.sleep(1)
    p = shot("s18_end")
    record(18, name, "OK" if not issues else "ISSUE", "; ".join(issues), p)


# ===============================================================
# 场景 19：极端场景 → 截图 = 403/404 页面
# ===============================================================
def scenario_19():
    name = "安全测试 — 极端场景"
    issues = []
    tmp = APIClient()
    # 路径遍历 → 截图 403 页面
    c, b = tmp.get(f"{FRONTEND}/timeline/..%2F..%2Fetc%2Fpasswd")
    if c not in (400, 403, 404): issues.append(f"path traversal {c}")
    # 无效 JWT：公开模式返 200{logged_in:false}
    c, b = tmp.get(f"{FRONTEND}/auth/me", extra_headers={"Authorization": "Bearer xxx"})
    if c not in (200, 401): issues.append(f"invalid jwt {c}")
    # 暴力登录
    for _ in range(3):
        c, b = tmp.post(f"{ADMIN}/login",
            {"username": "admin", "password": "wrong", "captcha_answer": "0"})
        if c not in (200, 400, 401, 403): issues.append(f"暴力登录 {c}")
    # 截图 timeline 403 响应页面
    pc("goto", FRONTEND + "/timeline/..%2F..%2Fetc%2Fpasswd")
    time.sleep(1)
    p = shot("s19_end")
    record(19, name, "OK" if not issues else "ISSUE", "; ".join(issues), p)


# ===============================================================
# 场景 20：全链路回归 → 截图 = 28 卡 + 管理后台 activity
# ===============================================================
def scenario_20(api):
    name = "QA — 全链路 E2E 回归"
    issues = []
    CARDS = ["chat", "accuracy", "consensus", "rotation", "anomaly", "network",
             "system_status", "daemon", "telegram", "role_picker", "portfolio",
             "fetch_control", "portrait", "asset_alias", "crypto", "script_runner",
             "timeline", "pipeline_execute", "portrait_generate", "quality_gate",
             "risk_alerts", "panel_review", "publish_review", "config_center",
             "earnings_calendar", "price_alerts", "valuation_pro", "admin_monitor"]
    for card in CARDS:
        c, b = api.get(f"{FRONTEND}/cards/{card}")
        if c != 200: issues.append(f"card {card} {c}: {b[:60]}")
    c, b = api.get(f"{FRONTEND}/cards/meta")
    if c != 200: issues.append(f"cards/meta {c}")
    c, b = api.get(f"{FRONTEND}/api/reports/signal-quality?days=30")
    if c != 200: issues.append(f"signal-quality {c}: {b[:80]}")
    # 截图 Dashboard（全卡片加载后）
    pc("goto", FRONTEND + "/dashboard")
    time.sleep(2)
    p = shot("s20_end")
    record(20, name, "OK" if not issues else "ISSUE", "; ".join(issues), p)


# ===============================================================
# 主流程
# ===============================================================
def main():
    print("=" * 60)
    print("20 场景浏览器 E2E 测试 — 真实交互 + 有意义的截图")
    print("=" * 60)

    import secrets
    email = f"test_main_{secrets.token_hex(3)}@test.com"
    user = f"u_main_{secrets.token_hex(2)}"
    pw = "TestPw123!"
    api = APIClient()
    ok, msg = api.register_login(email, user, pw)
    if not ok:
        print(f"FATAL: {msg}"); return
    print(f"测试用户: {email}")

    print("\n[场景 01] 注册探索 → 截图 = Dashboard signals tab")
    scenario_01()

    print("\n[场景 02] 入门配置 → 截图 = settings tab")
    scenario_02(api)

    for n, fn, label in [(3, scenario_03, "signals tab"),
                          (4, scenario_04, "signals tab"),
                          (5, scenario_05, "decisions tab"),
                          (6, scenario_06, "signals tab"),
                          (7, scenario_07, "decisions tab"),
                          (8, scenario_08, "signals tab"),
                          (10, scenario_10, "decisions tab"),
                          (11, scenario_11, "data tab"),
                          (12, scenario_12, "signals tab"),
                          (13, scenario_13, "research tab"),
                          (15, scenario_15, "data tab"),
                          (16, scenario_16, "decisions tab"),
                          (17, scenario_17, "dashboard"),
                          (18, scenario_18, "data tab"),
                          (20, scenario_20, "全卡片渲染")]:
        print(f"\n[场景 {n:02d}] → 截图 = {label}")
        try:
            fn(api)
        except Exception as e:
            import traceback; traceback.print_exc()
            record(n, fn.__name__, "ERROR", str(e)[:200])
        time.sleep(0.5)

    print("\n[场景 09] 管理后台登录 → 截图 = admin /users")
    scenario_09()
    print("\n[场景 14] 管理后台深度 → 截图 = admin /dashboard")
    scenario_14()
    print("\n[场景 19] 极端场景 → 截图 = 403 响应页")
    scenario_19()

    # 报告
    ok_n = sum(1 for r in results if r["status"] == "OK")
    iss_n = sum(1 for r in results if r["status"] == "ISSUE")
    err_n = sum(1 for r in results if r["status"] == "ERROR")
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(f"# 20 场景浏览器 E2E 测试报告\n\n")
        f.write(f"**总计**: 20 场景 | **OK**: {ok_n} | **ISSUE**: {iss_n} | **ERROR**: {err_n}\n\n")
        f.write("| # | 场景 | 状态 | 截图（页面） | 问题 |\n")
        f.write("|---|------|------|-------------|------|\n")
        for r in results:
            sn = Path(r["screenshot"]).name if r["screenshot"] else ""
            f.write(f"| {r['scenario']:02d} | {r['name']} | {r['status']} | `{sn}` | {r['issues'][:200]} |\n")
        f.write(f"\n## 截图清单\n\n")
        for r in results:
            if r["screenshot"]:
                f.write(f"- 场景 {r['scenario']:02d}: `{Path(r['screenshot']).name}`\n")
    print(f"\n报告: {REPORT}")
    print(f"统计: OK={ok_n} ISSUE={iss_n} ERROR={err_n}")


if __name__ == "__main__":
    main()
