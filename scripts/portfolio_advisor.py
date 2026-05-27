"""#13 持仓叠加层 — Phase 5

读取用户持仓 CSV，注入分析师画像 + #1 信号分 + #2 准确率 + #7 角色代入结果，
生成 LLM prompt："如果分析师看到你的持仓，他会怎么调？"

设计原则：
- 强制人工确认环节：本模块只生成 prompt，不做自动交易决策
- 多维度数据融合：持仓盈亏 + 分析师信号 + 历史胜率 + 基本面
- 输出结构化 JSON 建议（加仓/减仓/持有/清仓 + 理由 + 风险提示）

数据依赖：
- data/my_portfolio.csv: 用户持仓（ticker, cost, shares）
- data/pipeline/*_analyzed_cleaned.json: 分析师信号分
- data/accuracy/*_accuracy.json: 分析师历史准确率
- data/fundamental_cache.json: 基本面数据
- data/prices.json: K 线快照

用法：
    python scripts/portfolio_advisor.py
"""
from __future__ import annotations

import json
from pathlib import Path

# ---- 数据路径配置 ----
PIPELINE_DIR = Path("data/pipeline")             # 分析师信号
ACCURACY_DIR = Path("data/accuracy")              # 历史准确率
FUND_CACHE = Path("data/fundamental_cache.json")  # 基本面
PRICES_PATH = Path("data/prices.json")            # K 线
PORTFOLIO_PATH = Path("data/my_portfolio.csv")    # 用户持仓


def load_portfolio() -> list[dict]:
    """加载用户持仓 CSV。

    CSV 格式：ticker,cost,shares
    - ticker: 股票代码（如 NVDA）
    - cost: 建仓均价（美元）
    - shares: 持有股数

    如果文件不存在，自动创建模板文件（含示例数据），提示用户编辑后重新运行。

    Returns:
        list[dict]: [{"ticker": "NVDA", "cost": 110.0, "shares": 50.0}, ...]
    """
    if not PORTFOLIO_PATH.exists():
        print(f"无持仓文件，创建模板: {PORTFOLIO_PATH}")
        # 创建示例模板
        PORTFOLIO_PATH.write_text(
            "ticker,cost,shares\nNVDA,110,50\nAVGO,320,20\n", encoding="utf-8"
        )
        print("  请编辑后重新运行")
        return []

    rows = []
    # 跳过表头，从第二行开始解析
    for line in PORTFOLIO_PATH.read_text(encoding="utf-8").strip().split("\n")[1:]:
        parts = line.split(",")
        if len(parts) >= 3:
            try:
                rows.append({
                    "ticker": parts[0].strip().upper(),
                    "cost": float(parts[1]),
                    "shares": float(parts[2]),
                })
            except ValueError:
                # 跳过格式错误的行
                pass
    return rows


def load_signals(tickers: list[str]) -> dict[str, list]:
    """加载每只持仓股对应的最新分析师信号。

    只加载 signal_score > 0 的信号（即分析师明确表态的），
    信号为零的记录（如"观望"、"无明确方向"）对持仓建议无增量信息。

    Args:
        tickers: 用户持仓的股票代码列表

    Returns:
        dict[str, list]: {ticker: [{analyst, signal, stance, action, date, text}]}
                         每只股票最多保留所有相关信号
    """
    signals: dict[str, list] = {}
    for fp in sorted(PIPELINE_DIR.glob("*_analyzed_cleaned.json")):
        username = fp.stem.split("_")[0]
        if username == "TJ":
            username = "TJ_Research"
        for r in json.loads(fp.read_text(encoding="utf-8")):
            ss = r.get("signal_score", 0)
            if ss == 0:
                continue  # 跳过无信号记录
            for s in r.get("stock_details", []):
                t = s.get("ticker", "").upper()
                if t in tickers:
                    if t not in signals:
                        signals[t] = []
                    signals[t].append({
                        "analyst": username,
                        "signal": ss,                          # 0-100 信号分
                        "stance": r.get("stance", ""),         # 看多/看空/观望
                        "action": r.get("action_hint", ""),    # LLM 输出的行动建议
                        "date": r.get("created_at", "")[:10],  # 推文日期
                        "text": (r.get("text", "") or "")[:100],  # 推文前 100 字符
                    })
    return signals


def load_accuracy() -> dict:
    """加载各分析师的 30 日准确率数据。

    Returns:
        dict: {username: {win_rate_30d, avg_return_30d, sharpe}}
              无数据的分析师不出现在结果中
    """
    acc = {}
    for fp in ACCURACY_DIR.glob("*_accuracy.json"):
        u = fp.stem.replace("_accuracy", "")
        d = json.loads(fp.read_text(encoding="utf-8"))
        acc[u] = {
            "win_rate_30d": d.get("returns_30d", {}).get("win_rate"),
            "avg_return_30d": d.get("returns_30d", {}).get("avg_return"),
            "sharpe": d.get("returns_30d", {}).get("sharpe"),
        }
    return acc


def load_fundamentals(tickers: list[str]) -> dict:
    """加载股票基本面数据。

    Returns:
        dict: {ticker: {pe_ratio, roe, revenue_growth_yoy, ...}}
              无数据的股票返回空字典
    """
    if not FUND_CACHE.exists():
        return {}
    cache = json.loads(FUND_CACHE.read_text(encoding="utf-8"))
    return {t: cache.get(t, {}) for t in tickers}


def load_prices_snapshot(tickers: list[str]) -> dict:
    """加载股票最新价格快照。

    Returns:
        dict: {ticker: {current_price, chg_30d}}
              current_price: 最新收盘价
              chg_30d: 30 日涨跌幅（%）
    """
    if not PRICES_PATH.exists():
        return {}
    prices = json.loads(PRICES_PATH.read_text(encoding="utf-8"))
    result = {}
    for t in tickers:
        bars = prices.get(t, {}).get("results", [])
        if bars:
            latest = bars[-1]
            result[t] = {
                "current_price": latest["c"],
                "chg_30d": (
                    round(
                        (latest["c"] - bars[-22]["c"]) / bars[-22]["c"] * 100, 1
                    )
                    if len(bars) >= 22
                    else None
                ),
            }
    return result


def build_prompt(
    portfolio: list[dict],
    signals: dict,
    acc: dict,
    fundamentals: dict,
    price_snap: dict,
) -> str:
    """构建持仓顾问 LLM prompt。

    Prompt 由四个部分组成：

    1. 持仓表：Markdown 表格，包含每只股票的：
       - 成本价、数量、当前市值
       - 盈亏百分比、仓位权重
       - 当前价、30日涨跌、PE、ROE

    2. 分析师最新信号：对每只持仓股，列出最近 5 条分析师信号

    3. 分析师准确率：30 日胜率 + 平均收益 + 夏普比率

    4. 任务指令：要求 LLM 以 JSON 格式输出每只股票的建议，
       包括行动（加仓/减仓/持有/清仓）、分析师视角、用户自身情况、
       建议仓位、风险提示

    Args:
        portfolio: 用户持仓列表
        signals: 分析师信号
        acc: 分析师准确率
        fundamentals: 基本面数据
        price_snap: 价格快照

    Returns:
        str: 完整的 LLM prompt 文本
    """
    # ---- Part 1: 持仓表 ----
    lines = [
        "## 你的持仓",
        "| 股票 | 成本 | 数量 | 市值 | 盈亏 | 占仓 | 当前价 | 30日涨跌 | PE | ROE |",
        "|------|------|------|------|------|------|--------|---------|-----|-----|",
    ]

    # 第一遍：计算总市值（用于仓位百分比）
    total_value = 0.0
    for p in portfolio:
        price = price_snap.get(p["ticker"], {}).get("current_price", 0)
        val = price * p["shares"]
        p["_current_value"] = val  # 临时字段：当前市值
        total_value += val

    # 第二遍：生成表格行
    for p in portfolio:
        t = p["ticker"]
        price = price_snap.get(t, {}).get("current_price", 0)
        chg = price_snap.get(t, {}).get("chg_30d", "?")
        pe = fundamentals.get(t, {}).get("pe_ratio", "?")
        roe = fundamentals.get(t, {}).get("roe", "?")

        # 盈亏百分比
        pnl_pct = (
            round((price - p["cost"]) / p["cost"] * 100, 1) if price > 0 else 0
        )
        # 仓位权重
        weight = (
            round(p["_current_value"] / total_value * 100, 1)
            if total_value > 0
            else 0
        )

        lines.append(
            f"| {t} | ${p['cost']:.0f} | {p['shares']:.0f} | "
            f"${p['_current_value']:.0f} | {pnl_pct:+.1f}% | {weight:.1f}% | "
            f"${price:.0f} | {chg} | {pe} | {roe} |"
        )

    # ---- Part 2: 分析师最新信号 ----
    lines.append("\n## 分析师最新信号")
    for t in sorted(signals):
        sig_list = signals[t][-5:]  # 只展示最近 5 条
        for s in sig_list:
            lines.append(
                f"- [{s['analyst']}] {s['date']} {t} "
                f"信号={s['signal']:.0f} {s['stance']}: {s['text'][:60]}"
            )

    # ---- Part 3: 分析师准确率 ----
    lines.append("\n## 分析师准确率（30日）")
    for u, a in acc.items():
        wr = f"{a['win_rate_30d']*100:.0f}%" if a.get("win_rate_30d") else "?"
        ar = f"{a['avg_return_30d']*100:+.1f}%" if a.get("avg_return_30d") else "?"
        lines.append(
            f"- {u}: 胜率 {wr} 均收益 {ar} 夏普 {a.get('sharpe', '?')}"
        )

    # ---- Part 4: 任务指令 ----
    lines.append("""
## 任务
你是投资顾问，基于以上数据，为每只持仓股给出建议。格式：

```json
{
  \"recommendations\": [
    {
      \"ticker\": \"NVDA\",
      \"action\": \"加仓|减仓|持有|清仓\",
      \"analyst_perspective\": \"基于XXX分析师的框架，他认为...\",
      \"your_situation\": \"你的成本$110比分析师平均入场价高15%，当前盈亏+30%\",
      \"suggested_allocation\": 30,
      \"risk_note\": \"该分析师历史上此类判断的胜率为XX%\"
    }
  ],
  \"cash_recommendation\": \"建议保留X%现金\",
  \"overall_note\": \"总体建议\"
}
```

必须是 JSON，不做自动交易决策。
""")
    return "\n".join(lines)


def main():
    """持仓顾问主流程。

    执行步骤：
    1. 加载用户持仓 CSV（不存在则创建模板并退出）
    2. 提取持仓股列表
    3. 加载各项数据：分析师信号、历史准确率、基本面、价格快照
    4. 构建多维度 LLM prompt
    5. 保存 prompt 到文件供人工审查

    输出：
    - data/portfolio_advice_prompt.txt: LLM prompt 文件
    """
    # 加载持仓
    portfolio = load_portfolio()
    if not portfolio:
        return

    tickers = [p["ticker"] for p in portfolio]
    print(f"持仓: {len(portfolio)} 只 — {', '.join(tickers)}")

    # 加载各维度数据
    signals = load_signals(tickers)
    acc = load_accuracy()
    fundamentals = load_fundamentals(tickers)
    price_snap = load_prices_snapshot(tickers)

    # 构建 prompt
    prompt = build_prompt(portfolio, signals, acc, fundamentals, price_snap)

    # 保存
    out_path = Path("data/portfolio_advice_prompt.txt")
    out_path.write_text(prompt, encoding="utf-8")
    print(f"\nPrompt 已保存: {out_path} ({len(prompt)} 字符)")
    print("  可直接粘贴到 LLM 对话获取建议。")


if __name__ == "__main__":
    main()
