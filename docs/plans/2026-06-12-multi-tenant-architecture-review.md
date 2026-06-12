# Phase 14-16 架构评审报告

> 评审对象：`docs/plans/2026-06-12-multi-tenant-architecture-plan.md`
> 评审时间：2026-06-12
> 评审标准：架构合理性、安全性、稳定性、可扩展性、可维护性

---

## 一、Phase 14：用户体系

### 🔴 致命问题

#### 1.1 Refresh Token 无吊销机制，安全风险严重
JWT Refresh Token 设定 7 天有效期，但未提存储位置和吊销机制。JWT 本身是无状态的，如果 Refresh Token 也是纯 JWT 而不在后端记录，则无法主动登出、无法强制下线、Token 被盗即永久有效 7 天。

**建议**：Refresh Token 存储在数据库或 Redis，绑定 `(user_id, token_family_id)`，每次使用后轮换（refresh token rotation），发现同一 Token 被重放立即作废整个 family。

#### 1.2 API Key 加密密钥管理未定义
方案提到"用户 LLM/Twitter Key 使用 AES-256-GCM 加密存储"但未说明加密密钥从哪来。如果密钥硬编码在代码里，就只是变相的明文存储。

**建议**：使用环境变量注入主密钥（`ENCRYPTION_KEY`），或集成 KMS 方案（AWS KMS / HashiCorp Vault），密钥不在代码中。到 Phase 16 再考虑 KMS。

#### 1.3 现有数据迁移无 tenant_id 回填策略
方案说"现有数据加 tenant_id 隔离"但未解决：存量数据（用户已有的分析结果、治理包、推文数据）的 tenant_id 填什么？

**建议**：Phase 14 上线前必须写 migration script：为所有存量数据填充一个默认 `default_tenant` ID，并确保该 tenant 属于当前用户（第一个 admin）。

### 🟠 重要问题

#### 1.4 密码存储算法未指定
`password_hash` 字段未指定哈希算法。SHA256 等快速哈希已不安全，必须用慢哈希。

**建议**：使用 `bcrypt`（passlib 库），cost factor ≥ 12。Jinja2/FastAPI 生态中 `python-jose` + `passlib` 组合成熟。

#### 1.5 登录接口无限流保护
登录端点缺少频率限制。暴力破解者可以通过大量尝试破解弱密码。

**建议**：在 JWT 中间件之前加一层速率限制：同一 IP 每分钟最多 5 次登录尝试，同一 email 连续失败 5 次锁定 15 分钟。

#### 1.6 tenant_id 自动注入的可靠性
方案说"通过 SQLAlchemy 事件或中间件注入"，但这是整个多租户隔离的核心防线。如果某一处绕过该机制导致查询不带 tenant_id，就是跨租户数据泄露。

**建议**：在 `db.get_session()` 层面注入，不依赖业务代码手动加 filter。写测试专门验证：用租户 A 的 Token 不能读到租户 B 的数据。这类测试每条 SQL 查询路径至少要覆盖一次。

### 🟡 建议优化

#### 1.7 User.settings 的 JSON blob 反模式
把所有个性化配置（LLM/Twitter/Telegram/观察对象）塞进一个 JSON 字段，导致：无法独立索引、无法原子更新单个字段、无法在数据库层做约束校验。

**建议**：保持 `data/user_config.json` 文件存储方案，但重命名为 `data/tenants/{tenant_id}/user_config.json`。不塞进数据库。Phase 15 再考虑是否迁到 Redis Hash 或独立表。

#### 1.8 邮箱验证流程缺失邮件发送方案
"注册 → 邮箱验证"的链路中未提及用什么 SMTP 服务发送验证邮件。

**建议**：Phase 14 初期可以跳过邮箱验证，直接激活。商用后可选 SendGrid / Resend / AWS SES，或直接用 OAuth 跳过邮箱验证环节。

---

## 二、Phase 15：基础设施

### 🔴 致命问题

#### 2.1 SQLite → PostgreSQL 数据迁移无零停机方案
没有设计迁移时的停机窗口、数据校验策略、回滚方案。如果迁移中出错，用户数据可能丢失或不一致。

**建议**：分三步：
1. 写双写适配器（同时写 SQLite 和 PostgreSQL），运行 1 天验证新库数据完整性
2. 创建 pg_dump/restore 风格的完整迁移脚本 + 逐表 checksum 校验
3. 停机窗口（或只读模式）切流量到 PostgreSQL，保留 SQLite 作为紧急回滚备份

#### 2.2 Celery 引入导致执行模型断裂
当前治理 Pipeline (`task_executor.py`) 使用 `threading.Thread` 在进程内同步执行，结果直接写入数据库。改为 Celery 异步后：任务执行结果如何返回给等待中的 Dashboard 前端？错误如何处理？

**建议**：保留 Phase 14 的 threading 执行模型不变，Phase 15 只加 Celery 做"重任务异步化"（LLM 调用、大文件分析），治理流水线保持同步。Phase 16 再做全异步化。避免一次性改变所有执行路径。

#### 2.3 配额系统的竞态条件
`quota` 字段在 JSON 中，多并发 LLM 调用同时 `quota.daily_llm_calls += 1` 会互相覆盖。

**建议**：配额必须用 Redis 原子计数器（`INCR`），或者 PG `SELECT ... FOR UPDATE` 行级锁。JSON 字段只存静态配置，动态配额另存。

### 🟠 重要问题

#### 2.4 Redis 不可用时的降级策略缺失
方案没有提到 Redis 故障时的行为——所有限流、缓存、会话全部失效？还是系统直接崩溃？

**建议**：
- 会话：Redis 不可用时退化为纯 JWT 验证（牺牲登出/吊销能力）
- 限流：退化为内存 LRU 计数器（重启丢失但不崩溃）
- 缓存：退化为无缓存直接查库
- 启动时健康检查打印 Redis 状态，但不应阻止服务启动

#### 2.5 Sentry 错误追踪未覆盖 Celery Worker
方案提到 Sentry 但未说明如何集成到 Celery Worker。Celery 任务异常不会自然触发 FastAPI 的异常处理器。

**建议**：在 Celery 的 `task_failure` 信号中接入 Sentry，或使用 `sentry-sdk` 的 `CeleryIntegration`。

#### 2.6 数据库连接池大小未规划
FastAPI × 2 + Celery Worker 若都连 PostgreSQL，默认连接池会迅速耗尽。SQLAlchemy 默认 `pool_size=5, max_overflow=10`，两个 FastAPI + N 个 Worker = (5+10)×2 + N×(5+10) 个连接，很容易打满 PG 的 `max_connections`（默认 100）。

**建议**：使用 PgBouncer 做连接池复用，或精确规划每个实例的 `pool_size` + `max_overflow`，总和不超过 PG `max_connections` 的 70%。

### 🟡 建议优化

#### 2.7 pgvector vs ChromaDB 迁移成本被低估
方案提到"pgvector 可与业务库合一，减少组件"。但当前 ChromaDB 存了大量索引向量，迁移需要重新 embedding 或写导出脚本。

**建议**：Phase 15 先保留 ChromaDB，不急着迁。等向量规模真正成为瓶颈再迁 pgvector。过早迁移得不偿失。

#### 2.8 审计日志只定义模型，未定义存储和查询
AuditLog 表在写入密集场景下会成为性能瓶颈。每条配置变更、登录、操作都写一行，日均数千至数万条。

**建议**：审计日志用 PostgreSQL 存储即可（百级用户够用），但按月分区（partitioned table），设置 90 天自动清理策略。

---

## 三、Phase 16：商用化

### 🔴 致命问题

#### 3.1 Docker Compose 不足以支撑生产环境
Docker Compose 适合单机部署，但不解决：健康检查自动重启（需要 `restart: always` + healthcheck）、日志收集、零停机重启、资源限制。

**建议**：生产环境至少用 Docker Compose + `restart: unless-stopped` + `deploy.resources.limits` + `healthcheck`。有多机需求时上 Docker Swarm（与 Compose 语法兼容）或 K8s。

#### 3.2 灰度发布只提路由，不提数据库兼容性
灰度发布意味着两个版本的应用同时运行。如果新版改了数据库 schema，旧版会在新 schema 上崩溃。

**建议**：建立数据库迁移纪律：每次迁移必须前向兼容（新字段加默认值/允许 NULL），不能改名/删字段在同一版本。如果必须破坏性变更，必须先停灰度、全量升级、再恢复灰度。

### 🟠 重要问题

#### 3.3 i18n 方案过于基础
`Jinja2 {% trans %}` 只能翻译模板静态文本。API 错误消息、治理决策文案、角色评审结论等大量后端生成的动态文本无法翻译。

**建议**：后端建立消息码体系：`msg_codes.json` 中 `{ "err.invalid_api_key": {"zh": "...", "en": "..."} }`，API 返回 `{"code": "err.invalid_api_key", "message": "..."} `，前端按当前语言展示。

#### 3.4 计费模型缺少支付网关和发票
方案列出了三个套餐价格，但完全没有支付流程。商用产品需要：支付回调、发票生成、退款处理、用量实时统计。

**建议**：初期对接 Stripe / Lemon Squeezy / Paddle（处理税务），不自己造支付轮子。Phase 16 先做到"手动配置套餐+实时用量展示"，支付放在 Phase 17。

#### 3.5 没有 API 版本化策略
如果未来做 OpenAPI 或第三方接入，当前 API 端点（如 `/cards/meta`）无版本号前缀。更改数据结构会破坏所有客户端。

**建议**：Phase 16 开始所有新端点加 `/api/v1/` 前缀，旧端点保留但标记 deprecated，渐进迁移。

### 🟡 建议优化

#### 3.6 WAF 引入的维护成本
方案提到 WAF 但这对百级用户的 SaaS 工具过度了。WAF 规则需要持续调优，误拦影响用户体验。

**建议**：先用 Nginx `limit_req` + FastAPI 中间件做基础防护。真正需要 WAF 时用 Cloudflare 免费计划，无需自建。

#### 3.7 CDN 策略未区分静态和动态内容
CDN 加速对静态资源（JS/CSS/图片）有效，但对实时信号数据不应缓存。

**建议**：CDN 只缓存 `/static/` 和 `/dashboard` 页面的静态外链资源。API 响应设置 `Cache-Control: no-store`。

---

## 四、跨 Phase 系统性风险

### 🔴 致命

| 风险 | 说明 |
|------|------|
| **数据隔离防线单一** | 整个多租户安全完全依赖 SQLAlchemy 中间件自动注入 tenant_id。一旦某处绕过（原生 SQL、手动查询、ChromaDB 查询），就是跨租户泄漏。需要对每条数据访问路径建立测试防线 |
| **密钥生命周期管理缺失** | 用户 LLM/Twitter Key 存储后，没有 rotation、撤销、泄露检测、异常用量告警的完整生命周期 |

### 🟠 重要

| 风险 | 说明 |
|------|------|
| **测试策略未规划** | 多用户系统需要的测试类型远多��当前：跨租户隔离测试、并发竞态测试、JWT 过期/篡改测试、邮件发送 mock 测试——全部未提及 |
| **采集服务多用户化最复杂** | 当前采集是单进程单任务模型。多用户时：每人独立配置 Twitter API/观察对象/采集频率，定时任务如何隔离调度？这是整个架构中最容易出问题的环节——但计划中对它着墨最少 |
| **Jinja2 服务端渲染的 SPOF** | 当前 Dashboar 是 Jinja2 SSR。多用户时每次页面请求都要走 FastAPI 渲染，没有缓存策略。如果用户量增长，CPU 瓶颈会很早出现 |

### 🟡 建议

| 风险 | 说明 |
|------|------|
| **前端演进路径不明确** | 方案架构图中提到"Web SPA (Vue/React)"但实施路线图中完全没有前端改造计划。Jinja2 SSR → SPA 是巨大跳跃 |
| **文档体系缺失** | 多用户系统需要 API 文档（OpenAPI/Swagger）、部署文档、运维 Runbook、用户手册。方案中未提及 |

---

## 五、总体评价与建议

### 整体评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 架构合理性 | 7/10 | 分层清晰，模块边界基本合理，渐进式策略务实 |
| 安全性 | 4/10 | 多处关键安全设计缺失（Token 吊销、加密密钥管理、跨租户防护） |
| 可扩展性 | 6/10 | 预留了扩展点但前端演进路径不明确 |
| 稳定性 | 5/10 | 缺乏降级策略、备份方案、迁移回滚方案 |
| 前瞻性 | 7/10 | 技术选型不激进，务实可落地 |

### 优先级排序的修复建议

1. **Phase 14 立即修复**：Refresh Token 存储+吊销、密码算法 bcrypt、登录限流、tenant_id migration 策略
2. **Phase 14 同步补全**：测试计划（至少跨租户隔离测试、JWT 测试）
3. **Phase 15 前置设计**：采集多用户调度方案、Redis 降级策略、PG 连接池规划
4. **Phase 16 调整范围**：Docker Compose 加健康检查，WAF 推迟到 Phase 17，i18n 加消息码体系

### 一句话总结

> 方案的整体方向正确、渐进策略务实，但在**安全细节**（Token 管理、密钥保护、租户隔离防线）和**运维韧性**（降级、备份、迁移回滚）两个维度有明显的设计缺口。这两类问题如果在 Phase 14 不做、到 Phase 16 就更难补，建议现在就把它们纳入 Phase 14 的范围，而不是推迟到后面。
