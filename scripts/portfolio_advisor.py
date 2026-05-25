"""#13 持仓叠加层 — Phase 5

读取用户持仓 CSV → 注入分析师画像 + #1 信号 + #2 准确率 + #7 角色代入
→ 生成 LLM prompt："如果分析师看到你的持仓，他会怎么调"

强制人工确认环节——不做自动执行。

用法：python scripts/portfolio_advisor.py
"""
from __future__ import annotations

import json
from pathlib import Path

PIPELINE_DIR = Path("data/pipeline")
ACCURACY_DIR = Path("data/accuracy")
FUND_CACHE = Path("data/fundamental_cache.json")
PRICES_PATH = Path("data/prices.json")
PORTFOLIO_PATH = Path("data/my_portfolio.csv")


def load_portfolio() -> list[dict]:
    """加载持仓 CSV。"""
    if not PORTFOLIO_PATH.exists():
        print(f"⚠️ 无持仓文件，创建模板: {PORTFOLIO_PATH}")
        PORTFOLIO_PATH.write_text("ticker,cost,shares\nNVDA,110,50\nAVGO,320,20\n", encoding="utf-8")
        print("  请编辑后重新运行")
        return []
    rows = []
    for line in PORTFOLIO_PATH.read_text(encoding="utf-8").strip().split("\n")[1:]:
        parts = line.split(",")
        if len(parts) >= 3:
            try:
                rows.append({"ticker": parts[0].strip().upper(), "cost": float(parts[1]), "shares": float(parts[2])})
            except ValueError:
                pass
    return rows


def load_signals(tickers: list[str]) -> dict[str, list]:
    """加载每只持仓股的最新信号。"""
    signals: dict[str, list] = {}
    for fp in sorted(PIPELINE_DIR.glob("*_analyzed_cleaned.json")):
        username = fp.stem.split("_")[0]
        if username == "TJ":
            username = "TJ_Research"
        for r in json.loads(fp.read_text(encoding="utf-8")):
            ss = r.get("signal_score", 0)
            if ss == 0:
                continue
            for s in r.get("stock_details", []):
                t = s.get("ticker", "").upper()
                if t in tickers:
                    if t not in signals:
                        signals[t] = []
                    signals[t].append({
                        "analyst": username,
                        "signal": ss,
                        "stance": r.get("stance", ""),
                        "action": r.get("action_hint", ""),
                        "date": r.get("created_at", "")[:10],
                        "text": (r.get("text", "") or "")[:100],
                    })
    return signals


def load_accuracy() -> dict:
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
    if not FUND_CACHE.exists():
        return {}
    cache = json.loads(FUND_CACHE.read_text(encoding="utf-8"))
    return {t: cache.get(t, {}) for t in tickers}


def load_prices_snapshot(tickers: list[str]) -> dict:
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
                "chg_30d": round((latest["c"] - bars[-22]["c"]) / bars[-22]["c"] * 100, 1) if len(bars) >= 22 else None,
            }
    return result


def build_prompt(portfolio: list[dict], signals: dict, acc: dict, fundamentals: dict, price_snap: dict) -> str:
    # 持仓表
    lines = [
        "## 你的持仓",
        "| 股票 | 成本 | 数量 | 市值 | 盈亏 | 占仓 | 当前价 | 30日涨跌 | PE | ROE |",
        "|------|------|------|------|------|------|--------|---------|-----|-----|",
    ]
    total_value = 0
    for p in portfolio:
        price = price_snap.get(p["ticker"], {}).get("current_price", 0)
        val = price * p["shares"]
        p["_current_value"] = val
        total_value += val

    for p in portfolio:
        t = p["ticker"]
        price = price_snap.get(t, {}).get("current_price", 0)
        chg = price_snap.get(t, {}).get("chg_30d", "?")
        pe = fundamentals.get(t, {}).get("pe_ratio", "?")
        roe = fundamentals.get(t, {}).get("roe", "?")
        pnl_pct = round((price - p["cost"]) / p["cost"] * 100, 1) if price > 0 else 0
        weight = round(p["_current_value"] / total_value * 100, 1) if total_value > 0 else 0
        lines.append(
            f"| {t} | ${p['cost']:.0f} | {p['shares']:.0f} | ${p['_current_value']:.0f} | "
            f"{pnl_pct:+.1f}% | {weight:.1f}% | ${price:.0f} | {chg} | {pe} | {roe} |"
        )

    # 信号
    lines.append(f"\n## 分析师最新信号")
    for t in sorted(signals):
        sig_list = signals[t][-5:]  # 最近 5 条
        for s in sig_list:
            lines.append(f"- [{s['analyst']}] {s['date']} {t} 信号={s['signal']:.0f} {s['stance']}: {s['text'][:60]}")

    # 准确率
    lines.append(f"\n## 分析师准确率（30日）")
    for u, a in acc.items():
        wr = f"{a['win_rate_30d']*100:.0f}%" if a['win_rate_30d'] else "?"
        ar = f"{a['avg_return_30d']*100:+.1f}%" if a['avg_return_30d'] else "?"
        lines.append(f"- {u}: 胜率 {wr} 均收益 {ar} 夏普 {a.get('sharpe', '?')}")

    # 指令
    lines.append(f"""
## 任务
你是投资顾问，基于以上数据，为每只持仓股给出建议。格式：

```json
{{
  \"recommendations\": [
    {{
      \"ticker\": \"NVDA\",
      \"action\": \"加仓|减仓|持有|清仓\",
      \"analyst_perspective\": \"基于XXX分析师的框架，他认为...\",
      \"your_situation\": \"你的成本$110比分析师平均入场价高15%，当前盈亏+30%\",
      \"suggested_allocation\": 30,
      \"risk_note\": \"该分析师历史上此类判断的胜率为XX%\"
    }}
  ],
  \"cash_recommendation\": \"建议保留X%现金\",
  \"overall_note\": \"总体建议\"
}}
```

⚠️ 必须是 JSON，不做自动交易决策。
""")
    return "\n".join(lines)


def main():
    portfolio = load_portfolio()
    if not portfolio:
        return

    tickers = [p["ticker"] for p in portfolio]
    print(f"持仓: {len(portfolio)} 只 — {', '.join(tickers)}")

    signals = load_signals(tickers)
    acc = load_accuracy()
    fundamentals = load_fundamentals(tickers)
    price_snap = load_prices_snapshot(tickers)

    prompt = build_prompt(portfolio, signals, acc, fundamentals, price_snap)

    out_path = Path("data/portfolio_advice_prompt.txt")
    out_path.write_text(prompt, encoding="utf-8")
    print(f"\n✅ Prompt 已保存: {out_path} ({len(prompt)} 字符)")
    print("  可直接粘贴到 LLM 对话获取建议。")


if __name__ == "__main__":
    main()
