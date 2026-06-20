# 投资信号蒸馏台 — Twitter Investor Distiller

采集精选 X/Twitter 投资者的公开发言，经过 AI 去噪、信号抽取、8 角色治理评审、估值与风险校验后，输出可追踪的投资信号、治理报告和仪表盘视图。

## 当前状态

| 项目 | 状态 |
| --- | --- |
| 主应用 | FastAPI + Jinja2 Dashboard |
| 管理后台 | FastAPI 独立后台，支持用户、活动、权限与封禁管理 |
| 数据层 | SQLite 默认开发环境，PostgreSQL/Redis/Celery 生产编排 |
| 前端 | 模板化页面 + 静态资源 + 模块化卡片 |
| 治理链路 | 8 角色评审、质量门、风险扫描、发布门、HTML 报告 |
| 测试 | 单元测试、集成测试、E2E 场景脚本、数据完整性检查 |
| 部署 | Dockerfile、Docker Compose、Nginx 反向代理配置 |

## 核心能力

- **信号采集与蒸馏**：从 X/Twitter 投资者内容中抽取标的、方向、置信度、理由和时间窗口。
- **8 角色治理评审**：value、growth、momentum、contrarian、macro、technical、quality、risk_mgr 多视角审查。
- **估值与金融数据**：支持 DCF、Comps、尽调清单、价格、基本面、技术指标、评级和财报日历。
- **多租户与权限**：支持租户配置、RBAC、JWT、Refresh Token 轮换和敏感配置加密。
- **管理与监控**：独立管理后台、活动日志、系统状态、流水线执行与治理链路可视化。
- **可迁移部署**：本地 SQLite 开发，生产可切换 PostgreSQL + Redis + Celery。

## 项目结构

```text
.
├── config/                  # 配置样例与本地配置入口
├── data/                    # 本地数据目录，部分运行数据不进入 GitHub
├── docs/                    # 架构、部署、迁移、优化和整理记录
├── scripts/                 # 数据导入、验证、E2E 和维护脚本
├── src/                     # 应用源码
│   ├── admin/               # 管理后台
│   ├── api/                 # API 基础模块
│   ├── cards/               # Dashboard 卡片系统
│   ├── data/                # 金融数据适配
│   ├── governance/          # 治理评审链路
│   ├── interfaces/          # Web API、路由和交互处理
│   ├── pipeline/            # 采集、过滤、分析、画像流水线
│   ├── security/            # 加密与安全工具
│   ├── storage/             # 数据库模型、缓存、别名仓库
│   ├── static/              # 前端静态资源
│   └── templates/           # Jinja2 页面模板
├── tests/                   # 单元测试与集成测试
├── Dockerfile
├── docker-compose.yml
├── docker-compose.prod.yml
├── nginx.conf
└── requirements.txt
```

## 本地开发

建议使用 Python 3.13。

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
python -m src.interfaces.web_api
```

默认 Dashboard 地址：

```text
http://localhost:8000
```

管理后台可单独启动：

```bash
python -m src.admin.app
```

默认管理后台地址：

```text
http://localhost:8001
```

## Docker 启动

开发编排：

```bash
docker compose up --build
```

生产编排：

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

生产模式默认包含 PostgreSQL、Redis、Celery Worker、Web 服务和 Nginx。

## 测试与验证

```bash
python -m pytest
python -m pytest tests/test_alias_repository.py tests/test_stock_alias_csv_integrity.py
python scripts/e2e_20_scenarios.py
```

如果当前环境没有安装 `pytest`，先运行：

```bash
pip install -r requirements.txt
```

轻量语法检查可用：

```bash
python - <<'PY'
import ast
from pathlib import Path
for root in [Path('src'), Path('scripts'), Path('tests')]:
    for path in root.rglob('*.py'):
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
print('AST syntax check passed')
PY
```

## 换设备接手流程

在新设备上执行：

```bash
git clone https://github.com/Miss0x/twitter-investor-distiller.git
cd twitter-investor-distiller
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
cp config/.env.example config/.env
```

然后手动补充 `config/.env` 中的密钥、API Key、数据库地址等本地私密配置。

如果要恢复当前设备上的完整运行态，还需要从旧设备单独复制下面这些未进入 GitHub 的内容。

## 不会同步到 GitHub 的内容

以下内容默认不会、也不应该传到 GitHub，需要你按需单独保存或迁移：

| 类型 | 路径/示例 | 原因 |
| --- | --- | --- |
| 私密配置 | `config/.env`、`.env`、`.env.local` | 可能包含 API Key、JWT 密钥、数据库密码 |
| 采集会话 | `data/cookies.json`、`data/sessions.jsonl` | 登录态、Cookie 和会话信息敏感 |
| 加密主密钥 | `data/.master_key` | 用于解密本地敏感配置，不能公开 |
| 租户私有配置 | `data/tenants/` | 可能包含用户、租户和私有参数 |
| 原始采集数据 | `data/raw/`、`data/processed/` | 体积大，且可能包含未清洗数据 |
| 媒体文件 | `data/media/`、`*.jpg`、`*.png`、`*.mp4` | 体积大，不适合直接放 Git |
| 诊断与向量库 | `data/diagnostics/`、`data/vector_db/` | 本地生成，可重建或单独备份 |
| 治理运行产物 | `data/governance/` | 运行报告和中间产物，按需归档 |
| 运行日志 | `logs/*.log`、`logs/e2e_shots/` | 临时调试产物 |
| 本地记忆 | `.workbuddy/`、`.codebuddy/` | AI 工作区记忆，不属于项目源码 |
| 本地覆盖率/缓存 | `.pytest_cache/`、`.coverage`、`__pycache__/` | 可重建缓存 |

如果希望新设备完全延续旧设备的运行态，建议额外压缩备份：

```bash
# 在旧设备执行，注意不要上传到公开仓库
zip -r local-runtime-backup.zip config/.env data/cookies.json data/.master_key data/tenants data/vector_db data/governance
```

## GitHub 同步建议

适合提交到 GitHub：

- `src/` 源码
- `tests/` 测试
- `scripts/` 可复用脚本
- `docs/` 长期文档
- `config/.env.example` 配置样例
- `Dockerfile`、`docker-compose*.yml`、`nginx.conf`
- `.github/` CI 或仓库配置
- 小型样例数据、别名表和必要的 SQLite 开发基线数据

不建议提交到 GitHub：

- 真实密钥、Cookie、会话文件
- 大体积媒体、向量库、运行报告、日志截图
- 个人工作记忆、IDE 缓存、临时脚本和一次性诊断文件

## 重要文档

| 文档 | 说明 |
| --- | --- |
| `docs/DEPLOY.md` | 部署说明 |
| `docs/architecture-audit.md` | 架构审计与风险建议 |
| `docs/phase18-migration-guide.md` | PostgreSQL、Redis、Celery 迁移说明 |
| `docs/optimization-closure-2026-06-20.md` | 本阶段优化闭环记录 |
| `docs/project-cleanup-2026-06-20.md` | 项目结构整理记录 |
| `docs/archive/` | 历史计划、临时脚本和阶段归档 |

## 当前交接备注

- 当前主分支为 `master`。
- 当前远端为 `https://github.com/Miss0x/twitter-investor-distiller.git`。
- 新设备接手的关键是：先拉 GitHub 代码，再手动恢复私密配置和必要运行数据。
- GitHub 负责同步代码、测试、文档和可公开配置样例；不负责同步本地密钥、Cookie、AI 工作记忆和运行缓存。
