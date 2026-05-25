"""#10 异常检测 — Phase 4

基于画像 baseline 的 KL 散度检测：当最近 5 条推文的 topic/stance 分布
显著偏离分析师历史基线时触发。

用法：python scripts/detect_anomaly.py
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

PIPELINE_DIR = Path("data/pipeline")
OUTPUT_DIR = Path("data/anomaly")
WINDOW = 5
KL_PERCENTILE = 95  # 用训练集 KL 的 95% 分位数做阈值，而非固定值


def kl_divergence(p: dict, q: dict) -> float:
    """KL(P||Q)，加平滑避免 log(0)。"""
    all_keys = set(p) | set(q)
    kl = 0.0
    for k in all_keys:
        pk = p.get(k, 0.001)
        qk = q.get(k, 0.001)
        kl += pk * math.log(pk / qk)
    return kl


def build_baseline(entries: list[dict]) -> dict[str, dict]:
    """从历史推文构建 topic 和 stance 的 baseline 分布。"""
    topic_count = Counter()
    stance_count = Counter()
    total = len(entries)
    for r in entries:
        topic_count[r.get("topic", "未知")] += 1
        stance_count[r.get("stance", "无明确方向")] += 1
    return {
        "topic": {k: v / total for k, v in topic_count.items()},
        "stance": {k: v / total for k, v in stance_count.items()},
    }


def sliding_window_kl(entries: list[dict], baseline: dict, threshold: float) -> list[dict]:
    """滑动窗口计算每条推文所在窗口的 KL 散度。"""
    results = []
    for i in range(len(entries) - WINDOW + 1):
        window = entries[i:i + WINDOW]
        w_topic = Counter()
        w_stance = Counter()
        for r in window:
            w_topic[r.get("topic", "未知")] += 1
            w_stance[r.get("stance", "无明确方向")] += 1
        w_dist = {
            "topic": {k: v / WINDOW for k, v in w_topic.items()},
            "stance": {k: v / WINDOW for k, v in w_stance.items()},
        }
        kl_topic = kl_divergence(w_dist["topic"], baseline["topic"])
        kl_stance = kl_divergence(w_dist["stance"], baseline["stance"])
        avg_kl = round((kl_topic + kl_stance) / 2, 4)
        results.append({
            "window_start": entries[i].get("created_at", "")[:10],
            "window_end": entries[i + WINDOW - 1].get("created_at", "")[:10],
            "kl_topic": round(kl_topic, 4),
            "kl_stance": round(kl_stance, 4),
            "kl_avg": avg_kl,
            "anomaly": avg_kl > threshold,
            "topics": [r.get("topic", "") for r in window],
            "stances": [r.get("stance", "") for r in window],
        })
    return results


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for fp in sorted(PIPELINE_DIR.glob("*_analyzed_cleaned.json")):
        tag = fp.stem  # dearbaibabybus_2025-01_analyzed_cleaned
        username = tag.split("_")[0]
        if username == "TJ":
            username = "TJ_Research"

        data = json.loads(fp.read_text(encoding="utf-8"))
        data.sort(key=lambda x: x.get("created_at", ""))

        if len(data) < WINDOW + 5:
            print(f"{username}: 推文不足 {WINDOW+5}，跳过")
            continue

        baseline = build_baseline(data[:len(data)//2])  # 前一半做基线
        # 用训练集自身 KL 的 95% 分位数做阈值
        train_kls = sliding_window_kl(data[:len(data)//2], baseline, 999)
        kl_values = sorted([r["kl_avg"] for r in train_kls])
        if kl_values:
            idx = int(len(kl_values) * KL_PERCENTILE / 100)
            threshold = kl_values[min(idx, len(kl_values) - 1)]
        else:
            threshold = 1.0
        print(f"{tag}: 基线 {len(data)//2} 条, KL阈值(95%ile)={threshold:.2f}")
        results = sliding_window_kl(data, baseline, threshold)

        # 统计异常
        anomalies = [r for r in results if r["anomaly"]]
        anomaly_pct = len(anomalies) / len(results) * 100 if results else 0

        print(f"\n🔍 {username}: {len(results)} 窗口, {len(anomalies)} 异常 ({anomaly_pct:.1f}%)")

        if anomalies:
            print("  最近 3 条异常:")
            for a in anomalies[-3:]:
                topics_str = ", ".join(a["topics"])
                stances_str = ", ".join(a["stances"])
                print(f"    {a['window_start']}~{a['window_end']} KL={a['kl_avg']:.2f}")
                print(f"      topics: {topics_str}")
                print(f"      stances: {stances_str}")

        out_path = OUTPUT_DIR / f"{tag}_anomaly.json"
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n已写入: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
