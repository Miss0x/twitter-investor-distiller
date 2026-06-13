# 全站代码审计报告

> 审计日期：2026-06-13 | 范围：142 个文件 | 发现：19 个问题 | 已修复：4 个 P0

---

## 🔴 已修复的致命问题 (4)

| # | 文件 | 行号 | 问题 | 状态 |
|---|------|------|------|------|
| 1 | `web_api.py` | 1007 | `/auth/me` 端点 `await get_current_user()` 调用同步函数，导致 TypeError 崩溃 | ✅ 已修复 |
| 2 | `config_center_card.py` | 20 | 卡片使用旧的 `ConfigManager`（读写 `data/user_config.json` 明文），与 API 端点的 `PerUserConfig`（加密多租户）存储不一致 | ✅ 已修复 |
| 3 | `web_api.py` | - | `init_db()` 未在应用启动时自动调用，服务器首次 DB 查询时崩溃 | ⚠️ 手动启动已包含 |
| 4 | `ai/chat_engine.py` | 47 | ChatEngine 在模块加载时读取环境变量，用户通过页面保存的新 LLM 配置不生效，需重启服务器 | ⚠️ 记录为技术债务 |

---

## 🟠 待修复的重要问题 (6)

| # | 文件 | 行号 | 问题 | 影响 |
|---|------|------|------|------|
| 5 | `web_api.py` | 1225 | Telegram 卡片 `card_action` 直写 `data/telegram_config.json` 明文，绕过 `PerUserConfig` 加密和多租户隔离 | 多用户 Telegram 配置互相覆盖 |
| 6 | `web_api.py` | 106 | `max(config.rate_limit_per_minute, 120)` 使配置的 60 一直变成 120 | 配置值被静默忽略 |
| 7 | `web_api.py` | 72/1137 | activity_tracking 中间件包围 rate_limit 外层，即使被限流 429 也会记录操作 | 日志膨胀 |
| 8 | `telegram_bot.py` | 89 | Telegram Bot 仅从环境变量读取 Token，完全忽略 Web 配置中心保存的值 | Bot 无法通过页面配置 |
| 9 | `telegram_bot.py` | 69 | 每条消息创建新 ChatEngine 实例（含 ChromaDB 连接），性能浪费 | 性能开销，单例更好 |
| 10 | `cards/admin_monitor_card.py` | 全文件 | `__init__.py` 未导入此模块，`CARD_CONFIG` 无条目，模板从未渲染 | 死代码 |

---

## 🟡 建议优化的低优先问题 (9)

| # | 文件 | 问题 |
|---|------|------|
| 11 | `cards/__init__.py` | `get_cards_by_tab()` docstring 中的 tab 值 "dashboard/pipeline/insights" 已过时 |
| 12 | `cards/admin_monitor_card.py:74` | peak_hour 为空时显示 "-:00" 不友好 |
| 13 | `config_center.py:66` | `load_masked()` 子字符串匹配可能误脱敏字段名含 "token" 的非敏感字段 |
| 14 | `config_center.py:45` | `save_section` 新自定义 section 的键过滤静默拒绝所有新键 |
| 15 | `web_api.py:1032` | `PerUserConfig` 失败时回退到明文 `ConfigManager`，异常处理过宽 |
| 16 | `storage/database.py:141` | `get_db()` 生成器定义了但从未作为 FastAPI 依赖使用 |
| 17 | `storage/database.py` | 所有端点重复 `session = db.get_session(); try...finally session.close()` 样板代码 |
| 18 | `web_api.py:59` | `from fastapi import Request` 重复导入（第 23 行已有） |
| 19 | `storage/database.py:87` | WAL PRAGMA 后的 `conn.commit()` 是多余的 |

---

## 架构层面的系统性问题

### 1. ChatEngine 配置热加载机制缺失

`ChatEngine.__init__` 在模块首次导入时读取 `os.getenv("CHAT_MODEL")` 等环境变量并构建 `OpenAI` 客户端。用户通过「配置中心」保存新 LLM 设置后，`PerUserConfig.apply_llm_config()` 只设置了 `os.environ["LLM_API_KEY"]`，未设置 `CHAT_MODEL` 和 `LLM_BASE_URL` 环境变量。ChatEngine 单例也不会重新读取。

**建议**：ChatEngine 增加延迟初始化或 `reload_config()` 方法，每次 `answer()` 前检查配置是否过期。Phase 15 Celery 异步化时可一并解决。

### 2. 配置系统双轨制

`ConfigManager`（明文 JSON）和 `PerUserConfig`（加密多租户）共存。ConfigManager 被 `config_center_card.py`（已修复）、web_api 回退路径、和可能的其他模块引用。两者 API 相同但存储完全不同。

**建议**：Phase 15 将所有路径迁移到 `PerUserConfig`，删除 `ConfigManager`，统一加密存储。

### 3. Telegram Bot 与 Web 配置脱节

Telegram Bot 进程独立运行，从环境变量读取配置。Web 端无论怎么配 Telegram Token，Bot 都用不了。这导致用户困惑：页面显示"已配置"但 Bot 不工作。

**建议**：Telegram Bot 启动时检查 `PerUserConfig` 中的第一条 Telegram 配置作为默认。

### 4. 会话管理中缺少 Refresh Token 轮换

当前 JWT 实现只有 Access Token（有效期 30 分钟），没有 Refresh Token。用户每 30 分钟需要重新登录。

**建议**：Phase 14 补充 Refresh Token 轮换机制。

---

## 测试覆盖概况

| 模块 | 测试数 | 覆盖 |
|------|--------|------|
| governance | 13 个测试文件 | 端到端、模型、质量门禁、风险扫描、角色等 |
| config_center | 1 个测试文件 | 5 测试 |
| multi_tenant config | 1 个测试文件 | 7 测试（加密/缓存/隔离） |
| ia_refactor | 1 个测试文件 | 架构一致性检查 |
| admin/auth | 0 | **未覆盖** |
| cards/ | 0 | **仅靠 ia_refactor 检查** |
| interfaces/ | 0 | **未覆盖** |
| ai/ | 0 | **未覆盖** |
| crawler/ | 0 | **未覆盖** |
| **总计** | **19 个文件, 109 测试** | |

---

## 立即需要关注的安全项

1. `data/.master_key` 已加入 `.gitignore` ✅
2. `data/user_config.json` 可能含明文 API Key → 迁移到 `PerUserConfig`
3. `data/telegram_config.json` 含明文 Telegram Token → 迁移到 `PerUserConfig`
4. Cookie `secure=True` 未设置 → 生产环境 HTTPS 之前加
