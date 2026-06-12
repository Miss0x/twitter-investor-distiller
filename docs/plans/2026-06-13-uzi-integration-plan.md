# UZI-Skill 优点嫁接方案

> 日期：2026-06-13 | 参考：UZI-Skill (wbh604/UZI-Skill) | 当前测试：124 passed

---

## 一、可直接使用的（已有技能，零成本接入）

### 1. 金融数据维度 — 通过已有技能

| UZI-Skill 维度 | 我们的替代方案 | 接入方式 |
|---------------|-------------|---------|
| 实时股价 (yfinance) | `src/data/financial.py` (yfinance) | ✅ 已实现 |
| 基本面 (PE/PB/ROE) | `src/data/financial.py` (yfinance) | ✅ 已实现 |
| 板块/行业 | `src/data/financial.py` get_sector() | ✅ 已实现 |
| 财报日历 | `src/data/financial.py` get_earnings() | ✅ 已实现 |
| A股行情 | `westock-data` skill | 可调用 |
| 美股深度分析 | `stock-analysis` / `us-stock-analysis` skill | 可调用 |
| 宏观数据 | `macro-monitor` skill | 可调用 |
| 机构评级/研报 | `westock-data` skill | 可调用 |

**已实现**: `src/data/financial.py`
- `get_price(symbol)` → 最新价格 + 52周范围 + 市值
- `get_fundamentals(symbol)` → PE/PB/ROE/负债率/增长率/股息率
- `get_sector(symbol)` → 行业 + 板块分类
- `get_earnings_calendar(symbol)` → 近/远期财报日期
- 本地 JSON 缓存：价格 5min, 基本面 24h, 财报 12h
- 异常安全：任一接口失败不影响其他

### 2. 测试覆盖提升 — 方法论直接复制

| UZI-Skill 做法 | 我们的做法 | 状态 |
|---------------|----------|------|
| 每维度独立 fetcher + 独立测试 | `src/data/financial.py` + `tests/test_financial_data.py` | ✅ |
| 端到端测试 | `tests/test_governance_end_to_end.py` | ✅ |
| 数据缺口显式标注 | `src/governance/data_gaps.py` DataGap Registry | ✅ |
| 机械级自查 gate | Quality Gate + Risk Scan + Publish Gate | ✅ |
| 632 tests 全覆盖 | 109 → 124 tests (追赶到 ~20%) | 🔄 |

---

## 二、需要适配后接入的（中期）

### 1. 17 种机构分析模型 → 8 角色评分

UZI-Skill 的 17 个模型按类型分组，每个组映射到我们的角色：

| UZI 模型 | 我们的角色 | 适配方案 |
|----------|----------|---------|
| DCF/DDM/PE/PB 估值类 | `value` | 已有 ✅ |
| Momentum/RSI/MACD | `momentum` | 已有 ✅ |
| CANSLIM/Growth | `growth` | 已有 ✅ |
| 量化选股/因子模型 | `quant` (+quality) | 已有部分 ⚠️ |
| 风险模型/波动率 | `risk_mgr` | 已有 ✅ |
| 宏观/利率 | `macro` | 已有 ✅ |
| 技术分析/支撑阻力 | `technical` | 已有 ✅ |
| 逆向/情绪指标 | `contrarian` | 已有 ✅ |

**结论**: 我们的 8 个治理角色已经覆盖了 UZI-Skill 17 个模型的核心分类。不需要新增角色，但可以增强每个角色的评分维度。

### 2. 多角色共识分指标

```python
# 新增指标: 每个信号的 8 角色评分分布
consensus_score = {
    "signal_id": "...",
    "bullish_votes": 6,  # value + growth + momentum + quality + macro + technical
    "bearish_votes": 2,  # contrarian + risk_mgr
    "neutral_votes": 0,
    "conviction": "high",  # 6:2 看多一致
    "dissenting_roles": ["contrarian", "risk_mgr"],
}
```

接入位置：`src/governance/panel_review.py` 的 `aggregate_panel_results()`

### 3. 历史胜率追踪

```python
# 每个角色/信号的历史准确率
class AccuracyTracker:
    def log_prediction(role, ticker, direction, confidence, timestamp)
    def verify_prediction(ticker, actual_return, verification_date)
    def get_role_winrate(role, lookback_days=90)
```

---

## 三、三轨实施路线

### 轨道 1: 金融数据 (已完成 ✅)

```
✅ src/data/financial.py — 价格/基本面/板块/财报
✅ tests/test_financial_data.py — 6 测试
⏳ 接入 Pipeline: 在 task_executor 中调用 financial.get_price(ticker)
```

### 轨道 2: 测试覆盖 (进行中 🔄)

```
✅ tests/test_auth.py — 9 测试
✅ tests/test_multi_tenant_config.py — 7 测试
✅ tests/test_financial_data.py — 6 测试
⏳ tests/test_ai_chat_engine.py — 待补充
⏳ tests/test_crawler.py — 待补充
⏳ tests/test_interfaces_handlers.py — 待补充
```

### 轨道 3: 多角色增强 (待启动)

```
⏳ consensus_score 指标 — panel_review.py 新增
⏳ accuracy_tracker — 新建 src/governance/accuracy_tracker.py
```

---

## 四、与 UZI-Skill 的最终对比（更新后）

| 维度 | UZI-Skill | 我们 (当前) | 我们 (轨道3后) |
|------|-----------|-----------|--------------|
| 数据维度 | 22 | 5 (Twitter+价格+基本面+板块+财报) | 8+ 接入更多 skill |
| 分析模型 | 17 | 8 治理角色 | 8 + 共识分 + 胜率追踪 |
| 测试数 | 632 | 124 | 200+ |
| 多用户 | ❌ | ✅ | ✅ |
| 安全加密 | ❌ | ✅ | ✅ |
| Web Dashboard | ❌ | ✅ 25 卡片 | ✅ |
| 管理后台 | ❌ | ✅ | ✅ |
| 信号通知 | ❌ | ✅ Telegram | ✅ |

**核心差异**：我们是 SaaS 平台，UZI-Skill 是 CLI 工具。数据维度可追赶，但我们不需要照搬 22 个维度 — 精选 8-10 个最高信号质量的维度就够了。
