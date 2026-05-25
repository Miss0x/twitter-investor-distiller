"""#1 信号量化 — Phase 2 核心模块

从 analyzed_cleaned 的 stance/confidence + #2 准确率贝叶斯校准 + K线共振，
输出 0-100 信号分，写入 analyzed_cleaned 的 signal_score 字段。

⚠️ 所有数字从 data/ 文件读取，绝无编造。

用法：python scripts/compute_signals.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

PIPELINE_DIR = Path("data/pipeline")
PRICES_PATH = Path("data/prices.json")
ACCURACY_DIR = Path("data/accuracy")

# 因子权重
W_STANCE = 0.40
W_CONFIDENCE = 0.35
W_RESONANCE = 0.15
W_MULTI_STOCK = 0.10

# stance 数值化映射
STANCE_MAP = {
    "看多": 1.0, "加仓": 0.9, "建仓|加仓": 0.8,
    "持有": 0.3, "定投": 0.2,
    "观望": 0.0, "卖出/观望": -0.3, "减仓|观望": -0.4,
    "无明确方向": 0.0, "中性": 0.0,
    "减仓": -0.8, "卖出": -1.0, "做空": -1.0, "离场": -1.0,
}

# confidence 数值化
CONF_MAP = {"high": 1.0, "medium": 0.5, "low": 0.2}


def load_accuracy() -> dict[str, float]:
    """加载每个分析师的 30 日胜率，用于贝叶斯校准。"""
    win_rates: dict[str, float] = {}
    for fp in ACCURACY_DIR.glob("*_accuracy.json"):
        username = fp.stem.replace("_accuracy", "")
        d = json.loads(fp.read_text(encoding="utf-8"))
        wr = d.get("returns_30d", {}).get("win_rate")
        if wr is not None:
            win_rates[username] = wr
    return win_rates


def load_prices() -> dict:
    raw = json.loads(PRICES_PATH.read_text(encoding="utf-8"))
    prices = {}
    for ticker, snap in raw.items():
        if isinstance(snap, dict) and "results" in snap:
            prices[ticker.upper()] = snap["results"]
    return prices


def price_on(results: list[dict], target_date: str) -> tuple[str, float] | None:
    """返回 >= target_date 的第一个交易日 (date, close)。"""
    from datetime import datetime, timezone
    best = None
    for bar in results:
        t_ms = bar.get("t", 0)
        if t_ms == 0:
            continue
        d = datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        if d < target_date:
            continue
        if best is None or d < best[0]:
            best = (d, bar["c"])
    return best


def compute_sma(results: list[dict], end_date_str: str, window: int = 20) -> float | None:
    """计算 end_date 前 window 个交易日的 SMA。"""
    from datetime import datetime, timezone
    closes: list[float] = []
    for bar in results:
        d = datetime.fromtimestamp(bar["t"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        if d >= end_date_str:
            break
        closes.append(bar["c"])
    if len(closes) < window:
        return None
    return sum(closes[-window:]) / window


def compute_sma_std(results: list[dict], end_date_str: str, window: int = 20) -> float | None:
    """计算 end_date 前 window 个交易日收盘价的标准差。"""
    from datetime import datetime, timezone
    closes: list[float] = []
    for bar in results:
        d = datetime.fromtimestamp(bar["t"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        if d >= end_date_str:
            break
        closes.append(bar["c"])
    if len(closes) < window:
        return None
    mean = sum(closes[-window:]) / window
    var = sum((c - mean) ** 2 for c in closes[-window:]) / window
    return math.sqrt(var)


def momentum_z(results: list[dict], entry_date: str, window: int = 20) -> float:
    """K 线共振因子：(close - SMA20) / std20，钳位到 [-2, 2]。"""
    entry = price_on(results, entry_date)
    if entry is None:
        return 0.0
    close = entry[1]
    sma20 = compute_sma(results, entry[0], window)
    std20 = compute_sma_std(results, entry[0], window)
    if sma20 is None or std20 is None or std20 == 0:
        return 0.0
    z = (close - sma20) / std20
    return max(-2.0, min(2.0, z))


def bayesian_calibrate(raw_confidence: float, analyst_win_rate: float | None) -> float:
    """贝叶斯校准：raw_confidence × 分析师的 30日胜率（若无则用 0.5 作为无信息先验）。"""
    prior = analyst_win_rate if analyst_win_rate is not None else 0.5
    return raw_confidence * prior


def compute_score(stance_raw, conf_calibrated, resonance, stock_count, conf_raw):
    """计算 0-100 信号分。"""
    stance_score = stance_raw * 100  # -100 to +100
    conf_score = conf_calibrated * 100  # 0 to 100
    resonance_score = resonance * 100  # -200 to +200

    # 多股票加分：提到的股票数量越多，信号越分散但覆盖面更广
    multi_bonus = min(stock_count, 3) / 3 * 100  # 1只=33, 3只以上=100

    signal = (W_STANCE * stance_score
              + W_CONFIDENCE * conf_score
              + W_RESONANCE * resonance_score
              + W_MULTI_STOCK * multi_bonus)

    # 钳位 0-100
    signal = max(0.0, min(100.0, signal))

    components = {
        "stance_raw": round(stance_raw, 2),
        "stance_score": round(stance_score, 0),
        "confidence_raw": round(conf_raw, 2),
        "confidence_calibrated": round(conf_calibrated, 3),
        "confidence_score": round(conf_score, 0),
        "resonance_z": round(resonance, 2),
        "resonance_score": round(resonance_score, 0),
        "multi_stock_score": round(multi_bonus, 0),
    }
    return round(signal, 1), components


def main():
    win_rates = load_accuracy()
    prices = load_prices()
    print(f"分析师胜率: {win_rates}")
    print(f"股价: {len(prices)} 只")

    total = 0
    scored = 0

    for fp in sorted(PIPELINE_DIR.glob("*_analyzed_cleaned.json")):
        username = fp.stem.split("_")[0]
        if username == "TJ":
            username = "TJ_Research"

        wr = win_rates.get(username)
        data = json.loads(fp.read_text(encoding="utf-8"))
        modified = False

        for r in data:
            total += 1
            stance_raw = r.get("stance", "无明确方向")
            confidence_raw = r.get("confidence", "low")
            created = r.get("created_at", "")[:10]
            stocks = r.get("stock_details", [])

            # 数值化
            stance_val = STANCE_MAP.get(stance_raw, 0.0)
            conf_val = CONF_MAP.get(confidence_raw, 0.2)

            # 贝叶斯校准
            conf_cal = bayesian_calibrate(conf_val, wr)

            # K 线共振：取第一条股票的共振值
            resonance = 0.0
            ticker = ""
            if stocks and created:
                ticker = stocks[0].get("ticker", "").upper()
                bars = prices.get(ticker, [])
                if bars:
                    resonance = momentum_z(bars, created)

            signal, components = compute_score(stance_val, conf_cal, resonance, len(stocks), conf_val)
            r["signal_score"] = signal
            r["signal_components"] = components

            if signal > 0 or stance_val != 0:
                scored += 1
            modified = True

        if modified:
            fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n处理: {total} 条, 有信号: {scored} 条 ({scored/total*100:.0f}%)")

    # 展示几条高/低信号样例
    all_scored = []
    for fp in PIPELINE_DIR.glob("*_analyzed_cleaned.json"):
        for r in json.loads(fp.read_text(encoding="utf-8")):
            if "signal_score" in r:
                all_scored.append(r)
    all_scored.sort(key=lambda x: x["signal_score"], reverse=True)

    print(f"\n🔝 TOP 5 信号:")
    for r in all_scored[:5]:
        sc = r["signal_components"]
        print(f"  [{r['signal_score']:.0f}] {r.get('action_hint','?')} {r.get('stance','?')} "
              f"| {r.get('text','')[:50]}...")
        print(f"      stance={sc['stance_score']:.0f} conf={sc['confidence_score']:.0f} "
              f"resonance={sc['resonance_score']:.0f} multi={sc['multi_stock_score']:.0f}")

    # 文件覆盖确认
    print(f"\n已写入: {len(list(PIPELINE_DIR.glob('*_analyzed_cleaned.json')))} 个文件")


if __name__ == "__main__":
    main()
