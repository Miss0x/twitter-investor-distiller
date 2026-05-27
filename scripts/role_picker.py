"""#7 角色代入选股 — Phase 3 核心

加载分析师全量画像 + 基本面 + K线数据，注入 LLM system prompt，
模拟"如果我是这个分析师，在这个板块我会选什么股票"。

工作流程：
1. 加载目标分析师的完整投资风格画像（LLM 生成的 Markdown）
2. 从该分析师历史推文中提取与目标板块相关的股票列表
3. 加载每只候选股的基本面（PE、ROE、营收增速）和 K线快照（最新价、30日涨跌）
4. 构建 LLM system prompt：注入画像 + 股票数据表 + JSON 输出格式要求
5. 保存 prompt 到文件，供后续调用 LLM 使用

设计理念：
- "角色代入"不是让 LLM 自由发挥，而是强制它以画像中的投资框架为约束
- 输出格式为结构化 JSON（仓位、入场区间、止损线均有明确格式）

用法：
    python scripts/role_picker.py TJ_Research "AI半导体"
    python scripts/role_picker.py dearbaibabybus "消费电子"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PIPELINE_DIR = Path("data/pipeline")             # 分析师画像和分析结果目录
CACHE_PATH = Path("data/fundamental_cache.json")  # 基本面数据缓存
PRICES_PATH = Path("data/prices.json")            # K线快照数据


def load_portrait(username: str) -> str:
    """加载分析师的投资风格画像 (Markdown)。

    画像文件由 LLM 在分析流水线中生成，包含：
    - 投资哲学：价值/成长/趋势等偏好
    - 行业偏好：擅长和回避的板块
    - 风险偏好：激进/稳健/保守
    - 决策框架：PE/ROE/技术面 等维度的权重

    查找逻辑：
    1. 精确匹配 {完整用户名}*portrait.md
    2. 回退到模糊匹配（用户名第一段或前 3 个字符）
    3. 取最新的匹配文件（sorted 按文件名排序）

    Args:
        username: Twitter 用户名（如 "TJ_Research"）

    Returns:
        str: 画像的完整 Markdown 文本，找不到时返回 "[无画像] {username}"
    """
    candidates = sorted(PIPELINE_DIR.glob(f"{username}*portrait.md"))
    if not candidates:
        # 模糊匹配回退：取用户名非下划线部分或前 3 字符
        short = username.split("_")[0] if "_" in username else username[:3]
        candidates = sorted(PIPELINE_DIR.glob(f"{short}*portrait.md"))
    if not candidates:
        return f"[无画像] {username}"
    # 取最新的画像文件
    return candidates[-1].read_text(encoding="utf-8")


def load_tickers_by_sector(username: str, sector_hint: str) -> list[str]:
    """加载该分析师在目标板块中提及的股票代码列表。

    匹配逻辑（模糊搜索）：
    1. 将 sector_hint 拆分为关键词（如 "AI半导体" → ["ai半导体"] 或 "AI 半导体" → ["ai", "半导体"]）
    2. 在该分析师的 analyzed_cleaned.json 中搜索：
       - mentioned_sectors（LLM 标注的板块）
       - text（推文原文）
       - topic（LLM 标注的主题）
    3. 任一关键词命中即认为匹配
    4. 收集所有匹配推文中提到的股票代码（去重排序）

    Args:
        username: 分析师用户名
        sector_hint: 板块提示词（如 "AI半导体"、"消费电子"）

    Returns:
        list[str]: 匹配的股票代码列表（大写，已排序去重）
    """
    search_terms = [
        t.strip().lower()
        for t in sector_hint.replace("/", " ").split()
        if t.strip()
    ]
    result: set[str] = set()
    for fp in PIPELINE_DIR.glob("*_analyzed_cleaned.json"):
        u = fp.stem.split("_")[0]
        if u == "TJ":
            u = "TJ_Research"
        if u != username:
            continue
        for r in json.loads(fp.read_text(encoding="utf-8")):
            # 构建搜索文本（板块 + 推文 + 主题）
            sectors_str = " ".join(r.get("mentioned_sectors", [])).lower()
            text = (r.get("text", "") or "").lower()
            topic = (r.get("topic", "") or "").lower()
            haystack = f"{sectors_str} {topic} {text}"
            # 任一关键词命中
            if any(term in haystack for term in search_terms):
                for s in r.get("stock_details", []):
                    t = s.get("ticker", "").upper()
                    if t:
                        result.add(t)
    return sorted(result)


def load_stock_data(tickers: list[str]) -> list[dict]:
    """加载每只股票的基本面 + K线快照。

    数据来源：
    - 基本面: data/fundamental_cache.json（PE、ROE、营收增速）
    - K 线: data/prices.json（最新收盘价、30 日涨跌）

    注意：30 日涨跌的 window 取 -22（约一个月交易日），因为最近
    一个交易日可能还未收盘，使用前一个交易日的数据更可靠。

    Args:
        tickers: 股票代码列表

    Returns:
        list[dict]: 每只股票的数据字典，包含：
            - ticker: 股票代码
            - pe_ratio: 市盈率（可能为 None）
            - roe: 净资产收益率（可能为 None）
            - revenue_growth: 营收同比增长率（可能为 None）
            - latest_close: 最新收盘价（可能不存在）
            - chg_30d_pct: 30 日涨跌幅百分比（可能不存在）
    """
    fundamentals = {}
    if CACHE_PATH.exists():
        fundamentals = json.loads(CACHE_PATH.read_text(encoding="utf-8"))

    prices = {}
    if PRICES_PATH.exists():
        prices = json.loads(PRICES_PATH.read_text(encoding="utf-8"))

    result = []
    for t in tickers:
        row = {"ticker": t}

        # 加载基本面数据
        f = fundamentals.get(t, {})
        row["pe_ratio"] = f.get("pe_ratio")
        row["roe"] = f.get("roe")
        row["revenue_growth"] = f.get("revenue_growth_yoy")

        # 加载 K 线快照
        bars = prices.get(t, {}).get("results", [])
        if bars:
            # 最新收盘价（K 线数据按时间升序排列）
            latest = bars[-1]
            row["latest_close"] = latest["c"]
            # 30 日涨跌（约 22 个交易日）
            if len(bars) >= 22:
                row["close_30d_ago"] = bars[-22]["c"]
                row["chg_30d_pct"] = round(
                    (bars[-1]["c"] - bars[-22]["c"]) / bars[-22]["c"] * 100, 1
                )

        result.append(row)
    return result


def build_prompt(portrait: str, sector: str, stocks: list[dict]) -> str:
    """构建 LLM system prompt。

    Prompt 结构：
    [Role]   : 角色定义 + 分析师画像（取前 3000 字符）
    [Task]   : 任务描述 — 选 3-5 只股票 + rationale + 仓位 + 入场区间 + 止损线
    [Stock Pool]: Markdown 表格（PE, ROE, 营收增速, 最新价, 30日涨跌）
    [Output Format]: 严格 JSON 格式定义

    画像截断为 3000 字符是为控制 token 消耗（GPT-4 上下文窗口虽大，
    但 prompt 过长会增加成本且可能稀释关键信息）。

    Args:
        portrait: 分析师画像 Markdown
        sector: 目标板块名称
        stocks: 股票数据列表

    Returns:
        str: 组装完成的 LLM prompt 文本
    """
    # 构建股票数据表
    stock_table = "| Ticker | PE | ROE | 营收增速 | 最新价 | 30日涨跌 |\n"
    stock_table += "|--------|-----|-----|---------|--------|---------|\n"
    for s in stocks:
        pe = f"{s['pe_ratio']:.1f}" if s.get("pe_ratio") else "?"
        roe = f"{s['roe']:.1f}%" if s.get("roe") else "?"
        rg = f"{s['revenue_growth']*100:.0f}%" if s.get("revenue_growth") else "?"
        lc = f"${s['latest_close']:.0f}" if s.get("latest_close") else "?"
        chg = f"{s['chg_30d_pct']:+.1f}%" if s.get("chg_30d_pct") else "?"
        stock_table += f"| {s['ticker']} | {pe} | {roe} | {rg} | {lc} | {chg} |\n"

    # 组装完整 prompt
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
    """角色代入选股主流程。

    命令行参数：
    - sys.argv[1]: 分析师用户名（如 TJ_Research）
    - sys.argv[2]: 板块名称（如 "AI半导体"）

    输出：
    - data/role_pick_{username}_{sector}_prompt.txt: LLM prompt 文件
    """
    if len(sys.argv) < 3:
        print("用法: python scripts/role_picker.py <username> <sector>")
        print("例: python scripts/role_picker.py TJ_Research AI半导体")
        sys.exit(1)

    username = sys.argv[1]
    sector = sys.argv[2]

    # 加载分析师画像
    portrait = load_portrait(username)
    print(f"画像: {len(portrait)} 字")

    # 加载板块相关股票
    tickers = load_tickers_by_sector(username, sector)
    print(f"板块 {sector}: {len(tickers)} 只 {tickers[:10]}...")

    # 加载基本面 + K 线数据
    stocks = load_stock_data(tickers)
    print(f"数据完整: {sum(1 for s in stocks if s.get('pe_ratio'))}/{len(stocks)} 有PE")

    # 构建 LLM prompt
    prompt = build_prompt(portrait, sector, stocks)

    # 保存 prompt 文件
    out_path = Path(f"data/role_pick_{username}_{sector}_prompt.txt")
    out_path.write_text(prompt, encoding="utf-8")
    print(f"\nPrompts 已保存: {out_path}")
    print(f"   {len(prompt)} 字符，可直接粘贴到 LLM 对话中")


if __name__ == "__main__":
    main()
