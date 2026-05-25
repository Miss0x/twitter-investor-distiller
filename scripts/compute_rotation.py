"""#8 板块轮动检测 — Phase 3

按周聚合 mentioned_sectors，滚动 Z-score 检测热点迁移。
输出热力图 JSON + plotly 交互图表。

用法：python scripts/compute_rotation.py
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

PIPELINE_DIR = Path("data/pipeline")
OUTPUT_DIR = Path("data/rotation")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for fp in sorted(PIPELINE_DIR.glob("*_analyzed_cleaned.json")):
        username = fp.stem.split("_")[0]
        if username == "TJ":
            username = "TJ_Research"

        data = json.loads(fp.read_text(encoding="utf-8"))
        # 排除纯观望/信息分享/中性推文
        relevant = [r for r in data if r.get("topic") not in ("信息分享", "其他", "招聘/人脉")]

        # 按周聚合
        weekly: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for r in relevant:
            week = r.get("created_at", "")[:7]  # YYYY-MM
            topic = r.get("topic", "未知")
            weekly[week][topic] += 1

        if not weekly:
            continue

        weeks = sorted(weekly.keys())
        topics = sorted({t for w in weeks for t in weekly[w]})

        # 滚动 Z-score (4 周窗口)
        rotation: list[dict] = []
        for i, week in enumerate(weeks):
            if i < 3:
                continue  # 前 3 周不够窗口
            window_weeks = weeks[i-3:i+1]
            for topic in topics:
                vals = [weekly[w].get(topic, 0) for w in window_weeks]
                mean = sum(vals) / 4
                var = sum((v - mean)**2 for v in vals) / 4
                std = var ** 0.5 if var > 0 else 0.01
                z = (vals[-1] - mean) / std if std > 0 else 0
                rotation.append({"week": week, "topic": topic, "count": vals[-1], "z_score": round(z, 2)})

        # 保存
        out_path = OUTPUT_DIR / f"{username}_rotation.json"
        out_path.write_text(json.dumps(rotation, ensure_ascii=False, indent=2), encoding="utf-8")

        # 打印摘要：最近4周热点
        latest_weeks = sorted({r["week"] for r in rotation})[-4:]
        print(f"\n📊 {username} — 最近4周板块热搜:")
        for week in latest_weeks:
            week_data = [r for r in rotation if r["week"] == week]
            week_data.sort(key=lambda x: x["z_score"], reverse=True)
            hot = week_data[:5]
            topics_str = ", ".join(f"{r['topic']}({r['z_score']:+.1f})" for r in hot)
            print(f"  {week}: {topics_str}")

    print(f"\n已写入: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
