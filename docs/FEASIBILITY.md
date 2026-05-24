# 13 方向 — 工程可行性评估

> 评估维度：代码量 · 数据依赖 · 参考项目可复用度 · 集成风险 · 框架兼容性

---

## 逐个方向评估

### #1 信号量化

| 维度 | 评估 |
|------|------|
| 代码量 | 200-300 行 |
| 依赖 | analyzed_cleaned.json（已有）+ prices.json（已有）|
| 难度 | ⭐⭐ 中等 |
| 风险 | 低。纯数学，无外部依赖 |

**技术路径**：
```
stance → 数值化（看多=+1, 观望=0, 看空=-1）
confidence → 贝叶斯后验（历史准确率做先验）
K 线共振 → (close - SMA20) / SMA20 std → Z-score
信号分 = 0.4×stance + 0.3×confidence_posterior + 0.2×momentum_z + 0.1×volume_ratio
```

**参考项目可复用度**：
- Yang 2025 论文：**可复用公式和阈值**，非代码
- FinRL 信号融合模块：**可借鉴信号权重设计模式**，不直接复用代码
- vectorbt：**可用于后续参数权重扫描**

**结论：可行，不依赖任何外部框架，纯 Python 脚本。**

---

### #2 准确率回溯

| 维度 | 评估 |
|------|------|
| 代码量 | 300-400 行 |
| 依赖 | analyzed_cleaned.json（已有）+ prices.json（已有）|
| 难度 | ⭐⭐ 中等 |
| 风险 | 中低。核心挑战是日期对齐和股票代码匹配 |

**技术路径**：
```
对每条 action_hint ∈ {买入,加仓,卖出,减仓} 的推文：
  1. 提取推文日期 + 提到的股票
  2. 取推文日收盘价 → entry_price
  3. 计算 t+7 / t+30 的 excess_return vs SPY
  4. 汇总：胜率、平均超额收益、夏普比率、最大回撤
  5. 按月/按股票分组展示
```

**参考项目可复用度**：
| 项目 | 可复用度 | 理由 |
|------|---------|------|
| backtesting.py | ⭐⭐⭐ | 直接用 `pip install backtesting`，20 分钟出结果 |
| eventstudy PyPI | ⭐⭐⭐ | CAAR + 显著性检验开箱即用 |
| PakHsi0317 项目 | ⭐ | 学术课程项目，0 star，代码质量无法保证 |

**框架选择建议**：只用 **backtesting.py**，不混用。其他框架（vectorbt/Zipline）是后续优化时按需引入。

**结论：可行。backtesting.py 5 分钟安装、20 分钟跑通第一条回测。**

---

### #3 实时触发

| 维度 | 评估 |
|------|------|
| 代码量 | 150-200 行（加到现有 executor）|
| 依赖 | 现有 task_executor.py（已有）|
| 难度 | ⭐⭐ 中等 |
| 风险 | 中。API 调用成本和速率限制是主风险 |

**技术路径**：
```
现有 executor 是 while True 轮询 pending 任务
→ 加一个 scheduler 协程：
  1. 每 60 秒扫描 DB 新推文（id > last_checked_id）
  2. 自动入队 filter → 自动入队 analyze
  3. analyze 完成后检查持仓股是否有新信号
  4. 有信号 → WebSocket/Telegram 推送
  5. 日预算上限（默认 20 次 analyze/天）
```

**参考项目可复用度**：
- Fintwit.ai：**不可复用代码**，但架构描述有参考价值
- FastAPI BackgroundTasks：**文档**，非项目

**结论：可行。就是给现有 executor 加一个定时扫描循环。核心工作是速率控制。**

---

### #4 多信号联动

| 维度 | 评估 |
|------|------|
| 代码量 | < 100 行 |
| 依赖 | #1 做完后的信号数据 |
| 难度 | ⭐ 低 |
| 风险 | 极低 |

**技术路径**：
```
对每只股票：
  weight_TJ = TJ_准确率 / (TJ_准确率 + dearbaibabybus_准确率)
  联动分 = weight_TJ × TJ_signal + weight_dearbaibabybus × dearbaibabybus_signal
  if 两人同时提到且同向 → 联动分 × 1.3 bonus
```

**结论：一行加权平均。所有依赖的数据来自 #1 和 #2。**

---

### #5 预警系统

**结论：方向 #10 的应用子集。不独立评估。** 做完 #10 后用持仓股列表过滤即可。

---

### #6 可执行输出面板

| 维度 | 评估 |
|------|------|
| 代码量 | 200-300 行（Streamlit）/ 500+（Vue）|
| 依赖 | #1 → #4 全部做完 |
| 难度 | ⭐ 低（Streamlit）/ ⭐⭐⭐ 高（Vue）|
| 风险 | 低 |

**结论：长远方向。前 4 个方向做完后，Streamlit 15 分钟拼一个 TOP5 面板。**

---

### #7 角色代入选股

| 维度 | 评估 |
|------|------|
| 代码量 | 300-500 行 |
| 依赖 | 完整画像（已有）+ K 线（已有）+ #11 基本面 |
| 难度 | ⭐⭐⭐ 中高 |
| 风险 | 中。LLM 输出质量是瓶颈 |

**技术路径**：
```
1. 取 TJ_Research 全量画像 → system prompt
2. 注入板块股票池（NVDA/AVGO/AMD/MRVL... + K 线摘要 + PE/ROE）
3. 调用 gpt-5.4（1M context），问题："基于你的投资框架，从以上股票中选择并分配仓位"
4. 解析 LLM 输出 → 结构化推荐
```

**参考项目可复用度**：
| 项目 | 可复用度 | 理由 |
|------|---------|------|
| TradingAgents-CN | ⭐⭐⭐ | **可直接学习 system prompt 设计 + 多智能体辩论机制**，架构接近 |
| L-PPR 论文 | ⭐⭐ | Prompt 设计范式可参考，代码不可复用 |

**关键发现**：TradingAgents-CN 的 system prompt 结构可以直接借鉴——它把角色拆成"技术分析师""基本面分析师""新闻分析师""交易员"四个智能体，互相辩论后输出决策。我们的"角色代入"就是把画像塞进 system prompt，替代它的预定义角色。

**结论：可行。关键是 prompt engineering，不需要复杂架构。**

---

### #8 板块轮动检测

| 维度 | 评估 |
|------|------|
| 代码量 | 100-150 行 |
| 依赖 | analyzed_cleaned.json 的 mentioned_sectors |
| 难度 | ⭐ 低 |
| 风险 | 极低 |

**技术路径**：
```
mentioned_sectors 按周聚合 → 滚动 Z-score(4 周) → 排名变化 → 热力图/Sankey
```

**结论：最简单的方向之一。纯数据聚合 + matplotlib/plotly 画图。**

---

### #9 情绪时间线

| 维度 | 评估 |
|------|------|
| 代码量 | 100 行 |
| 依赖 | analyzed_cleaned.json |
| 难度 | ⭐ 低 |
| 风险 | 极低 |

**结论：是对 #2 的可视化副产品。双轴图：上轴股价、下轴 stance 散点。**

---

### #10 异常检测

| 维度 | 评估 |
|------|------|
| 代码量 | 250-350 行 |
| 依赖 | 画像 + 新推文 embedding |
| 难度 | ⭐⭐⭐ 中高 |
| 风险 | 中高。误报率调优需要长时间迭代 |

**技术路径**：
```
方案 A（轻量，推荐）：
  画像基线 → stance 分布 + topic 分布 + sector 分布
  新推文 → 计算 KL 散度 vs 基线
  连续 5 条推文 KL > 阈值 → 触发

方案 B（重量）：
  finBERT 做推文 embedding → 画像向量中心 → Cosine 距离检测
```

**参考项目可复用度**：
| 项目 | 可复用度 | 理由 |
|------|---------|------|
| finBERT | ⭐⭐⭐ | `pip install transformers` → 直接加载模型做 embedding |
| PyOD | ⭐⭐ | 60+ 检测器，但主要是数值异常，文本异常需 self-built |

**推荐先用方案 A（KL 散度，纯数学），效果不够再上 finBERT。**

---

### #11 基本面快照

| 维度 | 评估 |
|------|------|
| 代码量 | 100 行 |
| 依赖 | Polygon API（已注册）|
| 难度 | ⭐ 低 |
| 风险 | 极低 |

**技术路径**：
```python
# Polygon 免费已包含财报端点
GET https://api.polygon.io/vX/reference/financials/{ticker}?apiKey=...
→ PE, ROE, revenue_growth, debt_to_equity
→ 缓存到 data/fundamental_cache.json
```

**结论：就是调 API + 缓存。和其它方向无耦合。**

---

### #12 投资者关联网络

| 维度 | 评估 |
|------|------|
| 代码量 | 200 行 |
| 依赖 | DB 的 is_reply/is_quote/replied_to_user/quoted_user |
| 难度 | ⭐⭐ 中等 |
| 风险 | 低 |

**技术路径**：
```python
G = nx.DiGraph()
for tweet in db_tweets:
    if tweet.is_reply:
        G.add_edge(tweet.author, tweet.replied_to_user, weight=1)
# 中心性 → 推荐新信源
# pyvis → 交互可视化
```

**结论：networkx + pyvis 标准组合，稳定可靠。**

---

### #13 持仓叠加层

| 维度 | 评估 |
|------|------|
| 代码量 | 400-500 行 |
| 依赖 | #1 + #2 + #7 + 用户持仓 CSV |
| 难度 | ⭐⭐⭐⭐ 高 |
| 风险 | 高。直接涉及真实资金决策，需人工确认环节 |

**技术路径**：
```
1. 读取用户持仓 CSV（股票/成本/数量/日期）
2. 计算每只盈亏比、仓位占比
3. 注入方向 #1 信号 + 分析师画像 + K 线
4. LLM 综合推理："基于 TJ 的框架，你的 AVGO 持仓..."
5. 输出建议 + 强制人工确认
```

**结论：方向 #7 做完后再启动。所有底层数据依赖前序方向。核心复杂度在 LLM prompt 而非代码。**

---

## 框架组合可行性评估

### 核心问题：8 个量化框架能不能组合？

**答案：不组合。按需串行使用。**

```
方向 #2 MVP：
  pip install backtesting.py → 跑第一条回测
  → 不需要任何其他框架

方向 #2 进阶（参数优化）：
  pip install vectorbt → 独立脚本扫描 signal_weights
  → 不需要和 backtesting.py 互操作

方向 #2 最终验证：
  pip install zipline-reloaded → 独立脚本验证无前视偏差
  → 输出和 backtesting.py 对比，不同系统跑同样的数据

方向 #1 远期升级：
  pip install finrl → 独立训练 RL agent
  → 完全独立的子系统
```

**集成风险：零。** 每个框架都是独立的 Python 脚本，从同一个 `data/prices.json` 读数据，不存在 API 冲突或耦合。它们不需要"组合"——分别运行、比对结果。

### 真正要小心的

| 风险 | 等级 | 应对 |
|------|------|------|
| backtesting.py 有前视偏差 | 低 | event study 模式天然无前视偏差（买入点是固定日期） |
| vectorbt 和 numpy 版本冲突 | 低 | 用独立 venv 或 `pip install --user` |
| 不同框架的计算结果不一致 | 中 | 这是预期行为——用最严格的 Zipline 做最终基准 |
| FinRL 训练不稳定 | 高 | 这是 RL 的固有问题，不是框架问题。留给远期 |

---

## 总评

| 区间 | 方向 | 共性 |
|------|------|------|
| **立即可做**（1-2天/个） | #2→#1→#4→#8→#9→#11 | 纯数据计算，0 外部框架依赖 |
| **中期可做**（3-5天/个） | #7→#3→#10→#12 | 需要前序方向产出 + LLM prompt tuning |
| **远期** | #6→#5→#13 | 依赖大部分前序方向完成 |

**最重要的结论：**
1. 参考项目从 **代码层面可复用度低**（TradingAgents-CN 除外），但 **方法论和设计模式可复用度高**
2. 量化框架**不需要组合**，串行调用、独立脚本，零集成风险
3. 前 6 个方向写完大约 1500 行 Python——工程上完全可控
