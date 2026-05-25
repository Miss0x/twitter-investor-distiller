# 工程开发规范文档

> 版本 1.0 · 2026-05-25 · 13 模块完整技术规格

---

## 文档约定

| 标记 | 含义 |
|------|------|
| `#N` | 模块编号，对应 13 方向 |
| **P0** | 阻塞性依赖——前置模块未完成则本模块无法启动 |
| **P1** | 数据依赖——需要前置模块产出作输入 |
| **P2** | 独立模块——无硬依赖 |
| `src/` | 代码落于 `src/pipeline/` 下 |
| `scripts/` | 独立脚本，不依赖 FastAPI/Streamlit |
| `data/` | 数据文件，JSON 格式 |

---

## 模块 #2：准确率回溯 ⭐ P2

**定位**：Phase 1 核心——验证分析师可信度的量化基础

### 技术规格

| 项目 | 规格 |
|------|------|
| 输入 | `data/pipeline/*_analyzed_cleaned.json` + `data/prices.json` |
| 输出 | `data/accuracy/{username}_accuracy.json` |
| 核心方法 | Event Study（事件研究法） |
| 外部依赖 | `backtesting` (PyPI) |
| 代码位置 | `scripts/backtest_accuracy.py` |
| 代码量 | 约 350 行 |

### 算法流程

```
1. 加载所有 analyzed_cleaned 数据
2. 筛选 action_hint ∈ {买入, 加仓, 卖出, 减仓} 的推文
3. 对每条推文：
   a. 提取 created_at → entry_date
   b. 提取 mentioned_stocks（清洗后）
   c. 对每只股票：
      - 从 prices.json 取 entry_date 收盘价 → entry_price
      - 取 t+7 收盘价 → price_7d
      - 取 t+30 收盘价 → price_30d
      - 取同期 SPY 基准价格 → spy_price
      - excess_7d = (price_7d - entry_price) / entry_price - spy_7d_return
      - excess_30d = 同上
4. 按分析师汇总：
   - 胜率（excess > 0 的次数 / 总信号数）
   - 平均超额收益
   - 夏普比率
   - 最大回撤
   - 按月/按股票分组
5. 输出 JSON
```

### 输出 Schema

```json
{
  "username": "TJ_Research",
  "total_signals": 45,
  "win_rate_7d": 0.62,
  "win_rate_30d": 0.71,
  "avg_excess_7d_pct": 2.3,
  "avg_excess_30d_pct": 5.8,
  "sharpe_30d": 1.4,
  "max_drawdown_30d": -12.5,
  "by_stock": {
    "NVDA": { "signals": 8, "win_rate_30d": 0.88, "avg_excess_30d": 12.3 },
    "...": {}
  },
  "by_month": {
    "2025-03": { "signals": 3, "win_rate_30d": 0.67 },
    "...": {}
  }
}
```

### 开发检查点

- [x] 1. 安装 backtesting.py，验证可用
- [ ] 2. 编写 `extract_signals()` — 从 analyzed_cleaned 提取可回测信号
- [ ] 3. 编写 `match_prices()` — 信号日期 → 股价匹配
- [ ] 4. 编写 `compute_returns()` — t+7/t+30 超额收益
- [ ] 5. 编写 `aggregate_stats()` — 胜率/夏普/回撤
- [ ] 6. TJ_Research 跑通，人工验证 3 条信号逻辑正确
- [ ] 7. dearbaibabybus 跑通
- [ ] 8. 输出 JSON + Streamlit 面板集成

### 测试标准

- 手动抽查 5 条信号：推文日期 + 股票 + entry_price 是否正确
- SPY 基准收益计算与 Yahoo Finance 交叉验证
- 空信号（无人给出过买入建议）不报错

---

## 模块 #11：基本面快照 ⭐ P2

**定位**：Phase 1 辅助——为 #7 和 #13 提供估值锚点

### 技术规格

| 项目 | 规格 |
|------|------|
| 输入 | `data/stock_alias.csv` + analyzed_cleaned 的 verified stocks |
| 输出 | `data/fundamental_cache.json` |
| 核心方法 | Polygon Financials API |
| 外部依赖 | Polygon.io 免费额度（5 req/min） |
| 代码位置 | `scripts/fetch_fundamentals.py` |
| 代码量 | 约 120 行 |

### 算法流程

```
1. 从 analyzed_cleaned 提取所有 verified ticker
2. 去除已有 fundamental_cache 的
3. 对每个 ticker：
   GET /vX/reference/financials/{ticker}?limit=4&apiKey=...
   提取：
     - pe_ratio (trailing)
     - roe (return_on_equity)
     - revenue_growth_yoy
     - debt_to_equity
     - market_cap
     - sector
4. 每 5 次请求等待 60 秒（免费额度 5/min）
5. 写入 fundamental_cache.json
```

### 输出 Schema

```json
{
  "NVDA": {
    "pe_ratio": 38.2,
    "roe": 0.45,
    "revenue_growth_yoy": 0.65,
    "debt_to_equity": 0.12,
    "market_cap": 2800000000000,
    "sector": "Technology",
    "fetched_at": "2026-05-25"
  }
}
```

### 开发检查点

- [ ] 1. 验证 Polygon `/vX/reference/financials/{ticker}` 端点返回字段
- [ ] 2. 编写提取和缓存逻辑
- [ ] 3. 速率控制：`time.sleep(12)` 每请求
- [ ] 4. 跑通全部已验证股票

### 测试标准

- 对比 Yahoo Finance 同只股票的 PE/ROE，偏差 < 10%
- 缓存命中时不再调 API

---

## 模块 #1：信号量化 ⭐ P1（依赖 #2）

**定位**：Phase 2 核心——把 LLM 文本输出变成可比较的数字

### 技术规格

| 项目 | 规格 |
|------|------|
| 输入 | `*_analyzed_cleaned.json` + `prices.json` + `accuracy/*.json` |
| 输出 | 每条推文追加 `signal_score`（0-100） |
| 核心方法 | 多因子加权融合 + 贝叶斯置信度校准 |
| 外部依赖 | 无（纯 Python 计算） |
| 代码位置 | `scripts/compute_signals.py` |
| 代码量 | 约 250 行 |

### 算法流程

```
对每条 analyzed 推文：

1. Stance 数值化：
   看多 → +1.0, 加仓 → +0.8, 持有 → +0.3,
   观望 → 0.0, 减仓 → -0.8, 卖出 → -1.0

2. Confidence 贝叶斯校准：
   raw_confidence = {high: 1.0, medium: 0.5, low: 0.0}
   posterior = raw_confidence × analyzer_win_rate_30d（来自 #2）
   calibrated = posterior * 100

3. K 线共振因子（仅当推文提到具体股票）：
   close = 推文日期收盘价
   sma20 = 前 20 日均价
   momentum_z = (close - sma20) / std(close, 20)
   resonance = clamp(momentum_z, -2, 2) × 0.15

4. 信号分：
   signal = 0.40 × stance_score × 100
          + 0.35 × calibrated
          + 0.15 × resonance × 100
          + 0.10 × (has_multiple_stocks? 0.7 : 0.3)

5. 写入 analyzed_cleaned 的 signal_score 字段
```

### 输出 Schema

```json
// 追加入原有 analyzed_cleaned 条目
{
  "...existing_fields...": "...",
  "signal_score": 78,
  "signal_components": {
    "stance_raw": 80,
    "confidence_calibrated": 71,
    "momentum_z": 1.2,
    "resonance_bonus": 18
  }
}
```

### 开发检查点

- [ ] 1. 编写 stance 数值化映射
- [ ] 2. 贝叶斯校准：加载 #2 的准确率数据做先验
- [ ] 3. K 线共振因子：SMA20 + Z-score
- [ ] 4. 四因子加权融合
- [ ] 5. 对 TJ_Research 全量跑一遍，人工抽查 10 条信号分合理性
- [ ] 6. 确认 signal_score 范围在 0-100

### 测试标准

- 极端信号分验证：明确提出"加仓" + confidence=high + K 线底部 → 应接近 90+
- 无态度推文 → signal_score = 0
- 无股票推文 → resonance 因子权重降为 0，其他因子重新归一化

---

## 模块 #4：多信号联动 ⭐ P1（依赖 #1）

**定位**：Phase 2 辅助——多分析师交叉验证

### 技术规格

| 项目 | 规格 |
|------|------|
| 输入 | #1 输出的 signal_score + 对应推文日期/股票 |
| 输出 | `data/consensus/{ticker}_consensus.json` |
| 核心方法 | 加权平均 + 同向 bonus |
| 外部依赖 | 无 |
| 代码位置 | `scripts/compute_consensus.py` |
| 代码量 | 约 80 行 |

### 算法流程

```
对每只股票，时间窗口 = 7 天：

1. 收集窗口内所有分析师对该股的 signal_score
2. 每人权重 = 该人 30 日胜率（来自 #2）
3. consensus = Σ(w × signal) / Σ(w)
4. 同向 bonus：若所有人同向 → consensus × 1.2
5. 输出
```

### 开发检查点

- [ ] 1. 实现 7 天窗口滑动聚合
- [ ] 2. 加权平均 + 同向 bonus
- [ ] 3. 对现有二维分析师数据全量跑一遍
- [ ] 4. 标注哪些股票只有单人覆盖

### 测试标准

- 双人覆盖的股票联动分应高于单人
- 反向信号（一个看多一个看空） → consensus 应趋于中性

---

## 模块 #8：板块轮动检测 ⭐ P2

**定位**：Phase 3——追踪分析师关注焦点的迁移

### 技术规格

| 项目 | 规格 |
|------|------|
| 输入 | `*_analyzed_cleaned.json` 的 `mentioned_sectors` |
| 输出 | `data/rotation/{username}_rotation.json` + Streamlit 热力图 |
| 核心方法 | 周频聚合 + 滚动 Z-score + 排名变化 |
| 外部依赖 | `plotly`（可视化） |
| 代码位置 | `scripts/compute_rotation.py` |
| 代码量 | 约 150 行 |

### 算法流程

```
1. 提取所有推文的 created_at + mentioned_sectors
2. 按周聚合：每周每个 sector 的提及次数
3. 4 周滚动窗口：
   sector_z = (本周次数 - 4周均值) / 4周标准差
4. 排名变化：本周 rank - 上周 rank
5. 输出热力图（日期 × 行业，颜色 = Z-score）
```

### 开发检查点

- [ ] 1. 周聚合逻辑
- [ ] 2. 滚动 Z-score 计算
- [ ] 3. plotly 热力图渲染
- [ ] 4. Streamlit 面板集成

### 测试标准

- 至少 4 周数据不报错
- 极端 Z-score（> 3）标记为异常

---

## 模块 #9：情绪时间线 ⭐ P2

**定位**：Phase 3——单股 × 单人的态度变化可视化

### 技术规格

| 项目 | 规格 |
|------|------|
| 输入 | `*_analyzed_cleaned.json` + `prices.json` |
| 输出 | Streamlit 交互图表：双轴 K 线 + stance 散点 |
| 核心方法 | 时序对齐 + plotly 双轴图 |
| 外部依赖 | `plotly` |
| 代码位置 | `scripts/timeline_chart.py` |
| 代码量 | 约 100 行 |

### 开发检查点

- [ ] 1. 按股票 + 分析师筛选数据
- [ ] 2. stance → Y 轴映射（看多=上，看空=下）
- [ ] 3. K 线双轴叠加
- [ ] 4. Streamlit 交互选择器：股票下拉 + 分析师下拉

### 测试标准

- NVDA × TJ_Research 应产出至少 10 个数据点
- 空数据股票不报错，提示"无数据"

---

## 模块 #7：角色代入选股 ⭐ P1（依赖 #1, #11, 画像）

**定位**：Phase 3 核心——"如果我是他，会买什么"

### 技术规格

| 项目 | 规格 |
|------|------|
| 输入 | 分析师画像 + #11 基本面 + K 线 + #1 信号 |
| 输出 | LLM 生成的结构化选股建议 |
| 核心方法 | System Prompt 注入画像 + LLM 推理 |
| 外部依赖 | LLM API（gpt-5.4 或 deepseek） |
| 代码位置 | `src/pipeline/role_picker.py` |
| 代码量 | 约 400 行 |

### System Prompt 结构（参考 TradingAgents-CN）

```
[Role]
你是 {analyst_name} 的投资决策模拟器。
以下是你完整的投资风格画像：

{portrait_markdown}

[Context]
现在你需要从以下股票池中选择投资标的。
每只股票附带：
- 当前价格 / SMA20 / 30日涨跌幅
- PE / ROE / 营收增速
- 该分析师历史信号分（来自 #1）

[Data]
{stock_pool_table}

[Task]
基于你的投资框架，从以上股票中选择 3-5 只，
说明理由，分配仓位（总和 100%），
并给出入场价格区间和止损线。
```

### 输出 Schema

```json
{
  "analyst": "TJ_Research",
  "sector": "AI半导体",
  "timestamp": "2026-05-25T08:00:00",
  "picks": [
    {
      "ticker": "NVDA",
      "allocation_pct": 40,
      "thesis": "GPU 需求持续，估值在历史中位",
      "entry_range": [105, 115],
      "stop_loss": 90,
      "confidence": 0.85
    }
  ],
  "cash_reserve_pct": 10
}
```

### 开发检查点

- [ ] 1. 画像 → System Prompt 格式化
- [ ] 2. 股票池数据组装（K线 + 基本面 + 信号分）
- [ ] 3. LLM 调用 + 输出解析
- [ ] 4. 人工评估 3 轮输出质量，调 prompt
- [ ] 5. Streamlit 交互面板：选分析师 + 选板块 → 输出方案

### 测试标准

- 输出必须包含入场区间和止损线（否则不合规）
- 不能推荐分析师从未提过的股票（否则 reasoning_chain 为空）
- 分配比例总和必须 = 100%

---

## 模块 #3：实时触发 ⭐ P1（依赖 #1）

**定位**：Phase 4——新推文自动进入流水线

### 技术规格

| 项目 | 规格 |
|------|------|
| 输入 | DB Tweet 表的新记录 |
| 输出 | 自动入队 filter → analyze |
| 核心方法 | DB 轮询 + 任务队列 |
| 外部依赖 | 无（复用已有 task_executor） |
| 代码位置 | `src/pipeline/auto_scheduler.py` |
| 代码量 | 约 180 行 |

### 关键设计

```python
# 加到 task_executor.py 主循环
last_checked_tweet_id = 0
DAILY_ANALYZE_BUDGET = 20  # 可配置

while True:
    new_tweets = get_tweets_since(last_checked_tweet_id)
    for tweet in new_tweets:
        if daily_analyze_count < DAILY_ANALYZE_BUDGET:
            enqueue_filter_task(tweet)
            enqueue_analyze_task(tweet)
    time.sleep(60)
```

### 开发检查点

- [ ] 1. DB 轮询：`SELECT * FROM tweets WHERE id > last_checked_id`
- [ ] 2. 日预算计数器（每天 00:00 重置）
- [ ] 3. 自动入队 filter + analyze
- [ ] 4. WebSocket 连接 → 前端进度实时显示

### 测试标准

- 模拟新推文入库 → 60 秒内自动创建 filter 任务
- 超预算后停止创建新任务
- 跨天自动重置预算

---

## 模块 #10：异常检测 ⭐ P1（依赖画像 #1）

**定位**：Phase 4——发现分析师行为偏离基线

### 技术规格

| 项目 | 规格 |
|------|------|
| 输入 | 画像 baseline（stance/sector/topic 分布）+ 新推文 |
| 输出 | 异常分数 + 触发日志 |
| 核心方法 | KL 散度（首选）/ finBERT embedding（备选） |
| 外部依赖 | 无（方案 A）/ `transformers`（方案 B） |
| 代码位置 | `scripts/detect_anomaly.py` |
| 代码量 | 约 280 行 |

### 算法流程（方案 A）

```
1. 从画像提取 baseline 分布：
   - topic: {个股分析: 0.4, 行业研判: 0.2, ...}
   - stance: {看多: 0.5, 观望: 0.3, ...}
   - sector: {AI: 0.6, 半导体: 0.3, ...}

2. 对最近 5 条推文：
   计算每条推文 vs baseline 的 KL 散度
   avg_kl = mean(KL 5 条推文, baseline)

3. 如果 avg_kl > threshold → 触发异常
   threshold 初始设为 baseline 历史推文的 KL 的 95% 分位数
```

### 开发检查点

- [ ] 1. 从画像提取分布
- [ ] 2. KL 散度计算
- [ ] 3. 滑动窗口（5 条）聚合
- [ ] 4. 阈值设为 95% 分位数
- [ ] 5. 对 TJ_Research 全量历史数据跑一遍，标注异常点

### 测试标准

- 正常推文 KL 应 < 阈值
- 方向突变推文（看多→看空同一股票）应触发

---

## 模块 #5：预警系统 ⭐ P2（依赖 #10 + 用户持仓 CSV）

**定位**：Phase 4——持仓股异常表态 → 推送

### 技术规格

| 项目 | 规格 |
|------|------|
| 输入 | 用户持仓 CSV + #10 异常检测输出 |
| 输出 | Telegram Bot 消息 |
| 外部依赖 | Telegram Bot API |
| 代码位置 | `src/interfaces/alert_bot.py` |
| 代码量 | 约 100 行 |

### 开发检查点

- [ ] 1. 读取持仓 CSV（ticker, cost, shares）
- [ ] 2. #10 异常与持仓股交叉过滤
- [ ] 3. Telegram Bot 发送格式化消息
- [ ] 4. 测试推送

---

## 模块 #12：投资者关联网络 ⭐ P2

**定位**：Phase 4——发现新信源

### 技术规格

| 项目 | 规格 |
|------|------|
| 输入 | DB Tweet 的 is_reply/is_quote/replied_to_user/quoted_user |
| 输出 | 有向图 + 中心度排名 + pyvis 交互图 |
| 核心方法 | networkx 图分析 |
| 外部依赖 | `networkx`, `pyvis` |
| 代码位置 | `scripts/build_network.py` |
| 代码量 | 约 180 行 |

### 开发检查点

- [ ] 1. 从 DB 构建边列表
- [ ] 2. 计算 PageRank / betweenness centrality
- [ ] 3. pyvis 渲染交互图
- [ ] 4. 推荐 Top 5 未被追踪的高中心度用户

---

## 模块 #13：持仓叠加层 ⭐ P1（依赖 #1, #2, #7）

**定位**：Phase 5——"如果你是我关注的分析师，你会怎么调我的仓"

### 技术规格

| 项目 | 规格 |
|------|------|
| 输入 | 用户持仓 CSV + #1 信号 + #2 准确率 + #7 角色代入 + #11 基本面 |
| 输出 | LLM 生成的结构化调仓建议 |
| 核心方法 | 持仓分析 + LLM 综合推理 |
| 外部依赖 | LLM API |
| 代码位置 | `src/pipeline/portfolio_advisor.py` |
| 代码量 | 约 450 行 |

### 关键约束

```
1. 建议必须基于分析师画像框架，不得脱离角色
2. 必须展示每只持仓的盈亏比和仓位占比
3. 输出必须包含"分析师会怎么做"和"你的实际情况"的差异分析
4. 强制人工确认——不做自动执行
```

### 开发检查点

- [ ] 1. 持仓 CSV 解析
- [ ] 2. 盈亏比 / 仓位占比计算
- [ ] 3. 分析师画像 + 持仓 → System Prompt 组装
- [ ] 4. LLM 输出结构化解析
- [ ] 5. 强制人工确认环节
- [ ] 6. 测试 3 轮，人工检查建议合理性

---

## 模块 #6：完整控制台 ⭐ P1（依赖前 12 个模块全部完成）

**定位**：Phase 5——统一仪表盘

### 技术规格

| 项目 | 规格 |
|------|------|
| 输入 | 前 12 个模块的输出 |
| 技术方案 | Streamlit（MVP）→ HTMX/Vue（远期） |
| 代码位置 | `src/interfaces/web_ui.py`（扩展现有） |
| 代码量 | 约 350 行 |

### 面板布局

```
┌─────────────────────────────────────────────────────┐
│  🧠 Twitter 蒸馏控制台                     [设置⚙]  │
├──────────┬──────────┬──────────┬────────────────────┤
│ 📡 信号  │ 📊 准确率 │ 🔥 板块  │ ⚠️ 预警           │
│  TOP 5   │  评分     │  热力图  │  最近 3 条         │
├──────────┴──────────┴──────────┴────────────────────┤
│ 📈 情绪时间线（选股 + 选人）                         │
├─────────────────────────────────────────────────────┤
│ 🤖 角色代入（选分析师 + 选板块 → 输出方案）          │
├─────────────────────────────────────────────────────┤
│ 💼 我的持仓（上传 CSV → 分析师视角建议）             │
├─────────────────────────────────────────────────────┤
│ 🕸️ 关联网络（推荐新信源）                            │
└─────────────────────────────────────────────────────┘
```

---

## 附录 A：完整文件清单

```
src/pipeline/
├── task_executor.py          # 已有：任务执行器
├── role_picker.py            # 新增 #7
├── portfolio_advisor.py      # 新增 #13
├── auto_scheduler.py         # 新增 #3

scripts/
├── backtest_accuracy.py      # 新增 #2
├── fetch_fundamentals.py     # 新增 #11
├── compute_signals.py        # 新增 #1
├── compute_consensus.py      # 新增 #4
├── compute_rotation.py       # 新增 #8
├── timeline_chart.py         # 新增 #9
├── detect_anomaly.py         # 新增 #10
├── build_network.py          # 新增 #12

src/interfaces/
├── alert_bot.py              # 新增 #5

data/
├── accuracy/                 # 新增目录：#2 输出
├── consensus/                # 新增目录：#4 输出
├── rotation/                 # 新增目录：#8 输出
├── fundamental_cache.json    # 新增 #11 输出
```

---

## 附录 B：外部依赖清单

| 包 | 版本要求 | 用途 | 模块 |
|----|---------|------|------|
| `backtesting` | ≥0.3.3 | 回测框架 | #2 |
| `plotly` | ≥5.0 | 交互图表 | #8, #9 |
| `networkx` | ≥3.0 | 图分析 | #12 |
| `pyvis` | ≥0.3 | 图可视化 | #12 |
| `scipy` | ≥1.10 | KL 散度 | #10 |
| `numpy` | ≥1.24 | 数值计算 | #1, #8, #10 |
| `python-telegram-bot` | ≥20.0 | 推送 | #5 |
| `pandas` | ≥2.0 | 数据处理 | 全局 |

> 注：`transformers` + `finBERT` 预留为 #10 备选方案，初期不安装。

---

## 附录 C：模块间数据流

```
#2 准确率 ──→ accuracy/*.json
                 ↓
#1 信号量化 ──→ analyzed_cleaned + signal_score
                 ↓
#4 多信号联动 ←── #1 输出
                 ↓
#7 角色代入 ←── 画像 + #11 基本面 + #1 信号
                 ↓
#13 持仓叠加 ←── #7 + #2 + #1 + 用户 CSV
                 ↓
#6 控制台 ←── 全部前序模块
```

---

*最后更新：2026-05-25 · 版本 1.0*
