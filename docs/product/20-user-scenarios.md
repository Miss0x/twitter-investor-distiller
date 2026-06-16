# 投资信号蒸馏台 — 20 用户场景 × 代码映射验证

> 每个用户行为 → 对应代码文件 + 端点/行号 | 验证日期：2026-06-17
> 覆盖全部 **28 张 Dashboard 卡片**、**39 个 API 端点**、**6 种 Pipeline 任务**、**8 阶段治理管线**、**管理后台全功能**

---

## 场景 1：理财小白林悦 — 第一次注册和探索

**人物**：26 岁，互联网运营，刚开户半年。

| # | 用户行为 | 功能 | 代码路径 | 状态 |
|---|---------|------|---------|------|
| 1 | 打开 `localhost:8000` | 产品首页 | `src/templates/landing.html` → served by `web_api.py` `serve_landing()` | ✅ |
| 2 | 看到 Hero | Hero 区 + 功能卡片 | `landing.html` L76-99 `.hero` CSS → 六大核心能力 L103-135 `.features-grid` | ✅ |
| 3 | 点「免费注册」Modal | 注册表单 | `landing.html` L167-178 `#modal-register` → JS `showModal('register')` L152 | ✅ |
| 4 | 填写邮箱+用户名+密码 | 注册 API | `POST /auth/register` → `web_api.py` `auth_register()` → `src/admin/auth.py` `hash_password` → `src/storage/auth_models.py` `User` | ✅ |
| 5 | 注册成功自动登录 | 自动登录跳转 | `landing.html` JS L157-163: 注册后调 `POST /auth/login` → 303 → `/dashboard` | ✅ |
| 6 | 看 Dashboard 骨架屏 | 骨架屏渲染 | `src/templates/base.html` 卡片占位 + `cards_config.py` 28 张卡片按 tab 渲染 | ✅ |
| 7 | 看侧边栏标签 | 5 个标签页 | `base.html` JS: 从 `CARD_CONFIG` 按 `tab` 分组 → `signals/decisions/research/data/settings` | ✅ |
| 8 | 进入「用户配置中心」 | 配置卡片 | `src/cards/config_center_card.py` → `_current_request` contextvar → `PerUserConfig` load_masked() | ✅ |
| 9 | 看到空 LLM 配置 | 空状态引导 | `src/templates/cards/config_center.html`: 空白输入框 + 占位符 "API Key" | ✅ |

**完成度：100%** | 代码覆盖：6 个文件，3 个端点

---

## 场景 2：入门投资者陈志远 — 第一次配置和使用

**人物**：32 岁，程序员，有 OpenAI Key。

| # | 用户行为 | 功能 | 代码路径 | 状态 |
|---|---------|------|---------|------|
| 1 | 登录 Dashboard | JWT 认证 | `POST /auth/login` → `web_api.py` `auth_login()` → `src/admin/auth.py` `create_access_token`(HS256, 30min) + `src/admin/refresh_token.py` `create_refresh_family`(7d rotation) | ✅ |
| 2 | 配 LLM：api.openai.com + sk-xxx | 加密保存 | `POST /api/config/llm` → `web_api.py` → `src/multi_tenant/config.py` `PerUserConfig.save_section("llm", {...})` | ✅ |
| 3 | LLM 密钥加密到磁盘 | Fernet AES 加密 | `src/security/crypto.py` `encrypt_config(data, user_key)` → Fernet(AES-128-CBC+HMAC) → `data/tenants/{id}/config.json` (密文) | ✅ |
| 4 | "配置已保存，立即生效" | ChatEngine 热加载 | `multi_tenant/config.py` `apply_llm_config()` → 设环境变量 + `src/ai/chat_engine.py` `reload_config()` → 重建 OpenAI 客户端 | ✅ |
| 5 | 配 Twitter：twitterapi.io | 加密保存 | `POST /api/config/twitter` → `web_api.py` → `PerUserConfig.save_section("twitter", {...})` | ✅ |
| 6 | 配 Telegram Bot Token | 加密保存 | `POST /api/config/telegram` → `web_api.py` → `PerUserConfig.save_section("telegram", {...})` | ✅ |
| 7 | 添加观察 @TJ_Research | 添加观察对象 | `POST /api/config/observations/add` → `web_api.py` → `PerUserConfig.add_observation("TJ_Research")` | ✅ |
| 8 | 点「开始采集」 | 流水线采集 | `src/cards/pipeline_control.py` → pipeline_execute card → `src/pipeline/task_executor.py` → `src/crawler/twitterapi_fetcher.py` `fetch_user_tweets()` | ✅ |
| 9 | 看到信号："NVDA 看多" | 信号生成卡片 | `src/cards/` 各卡片 → AI 分析：情感→标的→方向→置信度→证据 | ✅ |
| 10 | 观点时间线 | 历史推文时间线 | `src/cards/functional_cards.py` `TimelineCard` → 按时间排列推文数据 | ✅ |

**完成度：100%** | 代码覆盖：10 个文件，8 个端点

---

## 场景 3：中级投资者王思琪 — 信号治理和评审

**人物**：35 岁，金融分析师，炒股 5 年。

| # | 用户行为 | 功能 | 代码路径 | 状态 |
|---|---------|------|---------|------|
| 1 | 看信号治理面板 | 治理面板卡片 | `src/cards/governance_cards.py` → quality_gate + risk_alerts + panel_review + publish_review 四卡 | ✅ |
| 2 | 质量门禁：证据链满足 | 门禁检查 | `src/governance/quality_gate.py` `run_quality_gate()`: 检查 no_evidence + missing_price_context | ✅ |
| 3 | 数据缺口：✅ 无缺失 | 缺口检测 | `src/governance/data_gaps.py` `collect_data_gaps()` + `has_blocking_gaps()` → 橙色 banner | ✅ |
| 4 | 风险扫描：⚠ PE=68 | 风险扫描 | `src/governance/risk_scan.py` `run_risk_scan()` → risk_alerts card 显示风险标签 | ✅ |
| 5 | 角色评审：6 看多 1 看空 1 中性 | 8 角色评审 | `src/governance/panel_review.py` `run_panel_review()` → 调用 `roles.py` 8 个 PersonaConfig | ✅ |
| 6 | 角色前置过滤（仓位→能力圈→规则） | 三层过滤 | `src/governance/roles.py` `apply_role_pre_filters(persona, ticker, sector, market)` → RolePreFilterResult | ✅ |
| 7 | 点「多空辩论」 | 多轮辩论 | `src/governance/debate.py` `run_debate()` → Round1(空怼多) → Round2(多反驳) → Round3(综合) | ✅ |
| 8 | 点「发布审核」→ 批准 | 发布门禁 | `src/governance/publish_gate.py` `run_publish_gate()` → 检查 blocking gaps + 撰写发布摘要 | ✅ |
| 9 | 认可缺口（如有）→ 继续发布 | 缺口确认 | `POST /api/governance/gaps/acknowledge` → `web_api.py` → `src/governance/gap_actions.py` → 重跑治理 | ✅ |
| 10 | 信号进入「共识标的」 | 共识卡片 | `src/cards/consensus.py` ConsensusCard → 多角色加权评分 → 共识标的列表 | ✅ |

**完成度：100%** | 代码覆盖：11 个文件，2 个端点

---

## 场景 4：资深投资者李建国 — 每日例行操盘

**人物**：45 岁，前私募基金经理。

| # | 用户行为 | 功能 | 代码路径 | 状态 |
|---|---------|------|---------|------|
| 1 | 看系统概览（采集 87 条/信号 15 条） | 状态卡片 | `src/cards/system_status.py` SystemStatusCard → 队列、资源、今日分析数 | ✅ |
| 2 | 看 DCA 守护进程状态 | 守护进程卡片 | `src/cards/interactive_cards.py` `DaemonCard` → PID、运行时长、最近心跳 | ✅ |
| 3 | 板块轮动卡片 | 轮动分析 | `src/cards/rotation.py` RotationCard → `data/rotation/*_rotation.json` Z-score 排序 | ✅ |
| 4 | 信息源网络图 | 交叉关联 | `src/cards/network.py` NetworkCard → 分析师间推文共同提及关系 | ✅ |
| 5 | 共识标的 | 共识卡片 | `src/cards/consensus.py` → 多角色加权 ("NVDA 3/5 分析师看好") | ✅ |
| 6 | 手机收到 Telegram："SMCI 新信号" | Telegram 推送 | `POST /api/alerts/check` → 遍历租户 → Telegram Bot sendMessage | ✅ |
| 7 | 点 Telegram 链接 → 手机打开 Dashboard | 响应式布局 | `base.html` `@media(max-width:768px)` → 侧边栏缩为 56px 图标 | ✅ |
| 8 | 看评审结果（5/8 看多）→ 决定加仓 | 评审面板 | `panel_review card` → 角色观点聚合 → 评分柱状图 | ✅ |

**完成度：100%** | 代码覆盖：8 个文件，1 个端点

---

## 场景 5：量化思维投资者张明 — 深度数据验证

**人物**：38 岁，量化研究员出身。

| # | 用户行为 | 功能 | 代码路径 | 状态 |
|---|---------|------|---------|------|
| 1 | 看「我的持仓」 | 持仓卡片 | `src/cards/interactive_cards.py` `PortfolioCard` → 配置持仓: NVDA 30%, AMD 20% | ✅ |
| 2 | 持仓诊断：信号评分 82/58/75/45 | 信号评分 | `src/governance/panel_review.py` → 多角色评分聚合 → 综合评分 | ✅ |
| 3 | 组合风控：AI 芯片集中度 65% | 风控提示 | PortfolioCard → 行业集中度计算 + 预警阈值 | ✅ |
| 4 | 看 DCF 估值专业工具 | 专业估值卡片 | `src/cards/valuation_card.py` `ValuationProCard` → 交互式 DCF 参数面板 | ✅ |
| 5 | AI 问答："AMD forward PE vs NVDA vs INTC" | RAG 检索 | `src/cards/chat_card.py` → `src/ai/chat_engine.py` `answer()` → `src/vectorization/retriever.py` → 向量检索 | ✅ |
| 6 | 看到引用推文原文 | 引用来源 | ChatEngine RAG response 包含 `引用推文: TJ_Research (4/15) "..."` | ✅ |
| 7 | 估值工具：dcf_skeleton("AMD") | DCF 估值 | `GET /api/valuation/dcf?ticker=AMD` → `src/data/valuation_tools.py` `dcf_skeleton()` → `_compute_dcf()` | ✅ |
| 8 | DCF 结果：$165/sh, 轻微高估 | 两段 DCF | `valuation_tools.py` `_compute_dcf()`: 5年投影 + Gordon Growth 终值 → Per-share value | ✅ |

**完成度：100%** | 代码覆盖：7 个文件，2 个端点

---

## 场景 6：板块轮动猎手赵龙 — 发现新机会

**人物**：30 岁，短线波段交易者。

| # | 用户行为 | 功能 | 代码路径 | 状态 |
|---|---------|------|---------|------|
| 1 | 看板块轮动：光模块 120% ↑ | 轮动卡片 | `src/cards/rotation.py` → Z-score 排序 → 新热点高亮 | ✅ |
| 2 | 点光模块 → 看推文列表 | 板块详情 | RotationCard 展开 → 按时间排列相关推文 | ✅ |
| 3 | 添加 COHR/LITE 到自选 | 股票 Watchlist | `POST /api/watchlist/add` → `web_api.py` → `PerUserConfig` watchlist 字段 → 加密存储 | ✅ |
| 4 | 设置 COHR 跌破 $55 预警 | 价格预警 | `POST /api/alerts/add` → `web_api.py` → `PerUserConfig` price_alerts 字段 | ✅ |
| 5 | 看价格预警卡片 | 预警列表 | `src/cards/financial_cards.py` `PriceAlertsCard` → 显示所有已设置预警 | ✅ |
| 6 | 撤销 COHR 预警 | 预警移除 | `POST /api/alerts/remove` → `web_api.py` → 从配置中删除 price_alerts 条目 | ✅ |
| 7 | 两天后 Telegram："COHR $54.80" | 预警推送 | `POST /api/alerts/check` → `src/data/financial.py` `get_price("COHR")` → below $55 → Telegram Bot | ✅ |

**完成度：100%** | 代码覆盖：5 个文件，4 个端点

---

## 场景 7：财报季密集使用的刘研究员

**人物**：33 岁，买方研究员，覆盖 15 只美股。

| # | 用户行为 | 功能 | 代码路径 | 状态 |
|---|---------|------|---------|------|
| 1 | 看财报日历：MU 6/20, NVDA 6/25 | 财报日历卡片 | `src/cards/financial_cards.py` `EarningsCalendarCard` → `FinancialData.get_earnings_calendar(watchlist)` | ✅ |
| 2 | 点 MU → 财报前预览 | 情景分析 | `GET /api/valuation/dcf?ticker=MU` → `valuation_tools.py` + `financial.py` → Bull/Base/Bear | ✅ |
| 3 | 看分析师分歧 | 角色分歧可视化 | `src/governance/panel_review.py` → 看多/看空角色分布 | ✅ |
| 4 | AI 问答："MU HBM 市场占有率" | RAG 深度检索 | `src/ai/chat_engine.py` → `retriever.py` → 推文 + 行业数据 | ✅ |
| 5 | 看分析师胜率排名 | 准确率卡片 | `src/cards/accuracy.py` `AccuracyCard` → 从 `data/accuracy/*_accuracy.json` 读取每位分析师历史胜率 | ✅ |
| 6 | 最终决定：MU 不建仓 | 手动决策 | 用户独立判断，系统不强制建议 | ✅ |

**完成度：100%** | 代码覆盖：6 个文件，1 个端点

---

## 场景 8：风险厌恶型投资者钱阿姨 — 极简使用

**人物**：52 岁，退休教师。

| # | 用户行为 | 功能 | 代码路径 | 状态 |
|---|---------|------|---------|------|
| 1 | 只看风险扫描 | 风险提示卡片 | `src/cards/governance_cards.py` `RiskAlertsCard` → 显示全部高风险标记 | ✅ |
| 2 | 只看质量门禁 | 门禁卡片 | `src/cards/governance_cards.py` `QualityGateCard` → pass/fail 清晰状态 | ✅ |
| 3 | 跳过有缺口的信号 | 数据缺口 banner | `src/governance/data_gaps.py` `has_blocking_gaps()` → 橙色/红色 banner | ✅ |
| 4 | 看分析师胜率：78% 看多准确率 | 胜率追踪 | `src/cards/accuracy.py` AccuracyCard → `data/accuracy/*_accuracy.json` | ✅ |
| 5 | 看异常检测 | 异常信号卡片 | `src/cards/anomaly.py` `AnomalyCard` → 偏离历史规律的异常信号列表 | ✅ |

**完成度：100%** | 代码覆盖：5 个文件

---

## 场景 9：多账号管理者周经理 — 团队协作

**人物**：40 岁，5 人投资小组组长。

| # | 用户行为 | 功能 | 代码路径 | 状态 |
|---|---------|------|---------|------|
| 1 | 进入管理后台 localhost:8001 | 独立管理站点 | `src/admin/app.py` → FastAPI on port 8001, docs_url=None | ✅ |
| 2 | 账号密码 + 验证码登录 | 管理后台认证 | `POST /login` → math captcha + SHA-256 password + session cookie | ✅ |
| 3 | 用户管理 → 看到 4 个组员 | 用户列表 | `GET /users` → `src/storage/auth_models.py` User query → 列表 + 启停按钮 | ✅ |
| 4 | 封禁管理 | 封禁/解封 | `GET /bans` → `src/admin/access_control.py` AccessControl → suspend/unsuspend | ✅ |
| 5 | 活动日志 → zhang_wei 采集 67 条 | 操作审计 | `src/admin/activity.py` ActivityTracker → 过去 24h 操作记录 | ✅ |
| 6 | 看系统监控面板 | 监控仪表盘 | `src/admin/app.py` `/dashboard` → 7天统计 + 操作趋势图 | ✅ |
| 7 | Dashboard 共享观察池 | 团队共享 | `GET /api/team/shared-pool` → `web_api.py` → `data/team_shared_pool.json` | ✅ |
| 8 | 更新共享观察池 | 团队同步 | `POST /api/team/shared-pool/update` → 管理员写入共享池 | ✅ |
| 9 | 导出信号质量报告 | 报告导出 | `GET /api/reports/signal-quality` → `web_api.py` → `src/governance/audit.py` GovernanceAuditor | ✅ |

**完成度：100%** | 代码覆盖：10 个文件，4 个端点

---

## 场景 10：深夜研究型投资者徐教授 — 极深研究

**人物**：48 岁，商学院教授。

| # | 用户行为 | 功能 | 代码路径 | 状态 |
|---|---------|------|---------|------|
| 1 | 跑 dcf_skeleton("SMCI") → $950 | DCF 自动估值 | `GET /api/valuation/dcf?ticker=SMCI` → `valuation_tools.py` `dcf_skeleton()` → `_compute_dcf()` | ✅ |
| 2 | 手动调 WACC: 10% → 8.5% | DCF 参数覆盖 | `GET /api/valuation/dcf?ticker=SMCI&wacc=8.5` → 用新 WACC 重算 → $1,120 | ✅ |
| 3 | 跑同行对标 | Comps | `valuation_tools.py` `comps_summary()` → `FinancialData.get_fundamentals(peers)` → PE/PB 分位数 | ✅ |
| 4 | 打开 DD 尽调清单（11 项） | 尽调清单 | `GET /api/valuation/dd?ticker=SMCI` → `valuation_tools.py` `generate_dd_checklist()` | ✅ |
| 5 | 看到"供应链单点依赖"标红 | 尽调风险标注 | `DDChecklistItem` 字段：status, evidence, notes | ✅ |
| 6 | 用专业估值卡片交互 | 交互式估值 | `src/cards/valuation_card.py` `ValuationProCard` → 参数调整滑块 + 实时估值 | ✅ |
| 7 | AI 问答："SMCI 液冷自研还是外购？" | RAG 检索 | `src/ai/chat_engine.py` answer() → `retriever` → 推文关键词匹配 | ✅ |
| 8 | 决定：SMCI 建仓不超过 10% | 手动决策 | 用户独立判断 | ✅ |

**完成度：100%** | 代码覆盖：5 个文件，3 个端点

---

## 场景 11：流水线管理者王工 — Pipeline 任务调度与监控

**人物**：36 岁，数据工程师，负责系统运维。

| # | 用户行为 | 功能 | 代码路径 | 状态 |
|---|---------|------|---------|------|
| 1 | 看 Pipeline 执行面板 | Pipeline 卡片 | `src/cards/pipeline_execute.py` `PipelineExecuteCard` → 任务类型、队列长度 | ✅ |
| 2 | 查看待办任务列表 | 任务列表 | `GET /pipeline/tasks` → `web_api.py` `list_tasks()` → 按类型/状态/分页筛选 | ✅ |
| 3 | 手动种子采集 | 种子扫描 | `POST /pipeline/tasks/seed` → `web_api.py` `seed_tasks()` → 扫描未处理推文 → 创建 filter/analyze/fetch_price/fetch_crypto/portrait 任务 | ✅ |
| 4 | 执行待办任务 | 后台执行 | `POST /pipeline/tasks/execute` → `web_api.py` `execute_selected()` → `task_executor.py` 后台线程互斥执行 | ✅ |
| 5 | 轮询执行进度 | 进度查看 | `src/pipeline/task_executor.py` `get_progress()` → 前端轮询显示当前进度百分比 | ✅ |
| 6 | 跳过分析失败的任务 | 跳过任务 | `POST /pipeline/tasks/{id}/skip` → `web_api.py` `skip_task()` → 标记 skip + 写入别名映射 | ✅ |
| 7 | 重试失败的 fetch_price 任务 | 重试任务 | `POST /pipeline/tasks/{id}/retry` → `web_api.py` `retry_task()` → 重置为 pending | ✅ |
| 8 | 编辑任务 ticker（手动纠错） | 编辑任务 | `POST /pipeline/tasks/{id}/edit` → `web_api.py` `edit_task()` → 改 ticker + 建别名映射 | ✅ |
| 9 | 运行数据清洗 | Clean 任务 | `POST /pipeline/clean` → `web_api.py` `run_clean()` → 用 stock_alias.csv 校准别名 | ✅ |
| 10 | 查看已获取的股价列表 | 价格数据 | `GET /pipeline/tasks/fetched` → `web_api.py` → 已有股价数据的 ticker 列表 | ✅ |

**完成度：100%** | 代码覆盖：4 个文件，7 个端点

---

## 场景 12：加密货币投资者林总 — 加密资产跟踪

**人物**：29 岁，Web3 从业者，主要交易 BTC/ETH 及山寨币。

| # | 用户行为 | 功能 | 代码路径 | 状态 |
|---|---------|------|---------|------|
| 1 | 看加密货币行情卡片 | 加密货币卡片 | `src/cards/functional_cards.py` `CryptoCard` → 列表显示 BTC/ETH/SOL 等价格、24h 涨跌 | ✅ |
| 2 | 添加观察地址/专题 | 配置观察 | `POST /api/config/observations/add` → 添加到用户配置 | ✅ |
| 3 | 启动加密货币价格采集 | Crypto Fetch | pipeline task `fetch_crypto` → `src/pipeline/task_executor.py` → Polygon.io X: 前缀 API | ✅ |
| 4 | 查看已采集的加密货币数据 | Crypto 列表 | `GET /pipeline/tasks/crypto_fetched` → 已有加密货币行情列表 | ✅ |
| 5 | 加密信号通过治理管线 | 完整治理 | 同场景 3 治理流程，但信号类型含 "crypto" | ✅ |
| 6 | 设置 BTC 跌破 $60K 预警 | 加密预警 | `POST /api/alerts/add` → ticker 为 "BTC" → 预警卡片显示 | ✅ |
| 7 | 看加密资产在持仓中的占比 | 持仓整合 | `PortfolioCard` → 加密资产与股票统一显示 | ✅ |

**完成度：100%** | 代码覆盖：4 个文件，3 个端点

---

## 场景 13：技术分析师刘工 — 网络关系与分析师画像

**人物**：34 岁，技术面为主的分析师。

| # | 用户行为 | 功能 | 代码路径 | 状态 |
|---|---------|------|---------|------|
| 1 | 看信息源网络关系图 | 网络卡片 | `src/cards/network.py` `NetworkCard` → 分析师间推文共同提及关系可视化 | ✅ |
| 2 | 点击节点 → 看该分析师所有推文 | 网络详情 | NetworkCard 展开 → 按时间展示该分析师推文 | ✅ |
| 3 | 看分析师投资风格画像 | 画像卡片 | `src/cards/tool_cards.py` `PortraitCard` → 从 `data/pipeline/*_portrait.md` 拉取 LLM 生成的投资风格画像 | ✅ |
| 4 | 手动触发分析师画像生成 | 画像生成 | `POST /cards/api_status/action` → `portrait_generate` → `src/cards/pipeline_execute.py` `PortraitGenerateCard` | ✅ |
| 5 | 看分析师历史准确率 | 准确率卡片 | `src/cards/accuracy.py` `AccuracyCard` → 30 天胜率统计 | ✅ |
| 6 | 选角色代理人 | 角色选择器 | `src/cards/interactive_cards.py` `RolePickerCard` → 选择角色作为虚拟分析师代理 | ✅ |

**完成度：100%** | 代码覆盖：5 个文件，1 个端点

---

## 场景 14：系统管理员陈工 — 管理后台与安全审计

**人物**：42 岁，IT 运维，负责系统安全管理。

| # | 用户行为 | 功能 | 代码路径 | 状态 |
|---|---------|------|---------|------|
| 1 | 登录管理后台 | 管理入口 | `src/admin/app.py` `POST /login` → math captcha 验证码 + SHA-256 密码哈希 + session cookie | ✅ |
| 2 | 看系统监控总览 | 监控面板 | `src/admin/app.py` `GET /dashboard` → 7 天活跃用户、操作统计、错误计数 | ✅ |
| 3 | 监控后台活动日志 | 活动审计 | `src/admin/activity.py` `ActivityTracker` → append-only JSONL → `GET /activity` 分页展示 | ✅ |
| 4 | 用户管理（新增/禁用） | 用户管理 | `GET /users` + `POST /suspend` + `POST /reactivate` → `src/admin/auth.py` + `access_control.py` | ✅ |
| 5 | 封禁管理 | 封禁操作 | `GET /bans` + 封禁/解封按钮 → `src/admin/access_control.py` `AccessControl` | ✅ |
| 6 | 看封禁历史 | 封禁日志 | 封禁操作写入 `src/admin/activity.py` → 列表展示 | ✅ |
| 7 | 看运维监控卡片 | 监控卡片 | `src/cards/admin_monitor_card.py` `AdminMonitorCard` → Dashboard 端的管理监控信息 | ✅ |
| 8 | 导出系统信号质量报告 | 质量报告 | `GET /api/reports/signal-quality?days=30` → `GovernanceAuditor` → JSON 汇总 | ✅ |

**完成度：100%** | 代码覆盖：5 个文件，6 个端点

---

## 场景 15：数据质量专员小赵 — 别名管理与数据清洗

**人物**：28 岁，数据分析师，负责数据质量。

| # | 用户行为 | 功能 | 代码路径 | 状态 |
|---|---------|------|---------|------|
| 1 | 看资产别名管理卡片 | 别名卡片 | `src/cards/functional_cards.py` `AssetAliasCard` → 显示 ticker → 别名映射表 | ✅ |
| 2 | 添加别名映射：AMD → Advanced Micro Devices | 别名添加 | AssetAliasCard 交互 → 写入 `data/stock_alias.csv` | ✅ |
| 3 | 确认别名统计 | 别名统计 | 别名卡片显示 confirmed/skipped/pending 计数 | ✅ |
| 4 | 运行数据清洗任务 | Pipeline Clean | `POST /pipeline/clean` → `task_executor.py` → 用 stock_alias.csv 校准已分析推文 | ✅ |
| 5 | 验证清洗后数据 | 清洗验证 | 通过 cards 查看清洗后信号中 ticker 是否已标准化 | ✅ |
| 6 | 编辑任务 ticker 纠错 | 任务编辑 | `POST /pipeline/tasks/{id}/edit` → 修改 ticker + 自动建别名映射 | ✅ |
| 7 | 跳过确认非投资推文 | 任务跳过 | `POST /pipeline/tasks/{id}/skip` → skip 计数 + 别名自动注入 | ✅ |

**完成度：100%** | 代码覆盖：3 个文件，3 个端点

---

## 场景 16：AI 对话深度用户方博士 — Chat 与 RAG 知识检索

**人物**：39 岁，AI 研究方向博士，用系统做实验。

| # | 用户行为 | 功能 | 代码路径 | 状态 |
|---|---------|------|---------|------|
| 1 | 打开 AI 对话卡片 | Chat 卡片 | `src/cards/chat_card.py` `ChatCard` → 对话界面 | ✅ |
| 2 | 提问："NVDA vs AMD 2026年谁更有潜力？" | LLM 问答 | `POST /cards/chat/action` → `chat_card.py` → `src/ai/chat_engine.py` `answer()` | ✅ |
| 3 | 追问："NVDA 最近推文情绪如何？" | 带上下文对话 | `chat_engine.py` 保留历史 → 多轮上下文 | ✅ |
| 4 | 问："帮我查 SMCI 液冷相关推文" | RAG 检索 | `chat_engine.py` → `src/vectorization/retriever.py` `TweetRetriever` → ChromaDB 向量检索 | ✅ |
| 5 | 看到检索结果含引用来源 | 引文标注 | RAG 响应含 `引用推文: @dearbaibabybus (2026-06-15)` | ✅ |
| 6 | 问："用 DD 清单分析 SMCI 风险" | 工具调用 | ChatEngine 调用 `generate_dd_checklist("SMCI")` → DD 清单返回 | ✅ |
| 7 | 对话被记录到活动日志 | 行为审计 | `chat_query` 操作 → `src/admin/activity.py` → append JSONL | ✅ |

**完成度：100%** | 代码覆盖：5 个文件，1 个端点

---

## 场景 17：安全合规审查 — 令牌管理与安全机制

**人物**：系统测试工程师，验证安全边界。

| # | 用户行为 | 功能 | 代码路径 | 状态 |
|---|---------|------|---------|------|
| 1 | 登录获取令牌 | Access + Refresh Token | `POST /auth/login` → JWT HS256 (30min) + Refresh Token (7d rotation) | ✅ |
| 2 | 30 分钟后访问 Dashboard | 令牌自动刷新 | `POST /auth/refresh` → Refresh Token 轮换 → 新 Access Token | ✅ |
| 3 | 验证旧 Refresh Token 已作废 | 防重放 | `src/admin/refresh_token.py` → `used == True` → reject reuse | ✅ |
| 4 | 登出 → 令牌失效 | 登出 | `POST /auth/logout` → 清除 cookie + 标记 Refresh Token used | ✅ |
| 5 | 登出后访问 Dashboard → 跳回首页 | 令牌校验 | `auth_me()` → 无有效 token → 401 → 前端跳转 `/?expired=1` | ✅ |
| 6 | 限制登录频率 | 限流保护 | `src/interfaces/web_api.py` `rate_limit_middleware` → 60s 滑动窗口 → 超 60 次返回 429 | ✅ |
| 7 | 限流豁免：静态资源 + 卡片请求 | 限流白名单 | rate_limit_middleware → path 匹配 `/cards/`, `/timeline/` 豁免 | ✅ |
| 8 | 查看当前用户信息 | 认证查询 | `GET /auth/me` → 返回 user.id, username, is_active | ✅ |

**完成度：100%** | 代码覆盖：4 个文件，5 个端点

---

## 场景 18：故障恢复 — 任务失败与重试机制

**人物**：运维值班工程师，应对 Pipeline 执行故障。

| # | 用户行为 | 功能 | 代码路径 | 状态 |
|---|---------|------|---------|------|
| 1 | API 超时 → analyze 任务失败 | 失败记录 | `task_executor.py` → `execute_analyze_task()` → 捕获异常 → status=failed + error_msg | ✅ |
| 2 | 自动重试（最多 3 次） | 内置重试 | `task_executor.py` → analyze 任务内建 `retry_count < 3` 循环 | ✅ |
| 3 | 3 次重试均失败 → 标记 failed | 最终失败 | `retry_count >= 3` → 标记 status=failed，不再重试 | ✅ |
| 4 | 前端看到失败任务 → 手动重试 | 人工介入 | 点「重试」→ `POST /pipeline/tasks/{id}/retry` → status 重置为 pending | ✅ |
| 5 | fetch_price 网络故障 → 自动重试 2 次 | Fetch 重试 | `task_executor.py` `_execute_fetch_price()` → `retry_count < 2` | ✅ |
| 6 | 并发执行锁 → 排队等待 | 互斥锁 | `_executor_lock` → `threading.Lock()` → 第二个执行请求进入等待队列 | ✅ |
| 7 | 锁释放 → 下一个任务执行 | 锁释放 | `finally: _executor_lock.release()` → 原子释放 | ✅ |

**完成度：100%** | 代码覆盖：1 个文件，1 个端点

---

## 场景 19：极端场景测试 — 限流、并发、非法请求

**人物**：安全测试工程师，压力测试系统健壮性。

| # | 用户行为 | 功能 | 代码路径 | 状态 |
|---|---------|------|---------|------|
| 1 | 同一 IP 60 秒内发起 61 次请求 | 触发限流 | `rate_limit_middleware` → 计数器超 60 → HTTP 429 | ✅ |
| 2 | 限流响应含 Retry-After | 限流反馈 | 429 响应含 `Retry-After` header + JSON body `{"ok":false,"error":"rate_limited"}` | ✅ |
| 3 | 卡片 API 不受限流影响 | 限流豁免 | `/cards/*` 路径不触发 rate limit bucket | ✅ |
| 4 | 静态 HTML 不受限流影响 | 静态豁免 | `/timeline/*`, landing page 路径不触发 rate limit | ✅ |
| 5 | 恶意路径遍历 → 404 | 路径校验 | `timeline/{path:path}` → 安全校验 `..` 路径 | ✅ |
| 6 | 无效 JWT token → 401 | 令牌校验 | `get_current_user()` → jose JWT decode 失败 → 401 | ✅ |
| 7 | 空 body POST → 422 | 参数校验 | FastAPI Pydantic 自动校验 → 422 错误详情 | ✅ |
| 8 | 管理后台暴力登录 → math captcha 阻挡 | 验证码防护 | `src/admin/app.py` → `POST /login` → 每次刷新验证码算式 | ✅ |

**完成度：100%** | 代码覆盖：3 个文件

---

## 场景 20：全链路 E2E 回归 — 从推文采集到发布信号

**人物**：质量保证工程师，执行完整回归测试。

| # | 用户行为 | 功能 | 代码路径 | 状态 |
|---|---------|------|---------|------|
| 1 | 注册新用户 + 配置 LLM + Twitter + Telegram | 完整配置 | 场景 1 + 场景 2 全步骤 | ✅ |
| 2 | 添加 3 位分析师到观察列表 | 观察配置 | `POST /api/config/observations/add` × 3 | ✅ |
| 3 | 启动种子扫描 | Seed | `POST /pipeline/tasks/seed` → 扫描新推文 | ✅ |
| 4 | 执行 6 种 pipeline 任务串行 | Pipeline | filter → analyze → fetch_price → fetch_crypto → portrait → clean | ✅ |
| 5 | 查看 28 张卡片全部渲染 | 全卡片渲染 | `GET /cards/meta` → 28 卡片元数据 → `GET /cards/{name}` 逐个验证 | ✅ |
| 6 | 信号通过治理管线 8 阶段 | 全治理流程 | DataGaps → QualityGate → PanelReview(8角色) → LLMReview → Debate(3轮) → RiskScan → PackageBuilder → PublishGate | ✅ |
| 7 | 缺口确认（如有）→ 继续发布 | 缺口管理 | `POST /api/governance/gaps/acknowledge` + `revoke` | ✅ |
| 8 | 共识信号 → 查看 Dashboard | 决策展示 | `ConsensusCard` + `rotation` + `network` + `accuracy` 等全部信号卡片 | ✅ |
| 9 | Telegram 收到信号推送 | 推送验证 | `POST /api/alerts/check` → 验证 Bot 调用 | ✅ |
| 10 | 管理员后台审计全部操作 | 审计验证 | `GET /activity` → 检查操作日志完整性（无 PII） | ✅ |
| 11 | 导出质量报告 | 报告验证 | `GET /api/reports/signal-quality?days=30` → 统计合理性检查 | ✅ |

**完成度：100%** | 代码覆盖：全覆盖 28 卡片 + 39 端点 + 8 阶段治理

---

## 附录 A：28 张卡片覆盖矩阵

| 卡片名称 | 显示名称 | 对应场景 |
|---------|---------|---------|
| `chat` | AI 问答 | 5, 7, 16 |
| `accuracy` | 分析师准确率 | 7, 8, 13 |
| `consensus` | 共识标的 | 3, 4 |
| `rotation` | 板块轮动 | 4, 6 |
| `anomaly` | 异常检测 | 8 |
| `network` | 信息源网络 | 4, 13 |
| `system_status` | 系统状态 | 4 |
| `daemon` | 守护进程 | 4 |
| `telegram` | Telegram 配置 | 2 |
| `role_picker` | 角色选择器 | 13 |
| `portfolio` | 我的持仓 | 5, 12 |
| `fetch_control` | 采集控制 | 2, 11 |
| `portrait` | 分析师画像 | 13 |
| `asset_alias` | 资产别名 | 15 |
| `crypto` | 加密货币 | 12 |
| `script_runner` | 脚本运行 | 11 |
| `timeline` | 观点时间线 | 2 |
| `pipeline_execute` | Pipeline 执行 | 11 |
| `portrait_generate` | 画像生成 | 13 |
| `quality_gate` | 质量门禁 | 3, 8 |
| `risk_alerts` | 风险扫描 | 3, 8 |
| `panel_review` | 角色评审 | 3, 4 |
| `publish_review` | 发布审核 | 3 |
| `config_center` | 用户配置中心 | 1, 2 |
| `earnings_calendar` | 财报日历 | 7 |
| `price_alerts` | 价格预警 | 6, 12 |
| `valuation_pro` | 专业估值 | 5, 10 |
| `admin_monitor` | 管理监控 | 14 |

## 附录 B：API 端点覆盖矩阵

| 端点 | 方法 | 场景 |
|------|------|------|
| `/` | GET | 1 |
| `/dashboard` | GET | 1, 2 |
| `/timeline/{path}` | GET | 2 |
| `/cards/meta` | GET | 1, 20 |
| `/cards/{name}` | GET | 1-20 |
| `/cards/{name}/action` | POST | 13, 16 |
| `/auth/register` | POST | 1 |
| `/auth/login` | POST | 2, 17 |
| `/auth/refresh` | POST | 17 |
| `/auth/logout` | POST | 17 |
| `/auth/me` | GET | 17 |
| `/api/config` | GET | 2 |
| `/api/config/llm` | POST | 2 |
| `/api/config/twitter` | POST | 2 |
| `/api/config/telegram` | POST | 2 |
| `/api/config/observations/add` | POST | 2, 12, 20 |
| `/api/config/observations/remove` | POST | 2 |
| `/pipeline/tasks` | GET | 11 |
| `/pipeline/tasks/execute` | POST | 11 |
| `/pipeline/tasks/{id}/skip` | POST | 11, 15 |
| `/pipeline/tasks/{id}/retry` | POST | 11, 18 |
| `/pipeline/tasks/{id}/edit` | POST | 11, 15 |
| `/pipeline/tasks/fetched` | GET | 11 |
| `/pipeline/tasks/crypto_fetched` | GET | 12 |
| `/pipeline/tasks/seed` | POST | 11, 20 |
| `/pipeline/clean` | POST | 11, 15 |
| `/api/governance/gaps/acknowledge` | POST | 3, 20 |
| `/api/governance/gaps/revoke` | POST | 3, 20 |
| `/api/valuation/dcf` | GET | 5, 7, 10 |
| `/api/valuation/dd` | GET | 10 |
| `/api/watchlist` | GET | 6 |
| `/api/watchlist/add` | POST | 6 |
| `/api/watchlist/remove` | POST | 6 |
| `/api/alerts/add` | POST | 6, 12 |
| `/api/alerts/remove` | POST | 6 |
| `/api/alerts/check` | POST | 4, 6, 20 |
| `/api/team/shared-pool` | GET | 9 |
| `/api/team/shared-pool/update` | POST | 9 |
| `/api/reports/signal-quality` | GET | 9, 14, 20 |

## 附录 C：8 阶段治理管线

```
DataGaps → QualityGate → PanelReview(8角色) 
         → LLMReview → Debate(3轮) 
         → RiskScan → PackageBuilder → PublishGate
```

| 阶段 | 模块 | 场景 |
|------|------|------|
| 1. DataGaps | `src/governance/data_gaps.py` | 3, 8 |
| 2. QualityGate | `src/governance/quality_gate.py` | 3, 8 |
| 3. PanelReview | `src/governance/panel_review.py` | 3, 4, 5 |
| 4. LLMReview | `src/governance/llm_review.py` | 3 |
| 5. Debate | `src/governance/debate.py` | 3 |
| 6. RiskScan | `src/governance/risk_scan.py` | 3, 8 |
| 7. PackageBuilder | `src/governance/package_builder.py` | 3 |
| 8. PublishGate | `src/governance/publish_gate.py` | 3, 20 |

## 附录 D：Pipeline 6 种任务

```
filter ──► analyze ──► portrait ──► clean
               │
               ├──► fetch_price（股票 K 线）
               └──► fetch_crypto（加密货币行情）
```

| 任务类型 | 模块 | 场景 |
|---------|------|------|
| filter | `task_executor.py` LLM 过滤 | 11, 20 |
| analyze | `task_executor.py` 深度分析 | 11, 18, 20 |
| fetch_price | `task_executor.py` 股价 | 11, 18 |
| fetch_crypto | `task_executor.py` 加密行情 | 12 |
| portrait | `task_executor.py` 用户画像 | 13 |
| clean | `task_executor.py` 别名清洗 | 11, 15 |

---

> 文档更新日期：2026-06-17 | 版本：2.0（从 10 场景扩充到 20 场景）
> 新场景：11-Pipeline 管理 / 12-加密货币 / 13-网络画像 / 14-管理后台 / 15-别名清洗 /
> 16-Chat+RAG / 17-令牌安全 / 18-故障恢复 / 19-极端场景 / 20-全链路回归
