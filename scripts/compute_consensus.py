"""#4 多信号联动 — Phase 2 辅助模块

对每只股票，在 7 天滑动窗口内聚合所有分析师的信号分，
按各自 #2 准确率进行加权平均，同向 Bonus 加成，输出联动共识分。

核心思路：
- 不是孤立看单个分析师的单条信号，而是看"这只股票在最近一周内
  被多少人怎么看"——多人一致看多/看空比单人判断更有参考价值
- 如果窗口内所有分析师立场同向（全看多或全看空）且至少 2 人，
  共识分 × 1.2 加成（同向 Bonus）

输出：
- data/consensus/{TICKER}_consensus.json: 每只股票的逐日共识分序列

用法：
    python scripts/compute_consensus.py
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

PIPELINE_DIR = Path("data/pipeline")      # analyzed_cleaned 结果目录
ACCURACY_DIR = Path("data/accuracy")       # 分析师准确率统计目录
OUTPUT_DIR = Path("data/consensus")        # 共识输出目录
WINDOW_DAYS = 7                            # 聚合窗口：7 天


def load_accuracy() -> dict[str, float]:
    """加载各分析师的 30 日胜率，作为共识聚合的权重。

    胜率越高的分析师，在共识计算中的权重越大。
    无数据的分析师赋予 0.5 默认权重（均匀先验）。

    Returns:
        dict[str, float]: {username: win_rate}，范围 0.0-1.0
    """
    win_rates: dict[str, float] = {}
    for fp in ACCURACY_DIR.glob("*_accuracy.json"):
        username = fp.stem.replace("_accuracy", "")
        d = json.loads(fp.read_text(encoding="utf-8"))
        wr = d.get("returns_30d", {}).get("win_rate")
        if wr is not None:
            win_rates[username] = wr
    return win_rates


def date_key(d: str) -> str:
    """提取日期字符串的前 10 位（YYYY-MM-DD）。

    Args:
        d: 完整 ISO 日期时间字符串（如 "2024-03-15T10:30:00Z"）

    Returns:
        str: 日期部分 "2024-03-15"
    """
    return d[:10]


def main():
    """多信号联动共识计算主流程。

    算法步骤：
    1. 加载各分析师胜率作为共识权重
    2. 遍历所有 analyzed_cleaned.json，收集 {(ticker, date): [signals]}
    3. 对每只股票的每个日期，向前滑动 7 天窗口聚合信号：
       a. 加权平均：每个信号的权重 = 对应分析师的胜率
       b. 同向检测：窗口内所有 stance 是否同向（全看多 or 全看空）
       c. 同向 Bonus：全同向且 >= 2 人时，共识分 x 1.2
    4. 按股票输出逐日共识序列到 JSON 文件
    5. 控制台展示 TOP 10 共识分及多人覆盖统计
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    win_rates = load_accuracy()
    print(f"分析师权重: {win_rates}")

    # --- 步骤 2: 收集所有信号 ---
    # 数据结构: {(ticker, date_str): [{analyst, signal, weight, stance, tweet_id}]}
    signals: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for fp in sorted(PIPELINE_DIR.glob("*_analyzed_cleaned.json")):
        username = fp.stem.split("_")[0]
        if username == "TJ":
            username = "TJ_Research"
        wr = win_rates.get(username, 0.5)

        data = json.loads(fp.read_text(encoding="utf-8"))
        for r in data:
            # 跳过无信号或信号为 0 的记录
            ss = r.get("signal_score")
            if ss is None or ss == 0:
                continue

            created = date_key(r.get("created_at", ""))
            if not created:
                continue

            # 提取该推文提到的每只股票
            stocks = r.get("stock_details", [])
            for s in stocks:
                ticker = s.get("ticker", "").upper()
                if not ticker:
                    continue
                signals[(ticker, created)].append({
                    "analyst": username,
                    "signal": ss,               # #1 计算出的 0-100 信号分
                    "weight": wr,               # 该分析师的胜率（聚合权重）
                    "stance": r.get("stance", ""),
                    "tweet_id": r.get("tweet_id"),
                })

    print(f"信号对: {len(signals)} 个 (股票,日期)")

    # --- 步骤 3: 每只股票 7 天窗口聚合 ---
    consensus: dict[str, list[dict]] = defaultdict(list)

    for (ticker, date), entries in signals.items():
        # 在 7 天窗口内收集该股票的所有信号
        window_signals: list[dict] = []
        for (t2, d2), ents in signals.items():
            if t2 != ticker:
                continue  # 不同股票忽略

            # 日期筛选：d2 在 [date, date + WINDOW_DAYS] 范围内
            if d2 < date:
                continue
            if d2 > date:
                from datetime import datetime, timedelta
                try:
                    d0 = datetime.strptime(date, "%Y-%m-%d")
                    dc = datetime.strptime(d2, "%Y-%m-%d")
                    if (dc - d0).days > WINDOW_DAYS:
                        continue
                except Exception:
                    continue

            window_signals.extend(ents)

        if not window_signals:
            continue

        # --- 加权平均共识分 ---
        # 以分析师的 30 日胜率为权重（胜率高的人的意见更重要）
        total_w = sum(s["weight"] for s in window_signals)
        if total_w == 0:
            continue
        consensus_score = sum(
            s["signal"] * s["weight"] for s in window_signals
        ) / total_w

        # --- 同向 Bonus: 所有人 stance 一致时额外加分 ---
        # 统计窗口中涉及的分析师人数
        analysts_in_window = {s["analyst"] for s in window_signals}
        stances = [s["stance"] for s in window_signals]

        # 判断是否全部看多
        all_bullish = all(st in ("看多", "加仓", "持有") for st in stances)
        # 判断是否全部看空
        all_bearish = all(st in ("看空", "卖出", "减仓") for st in stances)

        # 同向 Bonus 条件：全部同向且至少 2 位分析师
        if (all_bullish or all_bearish) and len(analysts_in_window) >= 2:
            consensus_score = min(100, consensus_score * 1.2)  # 1.2x 加成，上限 100

        # 记录该日共识
        consensus[ticker].append({
            "date": date,
            "consensus_score": round(consensus_score, 1),
            "analysts_in_window": sorted(analysts_in_window),
            "signal_count": len(window_signals),
            "all_bullish": all_bullish,
            "all_bearish": all_bearish,
        })

    # --- 步骤 4: 输出到文件 ---
    daily_scores: dict[str, dict] = {}
    for ticker, entries in consensus.items():
        # 按日期排序
        entries.sort(key=lambda x: x["date"])

        # 写入 {TICKER}_consensus.json
        out_path = OUTPUT_DIR / f"{ticker}_consensus.json"
        out_path.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # 记录最新一天的共识分
        latest = entries[-1]
        daily_scores[ticker] = latest

    print(f"\n联动股票: {len(consensus)} 只")

    # --- 步骤 5: 控制台展示 ---
    # TOP 10 共识分排序
    sorted_scores = sorted(
        daily_scores.items(),
        key=lambda x: x[1]["consensus_score"],
        reverse=True,
    )
    print("\n最新共识 TOP 10:")
    for ticker, info in sorted_scores[:10]:
        # 标记多人同向 Bonus
        bonus = ""
        if info.get("all_bullish") and len(info.get("analysts_in_window", [])) >= 2:
            bonus = "多人看多"
        elif info.get("all_bearish") and len(info.get("analysts_in_window", [])) >= 2:
            bonus = "多人看空"

        people = ", ".join(info["analysts_in_window"])
        print(
            f"  {ticker}: {info['consensus_score']:.0f}分 "
            f"({info['signal_count']}条信号 {people}) {bonus}"
        )

    # 统计被多人覆盖的股票数 vs 单人覆盖数
    # 多人覆盖 = 某股票历史上至少被 2 位不同分析师提到
    multi = sum(
        1 for v in consensus.values()
        if len(set(
            a for e in v for a in e.get("analysts_in_window", [])
        )) >= 2
    )
    single = len(consensus) - multi
    print(f"\n多人覆盖: {multi} 只, 单人覆盖: {single} 只")


if __name__ == "__main__":
    main()
