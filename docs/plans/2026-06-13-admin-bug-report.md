# 管理后台 Bug 排查报告

> 排查时间：2026-06-13 00:23
> 排查范围：`src/admin/app.py` 全量代码 + `/stats` `/users/toggle` `/suspend` `/unsuspend` 端点
> 测试方式：代码审计 + curl 实时验证

---

## 🔴 致命级（P0 — 必须立即修复）

### B1. API 端点完全无认证保护

**位置**：`app.py` L313-344（`/stats` `/users/toggle` `/suspend` `/unsuspend`）

**症状**：任何人都可以不需要登录直接调用这些 API。

**实测验证**：
```bash
curl -s http://127.0.0.1:8001/stats          # → 返回统计数据
curl -s -X POST http://127.0.0.1:8001/suspend -H "Content-Type: application/json" -d '{"identifier":"test"}'  # → 成功封禁
```

**影响**：攻击者可以：
- 读取系统统计数据（信息泄露）
- 启用/停用任意用户
- 封禁/解封任意对象

**修复**：每个 API 端点加 `_check_login()` 检查。

---

### B2. 管理员密码硬编码在代码中

**位置**：`app.py` L25

```python
ADMIN_CREDENTIALS = {"admin": "admin123"}
```

**影响**：密码明文存储在源代码中，Git 历史永久暴露。

**修复**：
1. 改为环境变量 `ADMIN_PASSWORD`，默认 `admin123` 仅用于开发
2. 密码存 bcrypt hash 而非明文

---

### B3. XSS 注入风险 — 用户名未转义

**位置**：`app.py` L260, L297

```python
rows += f"""<tr><td>{u.id}</td><td><b>{u.username}</b></td>..."""
```
```python
rows += f"""...onclick="unsuspend('{s.get('identifier','')}')">...</td></tr>"""
```

**实测场景**：如果用户名设为 `<script>alert('xss')</script>`，每次管理后台加载用户列表时 JavaScript 执行。

**修复**：所有用户输入数据嵌入 HTML 前必须 HTML 转义。Python 用 `html.escape()`。

---

### B4. 会话安全缺陷 — 使用 `random` 而非 `secrets`

**位置**：`app.py` L30

```python
return hashlib.sha256(str(random.getrandbits(256)).encode()).hexdigest()[:32]
```

**影响**：`random.getrandbits(256)` 基于 Mersenne Twister，不是密码学安全的随机数生成器。攻击者通过观察足够多的令牌可以预测后续令牌。

**修复**：改用 `secrets.token_hex(32)`。

---

## 🟠 重要级（P1 — 影响功能或安全）

### B5. Captcha 令牌泄漏到 `_sessions` — 内存泄漏

**位置**：`app.py` L158

```python
_sessions[f"captcha_{captcha_token}"] = captcha_answer
```

Captcha 答案写入 `_sessions` 字典后，只在登录成功时通过 `pop` 移除。如果用户刷新登录页 100 次但不登录，字典中会积压 100 条无用条目，永不过期。

**修复**：Captcha 存独立字典（如 `_captchas`），并在 `_login_page()` 中清理旧条目（超过 5 分钟的删除）。

---

### B6. 无登录失败频率限制

**位置**：`app.py` L174-193

**症状**：可以无限次尝试密码，无任何速率限制或锁定机制。

**修复**：加 Redis 或内存 LRU 计数器，同一 IP 5 次失败后封 15 分钟。

---

### B7. `_sessions` 字典无限增长

**位置**：`app.py` L26, L190

每次登录创建新 token，但只在显式 `logout` 时删除。如果没有 logout 就关闭浏览器，老 token 永远留在内存中。

**修复**：每次 `_check_login` 成功后记录 `last_seen` 时间戳。后台定期清理 2 小时无活动的 token。

---

### B8. 缺少 CSRF 防护

**位置**：`app.py` L319-344

`/users/toggle` `/suspend` `/unsuspend` 接受 JSON POST 请求，无 CSRF token 验证。如果管理员登录后访问恶意网站，该网站可以构造请求调用这些 API。

**修复**：为所有 POST 请求加 CSRF token 校验，或使用 `SameSite=Strict` Cookie。

---

### B9. Dashboard 和其他页面无异常处理

**位置**：`app.py` L208-243（dashboard）、L248-267（users）、L272-283（activity）、L288-306（bans）

如果 `ActivityTracker().stats()` 或数据库查询抛出异常，页面直接返回 500，无任何错误信息。

**修复**：每个页面函数加 `try/except`，异常时渲染友好的错误提示页面。

---

## 🟡 建议优化级（P2 — 体验或隐患）

### B10. 登录后密码验证时间恒定性问题

**位置**：`app.py` L186

```python
if username not in ADMIN_CREDENTIALS or ADMIN_CREDENTIALS[username] != password:
```

两次比较不是恒定时间，攻击者可以通过计时攻击推断用户名是否有效。

**修复**：使用 `secrets.compare_digest()` 做恒定时间比较。

---

### B11. Logout 使用 GET 请求

**位置**：`app.py` L196-202

`GET /logout` 会触发登出。浏览器预加载、搜索引擎爬虫可能会意外触发登出。

**修复**：改为 `POST /logout`。

---

### B12. 移动端侧边栏缺少汉堡菜单

**位置**：CSS `@media(max-width:768px)`

移动端侧边栏缩成 56px 图标模式，但没有展开/收起按钮，用户无法看到菜单文字。

**修复**：加汉堡菜单按钮和 JavaScript 切换逻辑。

---

### B13. Session cookie 未设置 `Secure` 标志

**位置**：`app.py` L192

```python
response.set_cookie("admin_token", token, httponly=True, samesite="lax", max_age=7200)
```

缺少 `secure=True`。如果生产环境部署 HTTPS 后未加此标志，Cookie 可能通过 HTTP 明文传输。

**修复**：加 `secure=True`（或从环境变量读取，开发环境关闭）。

---

### B14. 封禁管理页按钮样式语义混乱

**位置**：`app.py` L298

```python
<button class="btn btn-primary" onclick="unsuspend(...)">解除</button>
```

"解除封禁"用的是蓝色主按钮，视觉上不够明确是"撤销"操作。

**修复**：改为绿色 `btn-primary` 或专门的 `btn-success` 样式。

---

## 📊 汇总

| 级别 | 数量 | 关键项 |
|------|------|--------|
| 🔴 致命 | 4 | API 无认证、密码硬编码、XSS、会话不安全 |
| 🟠 重要 | 5 | Captcha 泄漏、无频率限制、Session 泄漏、缺 CSRF、无异常处理 |
| 🟡 建议 | 5 | 计时攻击、GET 登出、移动端菜单、Cookie Secure、样式 |

---

## 🔧 优先修复顺序

1. **B1** — API 端点加认证检查（安全性最高优先级）
2. **B3** — HTML 转义用户名（XSS 防护）
3. **B4** — `secrets` 替代 `random`（会话安全）
4. **B2** — 密码改为环境变量 + bcrypt
5. **B9** — 页面异常处理（用户体验）
6. **B5 + B7** — Captcha/Token 内存泄漏清理
7. **B6 + B8** — 频率限制 + CSRF
8. **B10-B14** — 体验优化
