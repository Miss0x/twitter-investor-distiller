# 多用户商用化系统架构方案

> **适用规模**：百级到万级用户，SaaS 模式投资研究工具
> **当前基础**：Python FastAPI + Jinja2 + SQLite + 单机部署
> **设计原则**：渐进式演进，不过度工程化；每层可独立升级

---

## 一、架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                        前端层                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│  │  Web SPA │  │ 移动端   │  │ 小程序   │                   │
│  │ (Vue/React)│ │ (PWA)   │  │ (微信)   │                   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                   │
│       └──────────────┼─────────────┘                        │
│                      ▼                                       │
│              CDN / OSS 静态资源                               │
├─────────────────────────────────────────────────────────────┤
│                       网关层                                 │
│  ┌──────────────────────────────────────────────────┐       │
│  │  Nginx / API Gateway                              │       │
│  │  · SSL 卸载  · 限流  · WAF  · 路由转发           │       │
│  └──────────────────────┬───────────────────────────┘       │
├─────────────────────────────────────────────────────────────┤
│                       服务层                                 │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐           │
│  │ 用户服务 │ │ 采集服务 │ │ 分析服务 │ │ 通知服务 │           │
│  │ ·注册/登录│ │ ·X API   │ │ ·LLM    │ │ ·Telegram│           │
│  │ ·RBAC   │ │ ·调度    │ │ ·治理   │ │ ·WebPush │           │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘           │
│       └────────────┼────────────┼───────────┘               │
│                    ▼            ▼                            │
│            ┌───────────┐  ┌───────────┐                     │
│            │ 消息队列   │  │ 任务队列   │                     │
│            │ (Redis)   │  │ (RQ/Celery)│                     │
│            └───────────┘  └───────────┘                     │
├─────────────────────────────────────────────────────────────┤
│                       数据层                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ PostgreSQL│ │  Redis   │ │  MinIO    │ │ ChromaDB │       │
│  │ 业务数据  │ │ 缓存/会话 │ │ 文件存储  │ │ 向量检索  │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
├─────────────────────────────────────────────────────────────┤
│                     运维/监控                                │
│  Docker Compose / K8s  ·  Prometheus  ·  ELK  · CI/CD       │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、用户体系

### 2.1 用户模型

```
User
├── id, email, password_hash
├── nickname, avatar_url
├── role: "super_admin" | "admin" | "member" | "viewer"
├── status: "active" | "suspended" | "pending"
├── plan: "free" | "pro" | "enterprise"
├── quota: {daily_llm_calls: 50, tracked_users: 5, ...}
├── created_at, last_login_at
└── settings (JSON): {llm: {...}, twitter: {...}, telegram: {...}}
```

### 2.2 权限模型 (RBAC)

| 角色 | 权限 |
|------|------|
| `super_admin` | 全部权限：用户管理、系统配置、计费、所有数据 |
| `admin` | 管理自己的团队：邀请/移除成员、查看团队数据 |
| `member` | 标准功能：配置LLM/Twitter/Telegram、管理观察对象、查看治理信号 |
| `viewer` | 只读：查看信号和报告，不能修改配置 |

### 2.3 认证流程

```
注册 → 邮箱验证 → 密码登录 → JWT Token (Access 15min + Refresh 7d)

可选：GitHub OAuth / Google OAuth 第三方登录
```

### 2.4 实现策略

- **Phase 1（当前→近期）**：email/password + JWT，单用户配置扩展为 User.settings
- **Phase 2（商用）**：引入 OAuth，RBAC 表，多租户数据隔离

---

## 三、数据架构

### 3.1 多租户隔离策略

采用**共享数据库 + tenant_id 字段隔离**（最适合百级用户规模）：

```sql
-- 所有业务表增加 tenant_id
ALTER TABLE tracked_users ADD COLUMN tenant_id UUID;
ALTER TABLE analysis_results ADD COLUMN tenant_id UUID;
ALTER TABLE governance_packages ADD COLUMN tenant_id UUID;

-- 查询自动过滤（通过 SQLAlchemy 事件或中间件注入）
SELECT * FROM analysis_results WHERE tenant_id = current_user().tenant_id;
```

### 3.2 数据库选型

| 数据类型 | 选型 | 原因 |
|---------|------|------|
| 业务数据（用户/配置/任务/治理） | PostgreSQL | 事务、JSON字段、全文搜索、成熟生态 |
| 缓存/会话/限流 | Redis | 高性能KV、发布订阅、队列 |
| 文件（报告/截图/用户上传） | MinIO (S3兼容) | 自建或云OSS，成本可控 |
| 向量检索 | ChromaDB 或 pgvector | pgvector 可与业务库合一，减少组件 |

### 3.3 演进路径

```
SQLite（当前）
  → PostgreSQL + Redis（多用户上线时）
    → 读写分离 + 连接池（百级用户）
      → 分库分表（万级用户，很少需要）
```

---

## 四、安全体系

### 4.1 传输与认证

| 层级 | 方案 |
|------|------|
| HTTPS | Nginx SSL 终止，Let's Encrypt 自动续期 |
| API 鉴权 | JWT (Access + Refresh Token)，前端存 HttpOnly Cookie + CSRF Token |
| 密钥存储 | 用户 LLM/Twitter Key 使用 AES-256-GCM 加密存储，不在日志/API 响应中暴露 |

### 4.2 防御措施

| 威胁 | 措施 |
|------|------|
| SQL 注入 | SQLAlchemy 参数化查询，禁止拼接 SQL |
| XSS | Jinja2 自动转义 + CSP Header + 前端 sanitize |
| CSRF | SameSite Cookie + CSRF Token |
| 暴力破解 | 登录失败 5 次锁定 15 分钟 + Redis 限流 |
| 敏感数据 | API Key 存储加密，日志自动脱敏 |

### 4.3 审计日志

```python
# 关键操作记录
AuditLog(
    tenant_id, user_id, action,  # "config.llm_changed", "observation.added"
    resource_type, resource_id,
    ip_address, user_agent,
    timestamp
)
```

---

## 五、高可用与性能

### 5.1 部署拓扑（百级用户）

```
                  ┌──── Nginx ────┐
                  │  SSL + 限流   │
                  └───────┬───────┘
                          │
            ┌─────────────┼─────────────┐
            ▼             ▼             ▼
      ┌──────────┐ ┌──────────┐ ┌──────────┐
      │ FastAPI  │ │ FastAPI  │ │ Worker   │
      │  实例 1  │ │  实例 2  │ │ (Celery) │
      └────┬─────┘ └────┬─────┘ └────┬─────┘
           └────────────┼────────────┘
                        ▼
            ┌────────────────────┐
            │ PostgreSQL + Redis │
            └────────────────────┘
```

### 5.2 关键优化

| 场景 | 方案 |
|------|------|
| 静态资源 | Nginx 直接 serve / CDN |
| LLM 调用 | 异步任务队列，避免 API 超时 |
| 数据采集 | 定时任务 (Celery Beat) + 频率控制 |
| 治理流水线 | 异步执行，结果写入后 WebSocket 推送 |

---

## 六、运维监控

### 6.1 最低可行监控（上线即需）

```
Docker Compose 部署
├── FastAPI × 2
├── PostgreSQL
├── Redis
├── Celery Worker + Beat
├── Nginx
└── Prometheus + Grafana (监控面板)
```

### 6.2 日志与告警

- 应用日志 → stdout → Docker logs → Loki/ELK（可选）
- 错误告警 → Sentry（推荐，有免费额度）
- 服务健康 → Uptime Kuma（自建）

---

## 七、商用化特性

### 7.1 多语言 i18n

```
locales/
├── zh-CN/  (默认)
├── en/
└── ja/    (可选)
```

策略：前端 Jinja2 `{% trans %}` + JS `Intl`，后端 API 错误消息从 JSON 翻译表加载。

### 7.2 计费模型

| 套餐 | 价格 | 包含 |
|------|------|------|
| Free | ¥0/月 | 跟踪 3 人，每日 10 次 AI 问答，基础治理 |
| Pro | ¥29/月 | 跟踪 20 人，每日 100 次 AI 问答，完整治理+辩论 |
| Team | ¥99/月 | 5 个子账号，共享观察池，API 访问 |

### 7.3 灰度发布

```
用户 → Nginx
        ├── 90% → stable 版本
        └── 10% → canary 版本 (通过 Cookie 或 header 路由)
```

---

## 八、实施路线图

```
Phase 14（本周）
├── 用户表 + 注册/登录 API
├── JWT 鉴权中间件（Refresh Token 轮换 + 重用检测 + 家族撤销）
├── 现有数据加 tenant_id 隔离（含迁移脚本与默认租户回填）
├── 前端登录页 + 个人设置页
├── 加密密钥管理（Fernet + ENCRYPTION_KEY 环境变量）
└── 跨租户隔离测试防线

Phase 15（2 周）
├── PostgreSQL 迁移（含双写校验）
├── Redis 缓存层（含降级策略）
├── 采集多用户调度（APScheduler 每用户独立 Job + 频率队列）
├── 计费模型 + 配额限制（Redis 原子计数器）
├── 审计日志基础（按月分区 + 90 天清理）
└── Celery 异步任务（仅 LLM 调用等重任务，治理链路保持同步）
```

---

## 九、Phase 14 关键设计 —— 评审后补全

### 9.1 JWT Refresh Token 轮换与重用检测

基于 Auth0/IETF 最佳实践和 FastAPI 社区验证方案，采用 **Refresh Token Rotation + Reuse Detection + Family Revocation** 模式。

**数据库模型：**

```python
class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id          = Column(UUID, primary_key=True, default=uuid4)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_hash  = Column(String(64), unique=True, nullable=False)  # SHA-256
    family      = Column(UUID, nullable=False)  # 轮换链标识
    used        = Column(Boolean, default=False)  # 已被轮换过的标记
    expires_at  = Column(DateTime, nullable=False)
    created_at  = Column(DateTime, default=datetime.utcnow)
```

**完整流程：**

```
登录 → 发放 Access Token (15min) + Refresh Token (30天)
        ├── Refresh Token 原始值返回给前端（HttpOnly Cookie）
        └── Refresh Token SHA-256 哈希存入 refresh_tokens 表

刷新 → 前端用 Refresh Token 请求 /auth/refresh
        ├── 1. 查 refresh_tokens 表中 token_hash 匹配记录
        ├── 2. 如果记录 used=True → 重用攻击！撤销整个 family，返回 401
        ├── 3. 检查 expires_at，过期返回 401
        ├── 4. 标记旧记录 used=True（轮换）
        ├── 5. 同一 family 下创建新 RefreshToken 记录
        └── 6. 返回新 Access Token + 新 Refresh Token

登出 → 将当前 family 下所有记录的 used 设为 True
```

**关键安全决策：**
- Refresh Token 存 HttpOnly + Secure + SameSite=Lax Cookie，path=/auth/refresh（不随每个请求发送）
- Access Token 仅存在内存（JS 变量），不存 local/sessionStorage
- 每个用户的并发 RefreshToken family ≤ 5（限制多设备），超出时撤销最旧的 family

### 9.2 API Key 加密存储方案

使用 Python `cryptography` 库的 **Fernet** 对称加密（AES-128-CBC + HMAC认证）：

```python
from cryptography.fernet import Fernet
import os, base64

# 初始化：从环境变量读取主密钥
_ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not _ENCRYPTION_KEY:
    raise RuntimeError("ENCRYPTION_KEY 环境变量未设置，无法启动")
_fernet = Fernet(_ENCRYPTION_KEY.encode())  # Fernet 要求 base64 编码的 32 字节密钥

def encrypt_api_key(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()

def decrypt_api_key(ciphertext: str) -> str:
    return _fernet.decrypt(ciphertext.encode()).decode()
```

**密钥管理约束：**
- `ENCRYPTION_KEY` 通过环境变量注入，不在代码/配置文件中
- 生成密钥：`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- 密钥丢失 = 所有用户 API Key 永久不可恢复。部署时备份密钥到安全位置（1Password/密码管理器）
- Phase 17 可升级为 AWS KMS / HashiCorp Vault

**存储对比：**

| 方案 | 安全性 | 复杂度 | 适用阶段 |
|------|--------|--------|---------|
| 明文存储 | ❌ 数据库泄露=全部 Key 泄露 | 最低 | 开发测试 |
| Fernet + 环境变量 | ✅ 数据库泄露不会暴露 Key | 低 | Phase 14-16 |
| KMS / Vault | ✅ 企业级密钥管理 | 高 | Phase 17+ |

### 9.3 存量数据 tenant_id 迁移策略

**三步迁移法：**

```
Step 1 — 创建默认租户
├── 系统中第一个用户注册时，自动创建 tenant_id="default"
├── 如果已有用户，写迁移脚本：INSERT INTO tenants (id, name) VALUES ('default', '默认工作区')

Step 2 — 回填存量数据
├── 所有业务表 ALTER TABLE ADD COLUMN tenant_id VARCHAR(36) DEFAULT 'default'
├── 如果没有已有数据，直接设置 DEFAULT 即可
├── 如果有已有数据（如分析结果、治理包、推文）：
│     UPDATE analysis_results SET tenant_id = 'default' WHERE tenant_id IS NULL;
│     UPDATE governance_packages SET tenant_id = 'default' WHERE tenant_id IS NULL;
│     ... 逐表执行
└── 验证：SELECT COUNT(*) FROM each_table WHERE tenant_id IS NULL;  — 必须为 0

Step 3 — 切换防线
├── 部署新版本代码（SQLAlchemy 中间件自动注入 tenant_id）
├── 删除 DEFAULT 约束（避免新数据意外继承 default tenant）
│     ALTER TABLE analysis_results ALTER COLUMN tenant_id DROP DEFAULT;
└── 运行跨租户隔离测试：租户 A 的 Token 不能读取租户 B 的数据
```

### 9.4 采集多用户调度方案

当前采集是手动触发 + 简单的后台循环。多用户时需要每人独立的采集配置和频率控制。

**方案：APScheduler + 数据库任务表**

```
┌─────────────────────────────────────────────────┐
│                  调度层                           │
│  APScheduler (进程内)                             │
│  ├── Job: tenant_a_fetch → 每 30 分钟            │
│  ├── Job: tenant_b_fetch → 每 60 分钟            │
│  └── Job: tenant_c_fetch → 每天 1 次             │
│                                                  │
│  每个 Job 执行时:                                 │
│    1. 查 tenant 的 twitter 配置 (独立 API Key)    │
│    2. 查 tenant 的观察对象列表                    │
│    3. 推入 Celery 队列: fetch_tweet(user, tenant) │
│    4. Celery Worker 执行实际 API 调用            │
│                                                  │
│  Job 生命周期管理:                                │
│    · 用户注册 → 创建 Job (默认频率)               │
│    · 用户修改频率 → 更新 Job trigger              │
│    · 用户删除 → 删除 Job                          │
│    · 服务重启 → 从数据库恢复所有 Job              │
└─────────────────────────────────────────────────┘
```

**为什么选 APScheduler 而不是 Celery Beat：**
- APScheduler 支持运行时动态增删 Job（Celery Beat 改 schedule 需要重启 Worker）
- 每个用户可能有不同的采集频率和观察对象，需要频繁修改调度计划
- APScheduler 的 SQLAlchemyJobStore 可以将 Job 持久化到数据库，重启不丢失
- 适合百级用户的轻量场景，不需要引入额外的 Beat 进程

**限流保护：**
```python
# 每个用户独立的速率限制
RATE_LIMITS = {
    "twitterapi_io": {"requests_per_minute": 30, "cooldown_seconds": 60},
    "official":      {"requests_per_minute": 15, "cooldown_seconds": 900},  # X API 更严格
}
# 超过限制自动排队，等待下一个时间窗口
```

**Phase 14 先做什么：**
Phase 14 先只支持当前单用户的采集调度不变，但把调度逻辑包装成接口，预留 `tenant_id` 参数。到 Phase 15 再加 APScheduler 的动态多 Job 管理。├── JWT 鉴权中间件
├── 现有数据加 tenant_id 隔离
└── 前端登录页 + 个人设置页

Phase 15（2 周）
├── PostgreSQL 迁移
├── Redis 缓存层
├── 计费模型 + 配额限制
└── 审计日志基础

Phase 16（1 月+）
├── 多语言 i18n
├── Celery 异步任务
├── Docker Compose 部署方案
└── Prometheus 监控

Phase 17（商用上线）
├── OAuth 第三方登录
├── 灰度发布
├── 工单/客服系统
└── CDN + WAF
```

---

## 九、与本项目的对接路径

当前项目是 FastAPI + Jinja2 + SQLite 单用户。演进策略是**渐进式改造**，不是推倒重来：

1. **不改堆栈**：继续 Python + FastAPI + SQLAlchemy，加 PostgreSQL 只是换 URL
2. **不拆分微服务**：保持模块化单体，用目录边界划定服务域
3. **先做数据隔离**：`tenant_id` 字段是后续一切多用户功能的前提
4. **后端先行，前端跟进**：先加 JWT 鉴权中间件，再改造前端为登录态页面

**下一步行动：Phase 14 用户体系**，从单用户配置中心自然扩展为多用户系统。
