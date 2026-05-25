"""#4 多信号联动 — Phase 2 辅助模块

对每只股票，7天窗口内聚合所有分析师信号，按#2准确率加权，
同向bonus加成，输出联动共识分。

⚠️ 所有数字从 data/ 文件读取。

用法：python scripts/compute_consensus.py
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

PIPELINE_DIR = Path("data/pipeline")
ACCURACY_DIR = Path("data/accuracy")
OUTPUT_DIR = Path("data/consensus")
WINDOW_DAYS = 7


def load_accuracy() -> dict[str, float]:
    win_rates: dict[str, float] = {}
    for fp in ACCURACY_DIR.glob("*_accuracy.json"):
        username = fp.stem.replace("_accuracy", "")
        d = json.loads(fp.read_text(encoding="utf-8"))
        wr = d.get("returns_30d", {}).get("win_rate")
        if wr is not None:
            win_rates[username] = wr
    # 默认 0.5
    return win_rates


def date_key(d: str) -> str:
    return d[:10]


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    win_rates = load_accuracy()
    print(f"分析师权重: {win_rates}")

    # 收集所有信号：{(ticker, date): [{analyst, signal_score, stance}]}
    signals: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for fp in sorted(PIPELINE_DIR.glob("*_analyzed_cleaned.json")):
        username = fp.stem.split("_")[0]
        if username == "TJ":
            username = "TJ_Research"
        wr = win_rates.get(username, 0.5)
        data = json.loads(fp.read_text(encoding="utf-8"))
        for r in data:
            ss = r.get("signal_score")
            if ss is None or ss == 0:
                continue
            created = date_key(r.get("created_at", ""))
            if not created:
                continue
            stocks = r.get("stock_details", [])
            for s in stocks:
                ticker = s.get("ticker", "").upper()
                if not ticker:
                    continue
                signals[(ticker, created)].append({
                    "analyst": username,
                    "signal": ss,
                    "weight": wr,
                    "stance": r.get("stance", ""),
                    "tweet_id": r.get("tweet_id"),
                })

    print(f"信号对: {len(signals)} 个 (股票,日期)")

    # 聚合：每只股票 7 天窗口
    consensus: dict[str, list[dict]] = defaultdict(list)
    all_dates = sorted({d for _, d in signals})

    for (ticker, date), entries in signals.items():
        # 统计窗口内的所有信号
        window_signals = []
        for (t2, d2), ents in signals.items():
            if t2 != ticker:
                continue
            if d2 < date:
                continue
            if d2 > date:
                from datetime import datetime, timedelta
                try:
                    d0 = datetime.strptime(date, "%Y-%m-%d")
                    dc = datetime.strptime(d2, "%Y-%m-%d")
                    if (dc - d0).days > WINDOW_DAYS:
                        continue
                except:
                    continue
            window_signals.extend(ents)

        if not window_signals:
            continue

        # 加权平均
        total_w = sum(s["weight"] for s in window_signals)
        if total_w == 0:
            continue
        consensus_score = sum(s["signal"] * s["weight"] for s in window_signals) / total_w

        # 同向 bonus：所有人 stance 同向（全看多或全看空）
        analysts_in_window = {s["analyst"] for s in window_signals}
        stances = [s["stance"] for s in window_signals]
        all_bullish = all(st in ("看多", "加仓", "持有") for st in stances)
        all_bearish = all(st in ("看空", "卖出", "减仓") for st in stances)
        if (all_bullish or all_bearish) and len(analysts_in_window) >= 2:
            consensus_score = min(100, consensus_score * 1.2)

        consensus[ticker].append({
            "date": date,
            "consensus_score": round(consensus_score, 1),
            "analysts_in_window": sorted(analysts_in_window),
            "signal_count": len(window_signals),
            "all_bullish": all_bullish,
            "all_bearish": all_bearish,
        })

    # 输出
    daily_scores: dict[str, dict] = {}
    for ticker, entries in consensus.items():
        # 按日期排序取最新
        entries.sort(key=lambda x: x["date"])
        out_path = OUTPUT_DIR / f"{ticker}_consensus.json"
        out_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

        # 最新一条
        latest = entries[-1]
        daily_scores[ticker] = latest

    print(f"\n联动股票: {len(consensus)} 只")

    # TOP 10 共识分
    sorted_scores = sorted(daily_scores.items(), key=lambda x: x[1]["consensus_score"], reverse=True)
    print("\n📊 最新共识 TOP 10:")
    for ticker, info in sorted_scores[:10]:
        bonus = "🔥 双人同向" if info.get("all_bullish") and len(info.get("analysts_in_window",[])) >= 2 else ""
        bonus = bonus or ("🔥 双人同向空" if info.get("all_bearish") and len(info.get("analysts_in_window",[])) >= 2 else "")
        people = ", ".join(info["analysts_in_window"] if len(info["analysts_in_window"]) >= 2 else [info["analysts_in_window"][0] + "(单)"])
        print(f"  {ticker}: {info['consensus_score']:.0f}分 ({info['signal_count']}条信号 {people}) {bonus}")

    # 统计被多人覆盖的
    multi = sum(1 for v in consensus.values() if len(set(e.get("analysts_in_window", [""])[0] for e in v)) >= 2)
    single = len(consensus) - multi
    print(f"\n多人覆盖: {multi} 只, 单人覆盖: {single} 只")


if __name__ == "__main__":
    main()
