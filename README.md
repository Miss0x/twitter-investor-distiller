# 投资信号蒸馏台 — Twitter Investor Distiller

采集精选 X/Twitter 投资者的发言 → AI 分析 → 8 角色治理评审 → 实时信号输出。

## 系统概览

| 指标 | 数值 |
|------|------|
| Dashboard 卡片 | 28 张 (5 标签页) |
| 测试覆盖 | 151 tests (0 失败) |
| 源文件 | 150+ |
| 架构 | FastAPI + SQLAlchemy + Jinja2 + SQLite/PostgreSQL |
| 部署 | Docker Compose 一键启动 |

## 核心能力

- **信号采集**: Twitter 推文 → AI 去噪 → 标的/方向/置信度
- **8 角色治理**: value / growth / momentum / contrarian / macro / technical / quality / risk_mgr
- **估值工具**: DCF / Comps / DD 尽调清单
- **金融数据**: 实时价格 / 基本面 / 技术指标 / 分析师评级 / 财报日历
- **多用户体系**: RBAC + Fernet AES 加密 + JWT + Refresh Token 轮换
- **管理后台**: 独立站点 (port 8001)，用户/活动/封禁管理

## 快速开始

```bash
# 开发模式 (SQLite)
pip install -r requirements.txt
python -m src.interfaces.web_api       # Dashboard: http://localhost:8000
python -m src.admin.app                # 管理后台: http://localhost:8001

# 生产模式 (PostgreSQL + Redis + Celery)
docker-compose -f docker-compose.prod.yml up -d
# Dashboard: http://localhost:8080
# 管理后台: http://localhost:8001
```

## 文档

| 文档 | 说明 |
|------|------|
| [10 用户场景](docs/product/10-user-scenarios-code-mapping.md) | 完整用户旅程 + 代码映射 |
| [UZI-Skill 对比](docs/uzi-comparison.md) | 与对标项目 22 维 × 17 模型的终局对标 |
| [架构审计](docs/architecture-audit.md) | 安全/性能/并发/优化建议 |
| [Phase 18 迁移](docs/phase18-migration-guide.md) | PostgreSQL + Redis + Celery 迁移指南 |
| [历史计划](docs/archive/) | 各阶段开发计划归档 |

## 技术栈

**后端**: Python 3.13, FastAPI, SQLAlchemy, Jinja2, Celery, jose JWT
**数据库**: SQLite (默认) / PostgreSQL 16 (生产)
**缓存**: 进程内存 / Redis 7 (生产)
**向量库**: ChromaDB (可选，用于 RAG)
**前端**: Jinja2 模板 + CSS Grid + vanilla JS 事件委托
**安全**: Fernet AES-128-CBC, JWT HS256, CORS, 限流, CSRF

## 采集目标

| 分析师 | 画像 | 账号 |
|--------|------|------|
| TJ_Research | 宏观趋势型，准确率 46% | @TJ_Research |
| dearbaibabybus | 成长波段型，准确率 45% | @dearbaibabybus (原 frankyluan) |
