# Information Architecture Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 Twitter Investor Distiller 从偏工程化的「系统运维控制台」重构为围绕投资研究任务组织的「投资信号操作台」。

**Architecture:** 本次重构采用「轻量 IA 产品化改造」策略，优先调整卡片分组、用户可见命名、导航层级、流程引导与入口显性化，不改动核心采集、流水线、存储、向量化与 RAG 后端逻辑。前端继续复用现有 FastAPI + Jinja2 + 卡片 API 信封模式 `{html, data, error}`，通过 `CARD_CONFIG` 作为 IA 元数据权威来源。

**Tech Stack:** Python 3.13、FastAPI、Jinja2、SQLite、Chroma、原生 JavaScript、CSS Grid、现有卡片系统、pytest/HTTP smoke test。

---

## 1. 方案依据与实施原则

### 1.1 输入依据

本方案基于以下事实文件和代码现状制定：

- IA 分析报告：`docs/2026-06-10-information-architecture-analysis.md`
- 卡片配置中心：`src/cards/cards_config.py`
- Dashboard 模板与前端加载逻辑：`src/templates/base.html`
- Landing Page：`src/templates/landing.html`
- 流水线执行卡片：`src/cards/pipeline_execute.py`
- 标的映射卡片：`src/cards/functional_cards.py`
- 卡片 API：`src/interfaces/web_api.py`
- 执行类交互处理器：`src/interfaces/handlers_exec.py`
- RAG 对话引擎：`src/ai/chat_engine.py`

### 1.2 产品目标

当前产品已覆盖「采集 → 过滤 → 分析 → 行情补全 → 信号展示 → 决策辅助 → 推送」闭环，但用户界面仍偏工程控制台。本次重构目标是让用户心智从：

> 我在管理一个爬虫和任务系统

转为：

> 我每天打开一个投资信号操作台，先看重点，再判断行动，必要时追溯来源和维护数据

### 1.3 核心用户路径

重构后默认支持 5 条核心路径：

1. **每日查看**：进入控制台 → 今日信号 → 看共识标的、观点异动、热门板块、数据状态。
2. **投资决策**：进入投资决策 → 模拟选股 / 持仓诊断 / 历史胜率 / 智能问答。
3. **深度研究**：进入深度研究 → 看观点时间线、信息源关系、分析师画像。
4. **更新数据**：进入数据管理 → 采集内容 → 扫描新内容 → 运行分析流程。
5. **配置自动化**：进入通知与设置 → 自动采集 / 推送通知 / 高级工具。

### 1.4 技术原则

必须遵守当前项目的前端架构宪章：

- 卡片 API 继续返回 `{html, data, error}`。
- 不新增 Python `onclick`，所有交互使用 `data-action` + 全局事件委托。
- 所有前端请求走 `apiFetch()`。
- 卡片数据继续通过 dataclass schema 校验。
- DOM ID 使用卡片名前缀。
- 卡片槽位保留加载中、失败、空数据三态。
- 不重写前端框架，不引入 React/Vue，不拆微服务。

---

## 2. 目标信息架构

### 2.1 一级导航目标结构

| 一级导航 | 用户问题 | 包含卡片/模块 | 说明 |
|---|---|---|---|
| 今日信号 | 今天最值得看什么？ | 共识标的、观点异动、热门板块、加密资产信号、数据状态 | 默认第一屏，强调投资信号而非系统状态 |
| 投资决策 | 我该买/卖/持有什么？ | 分析师模拟选股、我的持仓诊断、历史胜率、智能问答 | 承接行动判断 |
| 深度研究 | 为什么？谁说的？历史怎么看？ | 观点时间线、信息源关系、分析师画像、生成分析师画像 | 承接研究与溯源 |
| 数据管理 | 数据是否新鲜？如何补数据？ | 处理队列、账号采集状态、手动采集、标的代码映射 | 承接数据来源和处理链路 |
| 通知与设置 | 如何自动化和配置？ | 自动采集、推送通知、高级工具 | 降低运维内容对普通路径的干扰 |

### 2.2 卡片迁移映射

| card name | 当前 Tab | 目标 Tab | 当前显示名 | 目标显示名 |
|---|---|---|---|---|
| `consensus` | 今日概览 | 今日信号 | 抱团标的榜 | 共识标的 |
| `anomaly` | 信号深挖 | 今日信号 | 异常言论预警 | 观点异动 |
| `rotation` | 今日概览 | 今日信号 | 板块热度榜 | 热门板块 |
| `crypto` | 今日概览 | 今日信号 | 加密货币行情 | 加密资产信号 |
| `system_status` | 今日概览 | 今日信号 | 系统概览 | 数据状态 |
| `role_picker` | 决策分析 | 投资决策 | 模拟选股 | 分析师模拟选股 |
| `portfolio` | 决策分析 | 投资决策 | 持仓诊断 | 我的持仓诊断 |
| `accuracy` | 决策分析 | 投资决策 | 分析师胜率榜 | 历史胜率 |
| `timeline` | 信号深挖 | 深度研究 | 情绪时间线 | 观点时间线 |
| `network` | 信号深挖 | 深度研究 | 信源关系图 | 信息源关系 |
| `portrait` | 分析师画像 | 深度研究 | 画像档案 | 分析师画像 |
| `portrait_generate` | 分析师画像 | 深度研究 | 生成新画像 | 生成分析师画像 |
| `pipeline_execute` | 系统运维 | 数据管理 | 任务执行台 | 处理队列 |
| `api_status` | 系统运维 | 数据管理 | 采集状态 | 账号采集状态 |
| `fetch_control` | 系统运维 | 数据管理 | 手动拉取 | 手动采集 |
| `asset_alias` | 系统运维 | 数据管理 | 代码别名库 | 标的代码映射 |
| `daemon` | 系统运维 | 通知与设置 | 自动采集开关 | 自动采集 |
| `telegram` | 系统运维 | 通知与设置 | Telegram 推送 | 推送通知 |
| `script_runner` | 系统运维 | 通知与设置 | 脚本工具箱 | 高级工具 |

---

## 3. 项目规划

### 3.1 分阶段策略

本次重构分 5 个阶段推进：

| 阶段 | 名称 | 目标 | 风险等级 | 可回滚性 |
|---|---|---|---|---|
| Phase 0 | 基线与保护网 | 建立测试基线、截图/HTML 基线、确认现有行为 | 低 | 不涉及业务改动 |
| Phase 1 | 命名与导航重组 | 调整 `CARD_CONFIG`、显示名、Tab 图标、状态文案 | 低 | 单文件回滚为主 |
| Phase 2 | 数据管理路径产品化 | 优化处理队列、标的映射、采集流程文案和三步引导 | 中 | 可逐卡片回滚 |
| Phase 3 | 入口补强 | 新增/显性化智能问答入口、监控账号入口设计 | 中 | 可关闭新增卡片 |
| Phase 4 | 验证、灰度与部署 | 完成回归、验收、文档、部署与监控 | 低 | 保留旧配置快照 |

### 3.2 不纳入本次范围

以下内容明确不在本次实施范围内：

- 不迁移 SQLite 到 PostgreSQL。
- 不重构为 React/Vue 单页应用。
- 不拆分微服务。
- 不大规模调整采集、LLM、向量化、任务执行后端逻辑。
- 不批量修改历史数据内容，仅做必要配置和文案迁移。

---

## 4. 技术架构设计

### 4.1 现有架构保持

```mermaid
flowchart LR
    A[FastAPI /dashboard] --> B[base.html]
    B --> C[GET /cards/meta]
    C --> D[CARD_CONFIG / CARD_DISPLAY]
    B --> E[GET /cards/{name}]
    E --> F[Card.get_data]
    F --> G[SQLite / JSON / CSV / scripts output]
    E --> H[Card.render]
    H --> I[{html, data, error}]
    I --> B
    B --> J[用户交互 data-action]
    J --> K[POST /cards/{name}/action]
```

本次重构只调整以下层：

1. **元数据层**：`CARD_CONFIG` 的 tab、排序、显示名、副标题。
2. **展示层**：`base.html` 的导航图标、顶部状态文案、流程提示区域。
3. **卡片文案层**：`pipeline_execute.py`、`functional_cards.py`、模板内用户可见文案。
4. **入口层**：新增或显性化智能问答、监控账号入口。

### 4.2 IA 元数据权威来源

继续将 `src/cards/cards_config.py` 作为 IA 配置权威来源：

- `CARD_CONFIG` 控制 tab key、tab label、tab order、card order、模板、刷新周期。
- `CARD_DISPLAY` 控制用户看到的中文标题和一句话说明。
- 卡片类的 `name`、路由、后端 action 不改名，避免破坏 API 和事件绑定。

### 4.3 推荐 Tab key

| key | label | order | icon |
|---|---|---:|---|
| `signals` | 今日信号 | 1 | 📡 |
| `decisions` | 投资决策 | 2 | 🎯 |
| `research` | 深度研究 | 3 | 🔍 |
| `data` | 数据管理 | 4 | 🗄️ |
| `settings` | 通知与设置 | 5 | ⚙️ |

### 4.4 兼容策略

为降低回归风险：

- 保持 `card.name` 不变。
- 保持 `/cards/{name}` 和 `/cards/{name}/action` 不变。
- 保持 `data-action` 名称不变，除非同步更新事件委托和后端处理。
- 保留旧 tab key 的兼容处理：如果 `sessionStorage.lastTab` 仍是旧值，应自动切换到第一个新 Tab，而不是空白页。

---

## 5. 内容重组策略

### 5.1 内容层级

重组后，页面内容优先级如下：

1. **结果优先**：共识标的、观点异动、热门板块优先于系统状态。
2. **行动其次**：模拟选股、持仓诊断、智能问答作为决策入口。
3. **溯源第三**：时间线、关系图、画像解释为什么。
4. **维护最后**：采集、处理队列、映射、自动化、脚本默认后置。

### 5.2 文案规范

统一采用「对象 + 用户动作/结果」命名：

- 不用「种子任务」，用「扫描新内容」。
- 不用「任务执行台」，用「处理队列」。
- 不用「代码别名库」，用「标的代码映射」。
- 不用「Daemon」，用「自动采集」。
- 不用「股价拉取」，用「补全行情」。
- 不用「数据清洗」，用「校准标的」。

### 5.3 处理队列三步引导

在 `pipeline_execute` 顶部增加流程说明：

```text
1. 采集内容：从监控账号获取新推文
2. 扫描新内容：把新推文加入处理队列
3. 运行分析流程：筛选推文、分析观点、补全行情、生成画像
```

该引导只做展示，不改变任务执行逻辑。

### 5.4 Landing Page 对齐

`src/templates/landing.html` 的五大能力改为与新 IA 一致：

1. 今日信号
2. 投资决策
3. 深度研究
4. 数据管理
5. 通知与设置

同时将「查看文档」从 `https://github.com` 改为项目 README 或暂时移除。

---

## 6. 用户界面优化

### 6.1 侧边栏

- 使用新 5 个一级导航。
- 图标对齐用户心智，不使用过多工程类图标。
- 保持当前 fixed sidebar 和 responsive 行为。
- 若用户上次保存的 `lastTab` 不存在，自动切换到 `signals`。

### 6.2 顶部状态栏

当前顶部状态栏有 `sb_daemon`、今日条数、累计条数、更新时间。建议：

- `Daemon 运行中` → `自动采集运行中`
- `Daemon 已停止` → `自动采集已停止`
- `今日 X 条` 保留。
- `累计 X` 保留。
- 后续可增加「待处理任务 X」但不作为 Phase 1 必做。

### 6.3 今日信号页

排序建议：

1. `consensus` 共识标的，headline。
2. `anomaly` 观点异动。
3. `rotation` 热门板块。
4. `crypto` 加密资产信号。
5. `system_status` 数据状态。

### 6.4 数据管理页

排序建议：

1. `pipeline_execute` 处理队列。
2. `api_status` 账号采集状态。
3. `fetch_control` 手动采集。
4. `asset_alias` 标的代码映射。

### 6.5 通知与设置页

排序建议：

1. `daemon` 自动采集。
2. `telegram` 推送通知。
3. `script_runner` 高级工具。

`script_runner` 后续可增加高级提示：

```text
高级工具用于手动触发后台脚本。普通情况下，请优先使用数据管理页的处理队列。
```

---

## 7. 数据迁移计划

### 7.1 数据影响评估

本次 IA 重构原则上不迁移业务数据，影响范围如下：

| 数据/配置 | 是否迁移 | 说明 |
|---|---|---|
| SQLite `data/twitter_data.db` | 否 | 不改表结构、不改数据 |
| Chroma 向量库 | 否 | 不改索引和检索逻辑 |
| `data/users.json` | 否 | 仅在 UI 上改为「监控账号/账号采集状态」 |
| `data/stock_alias.csv` | 否 | 文件结构不变，仅 UI 文案改为「标的代码映射」 |
| `data/pipeline/*` | 否 | 结果文件不变 |
| `sessionStorage.lastTab` | 轻量兼容 | 旧 tab key 失效时切到新默认 Tab |
| 用户可见导航名称 | 是 | 通过 `CARD_CONFIG` 和 `CARD_DISPLAY` 修改 |

### 7.2 配置迁移

只迁移 IA 配置：

- `overview` → `signals`
- `deep_dive` + `profiles` → `research`
- `operations` 拆为 `data` 与 `settings`
- `decisions` 保留 key 或仅改 label 为「投资决策」

### 7.3 回滚计划

实施前保存旧 `CARD_CONFIG` 片段到计划执行记录或 commit 历史。若出现导航空白、卡片丢失、自动刷新异常：

1. 回滚 `src/cards/cards_config.py`。
2. 回滚 `src/templates/base.html` 中 `TAB_ICONS` 和 lastTab 兼容逻辑。
3. 保留文案类修改不影响功能时可不回滚。

---

## 8. 实施时间表与里程碑

> 以下用阶段和里程碑表达，不假设具体日历排期。若单人执行，可按顺序推进；若多人执行，可将 Phase 1 与 Phase 2 的文案类任务并行。

| 阶段 | 主要任务 | 里程碑 | 验收输出 |
|---|---|---|---|
| Phase 0 | 建立基线、读取报告、确认测试命令 | M0 基线完成 | 当前页面可启动、`/cards/meta` 可返回 19 张卡片 |
| Phase 1 | 重组导航和显示名 | M1 新 IA 导航上线 | 侧边栏显示 5 个新导航，所有卡片仍可加载 |
| Phase 2 | 优化处理队列和标的映射文案 | M2 数据管理路径产品化 | 「扫描新内容 / 处理队列 / 标的代码映射」可见 |
| Phase 3 | Landing 对齐、新入口设计 | M3 首页和控制台心智一致 | Landing 五大能力与控制台一致 |
| Phase 4 | 回归测试、验收、部署 | M4 可部署版本 | HTTP smoke test、核心交互测试通过 |

---

## 9. 资源配置

### 9.1 角色分工

| 角色 | 责任 |
|---|---|
| 产品/IA 负责人 | 确认导航、命名、页面顺序、验收标准 |
| 前端/全栈工程师 | 修改 `cards_config.py`、`base.html`、卡片文案和事件兼容 |
| 后端工程师 | 确认卡片 API、action 分发、任务处理不受影响 |
| QA/验收 | 执行 smoke test、交互测试、截图对比 |
| 用户代表 | 按核心路径验证是否更容易理解 |

单人项目可由同一人承担所有角色，但验收时必须按角色视角逐项检查。

### 9.2 环境要求

- 使用项目当前 Python 环境。
- 不新增全局依赖。
- 若需要执行测试，优先使用项目已有测试命令；若未发现完整测试套件，则使用 HTTP smoke test。
- 所有改动通过 git 分阶段提交。

---

## 10. 风险评估

| 风险 | 等级 | 触发原因 | 缓解措施 | 验收检查 |
|---|---|---|---|---|
| 卡片丢失 | 中 | `CARD_CONFIG` tab/key/order 写错 | 保持 card name 不变，跑 `/cards/meta` 计数 | meta 返回 19 张卡片 |
| 默认页空白 | 中 | `sessionStorage.lastTab` 保存旧 key | `switchTab` 前校验 tab 是否存在 | 清空/保留 sessionStorage 均能进入默认页 |
| 事件失效 | 中 | 修改按钮文案时误改 `data-action` | 不改 action 名；如需改同步测试 | 点击扫描、执行、添加映射仍可用 |
| 用户误解「高级工具」 | 低 | 脚本工具仍可见 | 增加高级提示并后置 | 普通路径不需要进入高级工具 |
| 文案不统一 | 中 | 多处硬编码旧名称 | Grep 检查旧词 | 不再出现 Daemon/种子任务/代码别名库等用户可见词 |
| 样式破坏 | 低 | 新提示条 CSS 与暗色主题不一致 | 使用现有 CSS 变量 | 暗色模式正常，移动端不溢出 |
| 运行脚本超时 | 低 | 误触高级脚本 | 本次不改执行逻辑，只改提示 | 脚本卡片仍默认手动触发 |

---

## 11. 质量控制措施

### 11.1 静态检查

实施后必须检查：

- `CARD_CONFIG` 中每个 card name 唯一。
- `tab_order` 和 `order` 连续或至少排序稳定。
- `CARD_DISPLAY` 覆盖所有卡片。
- 用户可见旧词检索：
  - `种子任务`
  - `任务执行台`
  - `代码别名库`
  - `资产代码库`
  - `Daemon`
  - `股价拉取`
  - `运行校准`

### 11.2 API 检查

必须验证：

- `GET /cards/meta` 返回列表且包含所有卡片。
- `GET /cards/consensus` 返回 `{html, data, error}`。
- `GET /cards/pipeline_execute` 返回可渲染 HTML。
- `GET /dashboard` 返回 200。
- `GET /` 返回 200。

### 11.3 UI 检查

必须验证：

- 侧边栏显示 5 个一级导航。
- 每个导航至少有 2 张卡片，除非设计明确允许。
- 默认进入「今日信号」。
- 卡片标题和副标题显示正常。
- 加载中、失败、空数据状态仍可见。
- 移动端侧边栏折叠仍正常。

### 11.4 核心交互检查

必须验证：

- 处理队列中「扫描新内容」按钮仍触发原 `seed` 动作。
- 处理队列中执行选中任务仍触发原 task_type。
- 标的代码映射的添加、编辑、删除、跳过、恢复仍可用。
- 手动采集仍可提交。
- 自动采集开关仍可切换。
- Telegram 保存/测试仍可提交。

---

## 12. 详细实施任务

### Task 1: 建立当前 IA 基线

**Files:**
- Read: `docs/2026-06-10-information-architecture-analysis.md`
- Read: `src/cards/cards_config.py`
- Read: `src/templates/base.html`
- Read: `src/cards/pipeline_execute.py`

**Step 1: 记录当前卡片数量和 tab 分布**

运行项目后访问：

```bash
python -m uvicorn src.interfaces.web_api:app --host 127.0.0.1 --port 8000
```

另开终端检查：

```bash
python - <<'PY'
import requests
meta = requests.get('http://127.0.0.1:8000/cards/meta', timeout=10).json()
print(len(meta))
from collections import Counter
print(Counter(c['tab'] for c in meta))
print([(c['name'], c['tab'], c['title']) for c in meta])
PY
```

Expected:

- 返回 19 张卡片。
- 旧 tab 包括 `overview`、`decisions`、`deep_dive`、`profiles`、`operations`。

**Step 2: 保存基线结果**

将结果记录到实施日志或 commit message，不需要写入业务文件。

**Step 3: Commit**

本任务只读，不需要 commit。

---

### Task 2: 重构 CARD_CONFIG 导航分组

**Files:**
- Modify: `src/cards/cards_config.py:30-59`
- Test: `/cards/meta` HTTP smoke test

**Step 1: 修改 `CARD_CONFIG`**

将配置改为：

```python
CARD_CONFIG: dict[str, tuple[str, str, int, int, bool, bool, str | None, int]] = {
    # ── 今日信号（每天打开第一眼看到的投资重点） ──
    "consensus":       ("signals",   "今日信号",   1, 1, True,  False, "consensus",       600),
    "anomaly":         ("signals",   "今日信号",   1, 2, False, False, "anomaly",          600),
    "rotation":        ("signals",   "今日信号",   1, 3, False, False, "rotation",        600),
    "crypto":          ("signals",   "今日信号",   1, 4, False, False, None,              300),
    "system_status":   ("signals",   "今日信号",   1, 5, False, False, "system_status",    60),

    # ── 投资决策（该买什么？该卖什么？） ──
    "role_picker":     ("decisions", "投资决策",   2, 1, False, True,  None,                0),
    "portfolio":       ("decisions", "投资决策",   2, 2, False, True,  None,                0),
    "accuracy":        ("decisions", "投资决策",   2, 3, False, False, "accuracy",         300),

    # ── 深度研究（为什么？谁说的？历史怎么看？） ──
    "timeline":        ("research",  "深度研究",   3, 1, False, False, "timeline",         600),
    "network":         ("research",  "深度研究",   3, 2, False, False, "network",         3600),
    "portrait":        ("research",  "深度研究",   3, 3, False, False, None,             300),
    "portrait_generate":("research", "深度研究",   3, 4, False, False, None,               0),

    # ── 数据管理（数据是否新鲜？如何补数据？） ──
    "pipeline_execute":("data",      "数据管理",   4, 1, False, True,  None,              15),
    "api_status":      ("data",      "数据管理",   4, 2, False, False, "api_status",      30),
    "fetch_control":   ("data",      "数据管理",   4, 3, False, False, "fetch_control",    0),
    "asset_alias":     ("data",      "数据管理",   4, 4, False, False, None,             300),

    # ── 通知与设置（自动化、推送、高级工具） ──
    "daemon":          ("settings",  "通知与设置", 5, 1, False, False, "daemon",           5),
    "telegram":        ("settings",  "通知与设置", 5, 2, False, False, "telegram",         0),
    "script_runner":   ("settings",  "通知与设置", 5, 3, False, False, "script_runner",    0),
}
```

**Step 2: 运行 smoke test**

```bash
python - <<'PY'
from src.cards.cards_config import CARD_CONFIG
from collections import Counter
assert len(CARD_CONFIG) == 19
print(Counter(v[0] for v in CARD_CONFIG.values()))
PY
```

Expected:

- PASS。
- tab 计数为 `signals=5`、`decisions=3`、`research=4`、`data=4`、`settings=3`。

**Step 3: Commit**

```bash
git add src/cards/cards_config.py
git commit -m "refactor(ia): reorganize dashboard navigation tabs"
```

---

### Task 3: 更新 CARD_DISPLAY 用户可见命名

**Files:**
- Modify: `src/cards/cards_config.py:105-134`
- Test: `/cards/meta` title/subtitle 检查

**Step 1: 修改 `CARD_DISPLAY`**

将显示名调整为：

```python
CARD_DISPLAY: dict[str, tuple[str, str]] = {
    "consensus":       ("共识标的",       "多位分析师在相近时间同时看好的标的，共识分越高越值得关注"),
    "anomaly":         ("观点异动",       "检测分析师近期观点与以往的明显偏离，捕捉态度转折信号"),
    "rotation":        ("热门板块",       "近期被讨论热度快速上升的行业板块，捕捉资金轮动方向"),
    "crypto":          ("加密资产信号",   "被追踪分析师提及的加密资产价格与讨论热度"),
    "system_status":   ("数据状态",       "今日数据采集、处理进度与系统健康状态"),

    "role_picker":     ("分析师模拟选股", "让 AI 代入某位分析师的风格，针对指定板块给出选股方案"),
    "portfolio":       ("我的持仓诊断",   "粘贴你的持仓，AI 结合分析师观点给出加减仓建议"),
    "accuracy":        ("历史胜率",       "回溯每位分析师历史信号的真实收益与胜率"),

    "timeline":        ("观点时间线",     "分析师看多看空观点随时间的变化曲线"),
    "network":         ("信息源关系",     "分析师之间的关注与互动关系，发现潜在信息源头"),
    "portrait":        ("分析师画像",     "已生成的分析师投资风格画像，点击展开查看全文"),
    "portrait_generate":("生成分析师画像", "选择分析师与时间范围，让 AI 归纳其投资风格"),

    "pipeline_execute":("处理队列",       "查看并运行待处理的筛选、分析、补行情、画像等任务"),
    "api_status":      ("账号采集状态",   "采集 API 的额度、限流与各监控账号已采集条数"),
    "fetch_control":   ("手动采集",       "针对指定账号手动补采某一时间段的推文"),
    "asset_alias":     ("标的代码映射",   "维护「提及名称 → 标的代码」映射，提升识别准确率"),

    "daemon":          ("自动采集",       "启停后台自动采集进程，开启后定时抓取新推文"),
    "telegram":        ("推送通知",       "配置 Telegram 机器人，把重要信号推送到你的手机"),
    "script_runner":   ("高级工具",       "手动触发后台脚本，供调试、维护与批量生成信号使用"),
}
```

**Step 2: 检查所有卡片都有 display**

```bash
python - <<'PY'
from src.cards.cards_config import CARD_CONFIG, CARD_DISPLAY
missing = set(CARD_CONFIG) - set(CARD_DISPLAY)
assert not missing, missing
print('ok')
PY
```

Expected: `ok`

**Step 3: Commit**

```bash
git add src/cards/cards_config.py
git commit -m "refactor(ia): productize dashboard card names"
```

---

### Task 4: 更新 Dashboard tab 图标和旧 tab 兼容

**Files:**
- Modify: `src/templates/base.html:312-318`
- Modify: `src/templates/base.html:366-395`
- Test: 浏览器/HTTP smoke test

**Step 1: 更新默认顶部标题**

将：

```html
<span id="topbar_title" class="title">今日概览</span>
```

改为：

```html
<span id="topbar_title" class="title">今日信号</span>
```

**Step 2: 更新 `TAB_ICONS`**

将：

```javascript
var TAB_ICONS = {
  overview: '📊', decisions: '🎯', deep_dive: '🔍', profiles: '👤', operations: '⚙️'
};
```

改为：

```javascript
var TAB_ICONS = {
  signals: '📡',
  decisions: '🎯',
  research: '🔍',
  data: '🗄️',
  settings: '⚙️'
};
```

**Step 3: 增加旧 tab fallback**

将：

```javascript
var lastTab = sessionStorage.getItem('lastTab') || (TABS[0] ? TABS[0].key : '');
switchTab(lastTab);
```

改为：

```javascript
var lastTab = sessionStorage.getItem('lastTab') || (TABS[0] ? TABS[0].key : '');
if (!TABS.some(function(t) { return t.key === lastTab; })) {
  lastTab = TABS[0] ? TABS[0].key : '';
}
switchTab(lastTab);
```

**Step 4: Commit**

```bash
git add src/templates/base.html
git commit -m "refactor(ia): update dashboard navigation icons and fallback"
```

---

### Task 5: 更新顶部状态栏 Daemon 文案

**Files:**
- Modify: `src/templates/base.html`
- Test: grep + 页面检查

**Step 1: 搜索 Daemon 文案**

```bash
python - <<'PY'
from pathlib import Path
p = Path('src/templates/base.html')
for i, line in enumerate(p.read_text(encoding='utf-8').splitlines(), 1):
    if 'Daemon' in line:
        print(i, line)
PY
```

**Step 2: 替换用户可见文案**

替换规则：

- `Daemon 运行中` → `自动采集运行中`
- `Daemon 已停止` → `自动采集已停止`
- `Daemon` 单独出现在用户可见文本中 → `自动采集`

不要修改变量名如 `sb_daemon`，除非同步修改所有引用。

**Step 3: 验证**

```bash
python - <<'PY'
from pathlib import Path
text = Path('src/templates/base.html').read_text(encoding='utf-8')
assert 'Daemon 运行中' not in text
assert 'Daemon 已停止' not in text
print('ok')
PY
```

**Step 4: Commit**

```bash
git add src/templates/base.html
git commit -m "refactor(ia): rename daemon status copy"
```

---

### Task 6: 产品化处理队列文案

**Files:**
- Modify: `src/cards/pipeline_execute.py:137-141`
- Modify: `src/cards/pipeline_execute.py:196-218`
- Modify: `src/cards/pipeline_execute.py:254-263`
- Test: `/cards/pipeline_execute` smoke test

**Step 1: 更新任务类型显示名**

将：

```python
type_names = {
    "filter": "过滤筛选", "analyze": "推文分析",
    "fetch_price": "股价拉取", "fetch_crypto": "加密货币",
    "portrait": "画像生成", "clean": "数据清洗",
}
```

改为：

```python
type_names = {
    "filter": "筛选推文", "analyze": "分析观点",
    "fetch_price": "补全行情", "fetch_crypto": "补全加密行情",
    "portrait": "生成画像", "clean": "校准标的",
}
```

**Step 2: 更新 clean 区域标题和按钮**

替换：

- `资产代码库` → `标的代码映射`
- `🔄 运行校准` → `应用映射修正`
- placeholder `别名` → `提及名称`
- placeholder `代码` → `标的代码`
- 表头 `别名` → `提及名称`
- 表头 `代码` → `标的代码`
- 按钮 `填代码` → `填写代码`

**Step 3: 增加三步引导条**

在返回 HTML 的标题后加入：

```html
<div class="mb-sm" style="font-size:11px;color:var(--text-secondary);line-height:1.6">
  <span class="tag tag-ok">1 采集内容</span>
  <span class="text-secondary">→</span>
  <span class="tag tag-warn">2 扫描新内容</span>
  <span class="text-secondary">→</span>
  <span class="tag tag-ok">3 运行分析流程</span>
</div>
```

注意：不要新增 inline script，不要新增 onclick。

**Step 4: 更新标题和按钮**

替换：

- `<div class="card-title">流水线执行</div>` → `<div class="card-title">处理队列</div>`
- `🌱 种子任务` → `扫描新内容`

**Step 5: 验证旧词**

```bash
python - <<'PY'
from pathlib import Path
text = Path('src/cards/pipeline_execute.py').read_text(encoding='utf-8')
for bad in ['种子任务', '流水线执行</div>', '股价拉取', '运行校准', '资产代码库']:
    assert bad not in text, bad
print('ok')
PY
```

**Step 6: Commit**

```bash
git add src/cards/pipeline_execute.py
git commit -m "refactor(ia): productize processing queue copy"
```

---

### Task 7: 产品化标的代码映射卡片

**Files:**
- Modify: `src/cards/functional_cards.py:99-191`
- Test: `/cards/asset_alias` smoke test

**Step 1: 更新卡片标题**

替换：

- `资产代码库` → `标的代码映射`

**Step 2: 更新字段名**

替换：

- `别名` → `提及名称`
- `Ticker` → `标的代码`
- placeholder `代码` → `标的代码`
- `ticker 明确` → `代码明确`
- `填代码` → `填写代码`

**Step 3: 更新底部提示**

将：

```text
提示：点"填代码"自动回填表单，输入 ticker 后提交即可移入已确认列表。
```

改为：

```text
提示：点"填写代码"自动回填表单，输入标的代码后提交即可移入已确认列表。
```

**Step 4: 验证**

```bash
python - <<'PY'
from pathlib import Path
text = Path('src/cards/functional_cards.py').read_text(encoding='utf-8')
assert '资产代码库' not in text
assert '填代码' not in text
print('ok')
PY
```

**Step 5: Commit**

```bash
git add src/cards/functional_cards.py
git commit -m "refactor(ia): rename asset alias management UI"
```

---

### Task 8: 更新 Landing Page 信息架构表达

**Files:**
- Modify: `src/templates/landing.html:71-123`
- Test: `GET /` 页面检查

**Step 1: 更新 CTA 文案**

可将「进入控制台」保留，也可改为「进入信号台」。建议保留顶部按钮，Hero 主按钮改为：

```html
<a href="/dashboard" class="btn-primary">进入信号台</a>
```

**Step 2: 修正文档链接**

将：

```html
<a href="https://github.com" class="btn-secondary">查看文档</a>
```

改为以下二选一：

```html
<a href="/dashboard" class="btn-secondary">查看今日信号</a>
```

或如果已有内部文档路由，再指向真实文档。不要保留 `https://github.com` 泛链接。

**Step 3: 更新五大核心能力**

改为：

- 今日信号：共识标的、观点异动、热门板块，10 秒扫描今日重点。
- 投资决策：模拟选股、持仓诊断、历史胜率，用数据辅助行动。
- 深度研究：观点时间线、信息源关系、分析师画像，解释信号来源。
- 数据管理：监控账号、手动采集、处理队列、标的代码映射，保证数据新鲜。
- 通知与设置：自动采集、推送通知、高级工具，把重要信号送到手机。

**Step 4: Commit**

```bash
git add src/templates/landing.html
git commit -m "refactor(ia): align landing page with new architecture"
```

---

### Task 9: 新增智能问答入口设计稿或最小卡片

**Files:**
- Potential Create: `src/cards/chat_card.py`
- Modify: `src/cards/cards_config.py`
- Modify: `src/cards/__init__.py`
- Modify: `src/interfaces/web_api.py` or handler module
- Existing dependency: `src/ai/chat_engine.py`

**Decision:** 该任务建议作为 Phase 3 单独实施。若本轮只做 IA 轻量改造，可先只在方案中保留，不立即开发。

**Minimal product behavior:**

- 卡片名：`chat`。
- 显示名：`智能问答` 或 `问分析师库`。
- 所属 Tab：`decisions`。
- 用户输入问题，后端调用 `ChatEngine.answer(question)`。
- 返回回答文本，提示回答基于历史推文检索。

**Acceptance criteria:**

- 当未配置向量库或 OpenAI key 时，卡片必须显示可见错误，而不是静默失败。
- 回答区域必须展示「基于检索结果生成，仅供研究参考」。
- 不得编造行情数字；若问到实时价格，应提示需要先补全行情或查询行情源。

**Commit:**

```bash
git add src/cards/chat_card.py src/cards/cards_config.py src/cards/__init__.py src/interfaces/web_api.py
git commit -m "feat(ia): add investor research chat entry"
```

---

### Task 10: HTTP smoke test

**Files:**
- Potential Create: `tests/test_dashboard_ia.py` if tests directory exists and project已有pytest习惯
- Otherwise: run one-off smoke script

**Step 1: 启动服务**

```bash
python -m uvicorn src.interfaces.web_api:app --host 127.0.0.1 --port 8000
```

**Step 2: 执行检查脚本**

```bash
python - <<'PY'
import requests
base = 'http://127.0.0.1:8000'
for path in ['/', '/dashboard', '/cards/meta', '/cards/consensus', '/cards/pipeline_execute', '/cards/asset_alias']:
    r = requests.get(base + path, timeout=15)
    print(path, r.status_code, r.headers.get('content-type'))
    assert r.status_code == 200
meta = requests.get(base + '/cards/meta', timeout=10).json()
assert len(meta) == 19
labels = {c['tab_label'] for c in meta}
assert labels == {'今日信号', '投资决策', '深度研究', '数据管理', '通知与设置'}, labels
names = {c['name']: c for c in meta}
assert names['pipeline_execute']['title'] == '处理队列'
assert names['asset_alias']['title'] == '标的代码映射'
print('IA smoke test passed')
PY
```

Expected:

- 所有路径返回 200。
- meta 返回 19 张卡片。
- tab label 是 5 个新导航。
- 关键标题已替换。

**Step 3: Commit test if created**

如创建测试文件：

```bash
git add tests/test_dashboard_ia.py
git commit -m "test(ia): add dashboard architecture smoke tests"
```

---

### Task 11: 用户路径验收

**Files:**
- No code changes expected

**Step 1: 每日查看路径**

验收项：

- 打开 `/dashboard` 默认进入「今日信号」。
- 第一屏能看到「共识标的」。
- 能看到「观点异动」或其卡片占位/空状态。
- 「数据状态」不再比核心信号更靠前。

**Step 2: 数据更新路径**

验收项：

- 进入「数据管理」。
- 能看到「处理队列」。
- 能理解三步流程：采集内容 → 扫描新内容 → 运行分析流程。
- 「扫描新内容」按钮仍可触发任务生成。

**Step 3: 设置路径**

验收项：

- 进入「通知与设置」。
- 能找到「自动采集」和「推送通知」。
- 「高级工具」后置，不干扰日常操作。

**Step 4: 记录验收结果**

将验收结果记录到 PR 描述或工作日志。

---

### Task 12: 部署与回滚准备

**Files:**
- No mandatory code changes

**Step 1: 部署前检查**

```bash
git status --short
```

Expected:

- 无未提交改动，或仅有明确文档改动。

**Step 2: 标记回滚点**

```bash
git log --oneline -5
```

记录 IA 重构前的 commit hash。

**Step 3: 部署**

按项目当前部署方式重启 Web 服务。若只是本地自用：

```bash
python -m uvicorn src.interfaces.web_api:app --host 127.0.0.1 --port 8000
```

若已有 systemd/docker/远程部署，以现有部署脚本为准，不在本计划中新增。

**Step 4: 部署后验收**

重复 Task 10 和 Task 11。

**Step 5: 回滚策略**

若出现 P0 问题：

```bash
git revert <ia-refactor-commit-range>
```

优先回滚最近的 IA commit，不要手工大面积改回。

---

## 13. 最终验收标准

### 13.1 功能验收

- `/` 和 `/dashboard` 可正常访问。
- `/cards/meta` 返回 19 张卡片。
- 所有卡片仍通过 `/cards/{name}` 加载。
- 卡片 action 分发不受影响。
- 数据采集、扫描、任务执行、标的映射、自动采集、Telegram 配置等核心交互仍可用。

### 13.2 IA 验收

- 一级导航为：今日信号、投资决策、深度研究、数据管理、通知与设置。
- 「系统运维」不再作为一级导航出现。
- 「种子任务」不再作为用户可见主按钮出现，改为「扫描新内容」。
- 「任务执行台」改为「处理队列」。
- 「代码别名库/资产代码库」改为「标的代码映射」。
- 「Daemon」不再作为用户可见文案出现。

### 13.3 用户体验验收

- 新用户能在 10 秒内理解默认页展示什么。
- 用户能在 2 次点击内找到：更新数据、处理队列、手动采集、推送通知。
- 运维/高级工具被后置，不干扰投资信号浏览。
- 每张卡片标题和副标题能解释该模块的用途。

### 13.4 质量验收

- HTTP smoke test 全部通过。
- 无新增 console error。
- 无破坏移动端侧边栏折叠。
- 无新增 `onclick`。
- 所有新增 fetch 如有必须走 `apiFetch()`。
- 无静默失败；错误必须可见。

---

## 14. 推荐交付物

实施完成后应交付：

1. IA 重构代码变更 commit 列表。
2. HTTP smoke test 结果。
3. 关键页面截图：今日信号、投资决策、深度研究、数据管理、通知与设置。
4. 用户路径验收记录。
5. 如新增智能问答入口，需补充其错误态和无向量库状态截图。

---

## 15. 执行建议

推荐先执行 Task 1-8，完成低风险高收益的轻量 IA 产品化改造；Task 9「智能问答入口」作为第二轮功能增强单独评审。这样可以在不触碰核心数据链路的前提下，快速把产品从开发者控制台提升为投资研究信号操作台。
