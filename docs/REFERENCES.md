# 技术参考资料库

> 创建于 2026-05-25，持续更新。每个方向标注可触达性、借鉴价值。

---

## 一、论文

| 方向 | 标题 | 年份 | 获取 | 许可 | 洞见 |
|------|------|------|------|------|------|
| #1,#2,#4 | *The Price Impact of Tweets: A High‑Frequency Study* | Yang et al. 2025 | [AUT Repository PDF](https://openrepository.aut.ac.nz/items/c6a72635-7de4-4270-887f-a842b111f198) | CC BY‑NC | 推文情绪对股价日内级影响；多信号源聚合 > 单一信号源；错误定价需数日修正 |
| #7,#13 | *LLM‑based Personalized Portfolio Recommender* | Li & Gu 2025 | [arXiv PDF](https://arxiv.org/pdf/2512.12922v1) | 公开预印本 | LLM+RL 融合做个性化投资组合推荐，直接对应角色代入选股 |
| #8,#10 | *NLP in Finance: A Survey* | O'Sullivan et al. 2025 | [sentic.net PDF](https://sentic.net/nlp-in-finance.pdf) | 作者托管 | 10 大 NLP 金融应用，含板块轮动、异常检测、情绪分析 |

---

## 二、量化回测框架（多源对比）

| 框架 | 类型 | 定位 | GitHub | 适合我们 |
|------|------|------|--------|---------|
| **backtesting.py** | 事件驱动 | 最轻、最快上手，交互式图表 | [kernc/backtesting.py](https://github.com/kernc/backtesting.py) | ⭐⭐⭐ 方向 #2 MVP 首选 |
| **vectorbt** | 向量化 | 最快回测，支持万级参数扫描 | [polakowo/vectorbt](https://github.com/polakowo/vectorbt) | ⭐⭐ 参数优化 |
| **Zipline-Reloaded** | 事件驱动 | 最真实市场模拟，防前视偏差 | [stefan-jansen/zipline-reloaded](https://github.com/stefan-jansen/zipline-reloaded) | ⭐⭐ 准确度优先时 |
| **bt** | 组合树 | 多资产组合天然适配 | [pmorissette/bt](https://github.com/pmorissette/bt) | ⭐⭐ 方向 #13 多持仓 |
| **LEAN (QuantConnect)** | 生产级 | 全品类、实盘接口 | [QuantConnect/Lean](https://github.com/QuantConnect/Lean) | ⭐ 太重，远期 |
| **nautilus_trader** | 高性能 | Rust/Cython，纳秒级 | [nautechsystems/nautilus_trader](https://github.com/nautechsystems/nautilus_trader) | ⭐ 过于专业 |
| **Backtrader** | 事件驱动 | 曾经的王者，已停止维护 | [mementum/backtrader](https://github.com/mementum/backtrader) | ❌ 不推荐新项目 |
| **FinRL** | 强化学习 | 金融 RL 框架，15.2k ★ | [AI4Finance-Foundation/FinRL](https://github.com/AI4Finance-Foundation/FinRL) | ⭐⭐⭐ 方向 #1 远期升级 |
| **eventstudy** | 专用 | 金融事件研究专用包 | [PyPI eventstudy](https://pypi.org/project/eventstudy/) | ⭐⭐⭐ 方向 #2 精确对标 |

**建议策略**：方向 #2 用 `backtesting.py` 做 MVP → `vectorbt` 做参数优化 → `Zipline` 做最终验证。

---

## 三、13 方向逐一参考项目

### #1 信号量化
| 项目 | 描述 | 借鉴点 |
|------|------|--------|
| [FinRL](https://github.com/AI4Finance-Foundation/FinRL) | 金融 RL，信号→交易动作 | 多因子信号融合方法、奖励函数设计 |
| [vectorbt](https://github.com/polakowo/vectorbt) | 向量化回测，支持自定义信号 | 信号→收益的向量化计算、参数扫描 |
| Yang 2025 论文 | 推文情绪强度量化 | stance × confidence 的数值化方法 |

### #2 准确率回溯
| 项目 | 描述 | 借鉴点 |
|------|------|--------|
| [backtesting.py](https://github.com/kernc/backtesting.py) | 最轻量回测 | 事件驱动回测流程、Stats 输出 |
| [eventstudy](https://pypi.org/project/eventstudy/) | 专用事件研究 | CAAR 计算、显著性检验 |
| [PakHsi0317/...](https://github.com/PakHsi0317/Social-Media-Stock-Sentiment-Trading-Backtesting-System) | 推文→回测全流程 | 推文信号到交易执行的映射 |
| [Zipline-Reloaded](https://github.com/stefan-jansen/zipline-reloaded) | 真实市场模拟 | Pipeline API、防前视偏差机制 |

### #3 实时触发
| 项目 | 描述 | 借鉴点 |
|------|------|--------|
| [Fintwit.ai](https://fintwit.ai) | 实时监控 500+ 分析师 | 事件驱动架构、信号推送逻辑 |
| FastAPI BackgroundTasks | 原生异步任务 | web_api.py 已有，加 scheduler |

### #4 多信号联动
| 项目 | 描述 | 借鉴点 |
|------|------|--------|
| Yang 2025 论文 | 多源聚合优于单源 | 信号加权平均方法、信源可靠性衰减 |
| [Stocktwits](https://stocktwits.com) | 散户情绪聚合 | 聚合 API 设计、信号热力图 |

### #5 预警系统（→ #10 子集）
| 项目 | 描述 | 借鉴点 |
|------|------|--------|
| [TradingView Alerts](https://www.tradingview.com) | 多条件预警 | 条件触发器设计范式 |
| [FinRL](https://github.com/AI4Finance-Foundation/FinRL) | 交易动作触发 | 阈值调优方法 |

### #6 输出面板
| 项目 | 描述 | 借鉴点 |
|------|------|--------|
| [TradingAgents-CN](https://github.com/hsliuping/TradingAgents-CN) | Vue3 + FastAPI 面板 | 报告导出、可视化布局 |
| [Fintwit.ai](https://fintwit.ai) | 信号仪表盘 | 四级下钻设计模式 |
| Streamlit | 已有控制台 | 快速 MVP，长期换 Vue |

### #7 角色代入选股
| 项目 | 描述 | 借鉴点 |
|------|------|--------|
| [TradingAgents-CN](https://github.com/hsliuping/TradingAgents-CN) | 多智能体交易框架 | LLM 角色分工、辩论机制 |
| [L‑PPR 论文](https://arxiv.org/pdf/2512.12922v1) | LLM 个性化组合推荐 | system prompt 设计、RL 细调 |
| [FinRL](https://github.com/AI4Finance-Foundation/FinRL) | 策略训练 | 从画像→交易策略的参数化 |

### #8 板块轮动检测
| 项目 | 描述 | 借鉴点 |
|------|------|--------|
| [pyfolio](https://github.com/quantopian/pyfolio) | 持仓板块分析 | 板块暴露 tear sheet |
| O'Sullivan 2025 综述 | NLP 板块轮动 | 文本→板块映射方法 |

### #9 情绪时间线
| 项目 | 描述 | 借鉴点 |
|------|------|--------|
| [Finfluencer.Social](https://finfluencer.social) | K 线叠加情绪信号 | 双轴图设计 |
| D3.js / ECharts | 交互时间线 | 可视化实现 |

### #10 异常检测
| 项目 | 描述 | 借鉴点 |
|------|------|--------|
| [finBERT](https://github.com/ProsusAI/finBERT) | 金融 NLP 预训练 | embedding → 向量距离检测 |
| [PyOD](https://github.com/yzhao062/pyod) | 通用异常检测库 | 60+ 检测器，含文本异常 |
| O'Sullivan 2025 综述 | NLP 异常检测 | KL 散度、滑动窗口方法 |

### #11 基本面快照
| 项目 | 描述 | 借鉴点 |
|------|------|--------|
| Polygon.io Financials API | 财报端点 | `vX/reference/financials/{ticker}` |
| [yfinance](https://github.com/ranaroussi/yfinance) | 免费无限制 | 备选数据源 |
| [FundamentalAnalysis](https://github.com/JerBouma/FundamentalAnalysis) | 基本面数据聚合 | PE/ROE/增速统一接口 |

### #12 投资者关联网络
| 项目 | 描述 | 借鉴点 |
|------|------|--------|
| [networkx](https://github.com/networkx/networkx) | 图分析标准库 | 中心性、社区检测 |
| [pyvis](https://github.com/WestHealth/pyvis) | 交互图可视化 | 网络图渲染 |
| Twitter API v2 | 关注/互动关系 | 扩充网络数据源 |

### #13 持仓叠加
| 项目 | 描述 | 借鉴点 |
|------|------|--------|
| [bt](https://github.com/pmorissette/bt) | 组合回测 | 多资产仓位管理 |
| [L‑PPR 论文](https://arxiv.org/pdf/2512.12922v1) | 个性化推荐 | 用户画像→持仓映射 |
| [pyfolio](https://github.com/quantopian/pyfolio) | 持仓分析 | 风险敞口、归因分析 |

---

## 四、量化框架多源对比结论

| 维度 | 推荐 | 理由 |
|------|------|------|
| 方向 #2 MVP | **backtesting.py** | 最轻、最快出结果、交互图表 |
| 信号参数优化 | **vectorbt** | 万级参数扫描秒完成 |
| 准确度验证 | **Zipline-Reloaded** | 防前视偏差、真实市场模拟 |
| 组合级（#13） | **bt** | 多资产组合树天然适配 |
| 远期 RL 升级 | **FinRL** | 学术界最活跃的金融 RL 框架 |
| 事件研究专用 | **eventstudy** | CAAR/显著性开箱即用 |

---

*最后更新：2026-05-25*
