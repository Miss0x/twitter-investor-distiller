# 10 场景功能覆盖差距分析

> 审计日期：2026-06-13 | 来源：代码逐文件检查

---

## 逐场景拆解

### 场景 1：小白林悦 — 注册探索

| 需要的功能 | 代码状态 | 文件 |
|-----------|---------|------|
| 产品首页（功能展示） | ✅ 已实现 | `landing.html` full hero + features + pricing |
| 注册 Modal | ✅ 已实现 | `landing.html` 内联 JS |
| 自动登录跳转 Dashboard | ✅ 已实现 | `web_api.py` `/auth/register` → `/auth/login` → redirect |
| Dashboard 骨架屏 | ✅ 已实现 | `base.html` 三态渲染（加载/无数据/错误） |
| 用户配置中心（空状态引导） | ⚠️ 部分 | 卡片显示空白 LLM 配置模板，但无引导文字"请先配置 LLM" |

**场景 1 完成度：95%**

---

### 场景 2：入门陈志远 — 第一次配置

| 需要的功能 | 代码状态 | 文件 |
|-----------|---------|------|
| 配置 LLM 模型（加密存储） | ✅ 已实现 | `api/config/llm` → `PerUserConfig` → Fernet 加密 |
| 配置 Twitter API | ✅ 已实现 | `api/config/twitter` → 加密存储 |
| 添加观察对象 | ✅ 已实现 | `api/config/observations/add` |
| 保存后立即生效（热加载） | ✅ 已实现 | `PerUserConfig.apply_llm_config()` + `ChatEngine.reload_config()` |
| 一键采集推文 | ✅ 已实现 | Pipeline control card + daemon worker |
| 信号卡片显示 | ✅ 已实现 | 信号卡片组 |
| 观点时间线 | ⚠️ 部分 | `cards/timeline.html` 存在，但数据来源为预计算的 JSON |

**场景 2 完成度：90%**

---

### 场景 3：中级王思琪 — 信号治理

| 需要的功能 | 代码状态 | 文件 |
|-----------|---------|------|
| 信号治理面板（质量门禁） | ✅ 已实现 | `quality_gate.py` + `governance_cards.py` |
| 风险扫描 | ✅ 已实现 | `risk_scan.py` + risk_alerts card |
| 8 角色评审 | ✅ 已实现 | `panel_review.py` + `roles.py` |
| 角色前置过滤 | ✅ 已实现 | `roles.py` `apply_role_pre_filters()` |
| 多空辩论 | ❌ **单轮** | `debate.py` 只做单轮合成，不是真正的多轮互喷 |
| 发布审核 | ✅ 已实现 | `publish_gate.py` + publish_review card |
| 共识标的卡片 | ✅ 已实现 | `consensus.py` |

**场景 3 完成度：85%** — **多空辩论需要升级为真正的多轮**

---

### 场景 4：操盘手李建国 — 每日日常

| 需要的功能 | 代码状态 | 文件 |
|-----------|---------|------|
| 系统概览（今日采集数/信号数） | ✅ 已实现 | system_status card |
| 板块轮动 | ✅ 已实现 | `rotation.py` RotationCard |
| 信息源关系网络 | ✅ 已实现 | `network.py` NetworkCard |
| 共识标的 | ✅ 已实现 | `consensus.py` |
| Telegram 实时推送 | ⚠️ 部分 | Bot 存在但不支持主动推送信号 |
| 移动端响应式 | ✅ 已实现 | `base.html` @media 768px |

**场景 4 完成度：85%** — **Telegram 推送需要主动推送能力**

---

### 场景 5：量化张明 — 深度验证

| 需要的功能 | 代码状态 | 文件 |
|-----------|---------|------|
| 持仓诊断 | ✅ 已实现 | PortfolioCard `interactive_cards.py` |
| AI 问答（RAG + 引用） | ✅ 已实现 | `chat_engine.py` + `chat_card.py` |
| DCF 估值工具 | ⚠️ 部分 | `valuation_tools.py` 有骨架，**但不可手动调 WACC** |
| Comps 同行对标 | ✅ 已实现 | `valuation_tools.py` comps_summary |
| 估值工具卡片（Dashboard UI） | ❌ **缺失** | 无 valuation_pro 卡片 |

**场景 5 完成度：60%** — **DCF 不能调参、估值无 Dashboard 卡片**

---

### 场景 6：轮动猎手赵龙 — 发现新机会

| 需要的功能 | 代码状态 | 文件 |
|-----------|---------|------|
| 板块轮动热力图 | ✅ 已实现 | `rotation.py` |
| 新板块发现 | ✅ 已实现 | 轮动卡片的 Z-score 排序 |
| 自选股 watchlist（不同于观察列表） | ❌ **缺失** | 只有 Twitter 观察列表，没有股票 watchlist |
| 价格预警 | ❌ **缺失** | 无 price alert 功能 |
| Telegram 价格触发通知 | ❌ **缺失** | 同上 |

**场景 6 完成度：45%** — **watchlist + price alert 完全缺失**

---

### 场景 7：财报季刘研究员

| 需要的功能 | 代码状态 | 文件 |
|-----------|---------|------|
| 财报日历数据 | ✅ 已实现 | `financial.py` `get_earnings_calendar()` |
| 财报日历 Dashboard 卡片 | ❌ **缺失** | 数据可用但无 UI 卡片 |
| 财报前预览（三情景） | ❌ **缺失** | 无 earnings_preview 功能 |
| 分析师评级数据 | ✅ 已实现 | `financial.py` `get_analyst_ratings()` |
| 分析师分歧可视化 | ❌ **缺失** | 无分歧度指标 |
| AI 问答深度研究 | ✅ 已实现 | chat_engine RAG |

**场景 7 完成度：40%** — **财报卡片 + 情景分析 + 分歧指标均缺失**

---

### 场景 8：风险厌恶钱阿姨 — 极简

| 需要的功能 | 代码状态 | 文件 |
|-----------|---------|------|
| 风险扫描卡片 | ✅ 已实现 | risk_alerts card |
| 质量门禁可视化 | ✅ 已实现 | quality_gate card |
| 数据缺口橙色 banner | ✅ 已实现 | governance_cards gap display |
| 分析师历史胜率卡片 | ⚠️ 部分 | `accuracy.py` 存在但依赖预计算 JSON，非实时计算 |
| 极简浏览路径 | ✅ 已实现 | 侧边栏导航可直达信号/决策 |

**场景 8 完成度：90%** — **胜率追踪需要实时化**

---

### 场景 9：团队周经理 — 管理

| 需要的功能 | 代码状态 | 文件 |
|-----------|---------|------|
| 管理后台（独立站点） | ✅ 已实现 | `admin/app.py` port 8001 |
| 用户管理（启停） | ✅ 已实现 | `/admin/users` API + UI |
| 活动日志（操作审计） | ✅ 已实现 | `activity.py` + 管理后台页面 |
| 封禁管理 | ✅ 已实现 | `access_control.py` + bans page |
| 团队观察池共享 | ❌ **缺失** | 租户间无数据共享 |
| 信号质量报告导出 | ❌ **缺失** | 无 PDF/CSV 导出 |

**场景 9 完成度：75%** — **团队共享 + 报告导出缺失**

---

### 场景 10：徐教授 — 极深研究

| 需要的功能 | 代码状态 | 文件 |
|-----------|---------|------|
| DCF 估值 | ⚠️ 部分 | 骨架可用，**WACC 不可调** |
| Comps 同行对标 | ✅ 已实现 | `valuation_tools.py` |
| DD 尽调清单 | ✅ 已实现 | `valuation_tools.py` `generate_dd_checklist()` |
| AI 深度问答 | ✅ 已实现 | RAG + chat_engine |
| DCF 手动调参（WACC/增长率） | ❌ **缺失** | 无 recalculate 方法 |
| 估值工具 Dashboard 卡片 | ❌ **缺失** | 无 UI 暴露 |
| 尽调结果手动标注 | ❌ **缺失** | 生成的 DD 清单不可交互标注 |

**场景 10 完成度：55%** — **核心分析引擎存在但 UI + 交互全缺**

---

## 汇总

| 场景 | 完成度 | 最关键的缺失 |
|------|--------|------------|
| 1 小白探索 | 95% | 引导文字 |
| 2 入门配置 | 90% | 基本完整 |
| 3 信号治理 | 85% | **多空辩论需升级为多轮** |
| 4 每日操盘 | 85% | Telegram 主动推送 |
| 5 量化验证 | 60% | **DCF调参 + 估值卡片** |
| 6 板块轮动 | 45% | **watchlist + 价格预警** |
| 7 财报季 | 40% | **财报卡片 + 情景分析** |
| 8 风险厌恶 | 90% | 胜率实时化 |
| 9 团队管理 | 75% | 团队共享 |
| 10 极深研究 | 55% | **DCF调参 + 估值UI + 标注交互** |

**全局平均完成度：73%**

---

## 优先级排序（按影响最大 → 最小）

| 优先级 | 功能 | 场景覆盖 | 工作量 |
|--------|------|---------|--------|
| P0 | DCF 手动调参（WACC/增长率可调） | 5, 10 | 1h |
| P0 | 估值工具 Dashboard 卡片 | 5, 10 | 2h |
| P1 | 多空辩论升级为真多轮 | 3, 7 | 3h |
| P1 | 财报日历卡片 + 情景分析 | 7 | 2h |
| P1 | 股票 watchlist（独立于观察列表） | 6, 7 | 2h |
| P2 | 价格预警系统 | 4, 6 | 4h |
| P2 | Telegram 主动推送 | 4, 6 | 3h |
| P2 | 团队共享观察池 | 9 | 3h |
| P3 | 尽调清单交互标注 | 10 | 2h |
| P3 | 分析师胜率实时化 | 8 | 1h |
