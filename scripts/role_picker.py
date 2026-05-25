"""#7 角色代入选股 — Phase 3 核心

加载分析师全量画像 + 基本面 + K线，注入 LLM system prompt，
模拟"如果我是他，这个板块我会选什么"。

用法：python scripts/role_picker.py TJ_Research "AI半导体"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PIPELINE_DIR = Path("data/pipeline")
CACHE_PATH = Path("data/fundamental_cache.json")
PRICES_PATH = Path("data/prices.json")


def load_portrait(username: str) -> str:
    """加载分析师全量画像 Markdown。"""
    # 找最新的 portrait 文件
    candidates = sorted(PIPELINE_DIR.glob(f"{username}*portrait.md"))
    if not candidates:
        # 尝试模糊匹配
        short = username.split("_")[0] if "_" in username else username[:3]
        candidates = sorted(PIPELINE_DIR.glob(f"{short}*portrait.md"))
    if not candidates:
        return f"[无画像] {username}"
    return candidates[-1].read_text(encoding="utf-8")


def load_tickers_by_sector(username: str, sector_hint: str) -> list[str]:
    """加载该分析师提及的股票，过滤出给定板块。"""
    # fuzzy: 搜索词拆开，任一命中 sectors/text/topic
    search_terms = [t.strip().lower() for t in sector_hint.replace("/", " ").split() if t.strip()]
    result = set()
    for fp in PIPELINE_DIR.glob("*_analyzed_cleaned.json"):
        u = fp.stem.split("_")[0]
        if u == "TJ":
            u = "TJ_Research"
        if u != username:
            continue
        for r in json.loads(fp.read_text(encoding="utf-8")):
            sectors_str = " ".join(r.get("mentioned_sectors", [])).lower()
            text = (r.get("text", "") or "").lower()
            topic = (r.get("topic", "") or "").lower()
            haystack = f"{sectors_str} {topic} {text}"
            if any(term in haystack for term in search_terms):
                for s in r.get("stock_details", []):
                    t = s.get("ticker", "").upper()
                    if t:
                        result.add(t)
    return sorted(result)


def load_stock_data(tickers: list[str]) -> list[dict]:
    """加载每只股票的基本面+K线快照。"""
    fundamentals = {}
    if CACHE_PATH.exists():
        fundamentals = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    prices = {}
    if PRICES_PATH.exists():
        prices = json.loads(PRICES_PATH.read_text(encoding="utf-8"))

    result = []
    for t in tickers:
        row = {"ticker": t}
        f = fundamentals.get(t, {})
        row["pe_ratio"] = f.get("pe_ratio")
        row["roe"] = f.get("roe")
        row["revenue_growth"] = f.get("revenue_growth_yoy")

        # K线：最新收盘 + 30日涨跌
        bars = prices.get(t, {}).get("results", [])
        if bars:
            latest = bars[-1]
            row["latest_close"] = latest["c"]
            if len(bars) >= 22:
                row["close_30d_ago"] = bars[-22]["c"]
                row["chg_30d_pct"] = round((bars[-1]["c"] - bars[-22]["c"]) / bars[-22]["c"] * 100, 1)

        result.append(row)
    return result


def build_prompt(portrait: str, sector: str, stocks: list[dict]) -> str:
    """构建 LLM system prompt。"""
    stock_table = "| Ticker | PE | ROE | 营收增速 | 最新价 | 30日涨跌 |\n"
    stock_table += "|--------|-----|-----|---------|--------|---------|\n"
    for s in stocks:
        pe = f"{s['pe_ratio']:.1f}" if s.get("pe_ratio") else "?"
        roe = f"{s['roe']:.1f}%" if s.get("roe") else "?"
        rg = f"{s['revenue_growth']*100:.0f}%" if s.get("revenue_growth") else "?"
        lc = f"${s['latest_close']:.0f}" if s.get("latest_close") else "?"
        chg = f"{s['chg_30d_pct']:+.1f}%" if s.get("chg_30d_pct") else "?"
        stock_table += f"| {s['ticker']} | {pe} | {roe} | {rg} | {lc} | {chg} |\n"

    prompt = f"""[Role]
你是分析师的投资决策模拟器。以下是该分析师的完整投资风格画像：

{portrait[:3000]}

[Task]
基于以上画像的投资框架，从以下 {sector} 板块股票池中选择 3-5 只最符合其投资理念的标的。
说明每只的 rationale（必须引用画像中的维度），分配仓位（总和 100%），给出入场区间和止损线。

[Stock Pool]
{stock_table}

[Output Format - JSON only]
{{
  "analyst": "name",
  "sector": "{sector}",
  "picks": [
    {{
      "ticker": "XXX",
      "allocation_pct": 30,
      "thesis": "理由（引用画像维度）",
      "entry_range": [low, high],
      "stop_loss": price
    }}
  ],
  "cash_reserve_pct": 10,
  "overall_thesis": "整体逻辑"
}}"""
    return prompt


def main():
    if len(sys.argv) < 3:
        print("用法: python scripts/role_picker.py <username> <sector>")
        print("例: python scripts/role_picker.py TJ_Research AI半导体")
        sys.exit(1)

    username = sys.argv[1]
    sector = sys.argv[2]

    portrait = load_portrait(username)
    print(f"画像: {len(portrait)} 字")

    tickers = load_tickers_by_sector(username, sector)
    print(f"板块 {sector}: {len(tickers)} 只 {tickers[:10]}...")

    stocks = load_stock_data(tickers)
    print(f"数据完整: {sum(1 for s in stocks if s.get('pe_ratio'))}/{len(stocks)} 有PE")

    prompt = build_prompt(portrait, sector, stocks)

    out_path = Path(f"data/role_pick_{username}_{sector}_prompt.txt")
    out_path.write_text(prompt, encoding="utf-8")
    print(f"\n✅ Prompt 已保存: {out_path}")
    print(f"   {len(prompt)} 字符，可直接粘贴到 LLM 对话中")


if __name__ == "__main__":
    main()
