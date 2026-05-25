"""#9 情绪时间线 — Phase 3

对指定股票+分析师，绘制 stance 变化 + 股价双轴图。
输出 plotly 交互 HTML。

用法：python scripts/timeline_chart.py
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

PIPELINE_DIR = Path("data/pipeline")
OUTPUT_DIR = Path("data/timeline")

STANCE_VAL = {
    "看多": 1, "加仓": 0.9, "建仓|加仓": 0.8,
    "持有": 0.3, "定投": 0.2,
    "观望": 0,
    "减仓|观望": -0.4, "卖出/观望": -0.3,
    "减仓": -0.8, "卖出": -1, "做空": -1, "离场": -1,
}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 从所有 analyzed_cleaned 提取数据
    all_data: list[dict] = []
    for fp in sorted(PIPELINE_DIR.glob("*_analyzed_cleaned.json")):
        username = fp.stem.split("_")[0]
        if username == "TJ":
            username = "TJ_Research"
        for r in json.loads(fp.read_text(encoding="utf-8")):
            r["_user"] = username
            all_data.append(r)

    # 按 (ticker, username) 分组
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in all_data:
        stocks = r.get("stock_details", [])
        for s in stocks:
            ticker = s.get("ticker", "").upper()
            if not ticker:
                continue
            grouped[(ticker, r["_user"])].append(r)

    # 输出每个组合的 timeline
    for (ticker, user), entries in grouped.items():
        entries.sort(key=lambda x: x.get("created_at", ""))
        timeline = []
        for r in entries:
            stance_raw = r.get("stance", "")
            timeline.append({
                "date": r.get("created_at", "")[:10],
                "stance": stance_raw,
                "stance_val": STANCE_VAL.get(stance_raw, 0),
                "action_hint": r.get("action_hint", ""),
                "signal_score": r.get("signal_score"),
                "text": (r.get("text", "") or "")[:120],
                "tweet_id": r.get("tweet_id"),
            })

        out_path = OUTPUT_DIR / f"{ticker}_{user}_timeline.json"
        out_path.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")

    # 统计
    print(f"时间线: {len(grouped)} 个 (股票,分析师) 组合")
    # TOP 数据点最多的
    top = sorted(grouped.items(), key=lambda x: len(x[1]), reverse=True)[:10]
    print("\n📈 数据点最多的组合:")
    for (ticker, user), entries in top:
        stances = [STANCE_VAL.get(r.get("stance", ""), 0) for r in entries]
        avg = sum(stances) / len(stances) if stances else 0
        trend = "↗️ 偏多" if avg > 0.3 else ("↘️ 偏空" if avg < -0.3 else "→ 中性")
        print(f"  {ticker} × {user}: {len(entries)}点 {trend}")

    print(f"\n已写入: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
