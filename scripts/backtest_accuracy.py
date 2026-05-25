"""#2 准确率回溯 — Phase 1 核心模块

从 analyzed_cleaned 提取买入/加仓信号，匹配股价做事件研究。
输出每人胜率 / 超额收益 / 夏普比率 / 按股票按月分组。

用法：python scripts/backtest_accuracy.py
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

PRICES_PATH = Path("data/prices.json")
PIPELINE_DIR = Path("data/pipeline")
OUTPUT_DIR = Path("data/accuracy")
HORIZONS = [("7d", 7), ("30d", 30)]


def load_prices() -> dict:
    raw = json.loads(PRICES_PATH.read_text(encoding="utf-8"))
    prices = {}
    for ticker, snap in raw.items():
        if not isinstance(snap, dict) or "results" not in snap:
            continue
        prices[ticker.upper()] = snap["results"]
    return prices


def price_on(results: list[dict], target_date: str) -> float | None:
    """返回 target_date 或其后最近交易日的收盘价。"""
    best = None
    for bar in results:
        t_ms = bar.get("t", 0)
        if t_ms == 0:
            continue
        # Polygon 返回毫秒时间戳
        from datetime import datetime, timezone
        bar_date = datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        if bar_date < target_date:
            continue
        if best is None or bar_date < best[0]:
            best = (bar_date, bar["c"])
    return best[1] if best else None


def returns_from(prices: dict, ticker: str, entry_date: str, days: int) -> float | None:
    """return (price_t - price_0) / price_0，无数据返回 None"""
    bars = prices.get(ticker.upper())
    if not bars:
        return None
    p0 = price_on(bars, entry_date)
    if p0 is None or p0 == 0:
        return None
    # target date = entry_date + days
    from datetime import datetime, timedelta
    target_dt = datetime.strptime(entry_date, "%Y-%m-%d") + timedelta(days=days)
    target = target_dt.strftime("%Y-%m-%d")
    pN = price_on(bars, target)
    if pN is None:
        return None
    return (pN - p0) / p0


def collect_signals() -> dict[str, list[dict]]:
    """读取所有 analyzed_cleaned，提取可回测信号。"""
    all_signals: dict[str, list[dict]] = defaultdict(list)
    for fp in sorted(PIPELINE_DIR.glob("*_analyzed_cleaned.json")):
        username = fp.stem.split("_")[0]
        # TJ_Research → 统一为 TJ（合并多用户视图）
        # dearbaibabybus 保持原名
        if username == "TJ":
            username = "TJ_Research"
        data = json.loads(fp.read_text(encoding="utf-8"))
        for r in data:
            ah = r.get("action_hint", "")
            stocks = r.get("stock_details") or []
            created = r.get("created_at", "")[:10]
            # 只取买入/加仓 + 有股票 + 有日期
            if ah in ("买入", "加仓") and stocks and created:
                all_signals[username].append({
                    "date": created,
                    "stocks": [s["ticker"].upper() for s in stocks if s.get("ticker")],
                    "text": (r.get("text") or "")[:80],
                    "tweet_id": r.get("tweet_id"),
                })
    return all_signals


def collect_signals_with_topic() -> dict[str, list[dict]]:
    """同 collect_signals，但附带 topic 字段用于按板块分组。"""
    all_signals: dict[str, list[dict]] = defaultdict(list)
    for fp in sorted(PIPELINE_DIR.glob("*_analyzed_cleaned.json")):
        username = fp.stem.split("_")[0]
        if username == "TJ":
            username = "TJ_Research"
        data = json.loads(fp.read_text(encoding="utf-8"))
        for r in data:
            ah = r.get("action_hint", "")
            stocks = r.get("stock_details") or []
            created = r.get("created_at", "")[:10]
            if ah in ("买入", "加仓") and stocks and created:
                all_signals[username].append({
                    "date": created,
                    "stocks": [s["ticker"].upper() for s in stocks if s.get("ticker")],
                    "text": (r.get("text") or "")[:80],
                    "tweet_id": r.get("tweet_id"),
                    "topic": r.get("topic", "未知"),
                })
    return all_signals


def compute_stats(returns_list: list[float]) -> dict:
    if not returns_list:
        return {"count": 0, "win_rate": None, "avg_return": None, "sharpe": None, "max_return": None, "min_return": None}
    n = len(returns_list)
    wins = sum(1 for r in returns_list if r > 0)
    avg = sum(returns_list) / n
    var = sum((r - avg) ** 2 for r in returns_list) / n if n > 1 else 0
    std = math.sqrt(var)
    sharpe = (avg / std) * math.sqrt(252 / 30) if std > 0 else 0  # 年化
    return {
        "count": n,
        "win_rate": round(wins / n, 4),
        "avg_return": round(avg, 4),
        "sharpe": round(sharpe, 2),
        "max_return": round(max(returns_list), 4),
        "min_return": round(min(returns_list), 4),
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_prices()
    print(f"加载股价：{len(prices)} 只")
    signals = collect_signals_with_topic()
    for user, sigs in signals.items():
        print(f"{user}: {len(sigs)} 条买入/加仓信号")

    # 按分析师分别计算
    for username, sigs in signals.items():
        all_returns_7d = []
        all_returns_30d = []
        by_stock = defaultdict(list)
        by_topic = defaultdict(list)
        by_month = defaultdict(list)

        for sig in sigs:
            for ticker in sig["stocks"]:
                for label, days in HORIZONS:
                    ret = returns_from(prices, ticker, sig["date"], days)
                    if ret is None:
                        continue
                    if days == 7:
                        all_returns_7d.append(ret)
                    else:
                        all_returns_30d.append(ret)
                    by_stock[ticker].append({label: ret, "date": sig["date"]})
                # 按 topic 分组（只用 30d）
                topic = sig.get("topic", "未知")
                if sig["stocks"]:
                    by_topic[topic].append(sig)
                # 按月分组（只用 30d）
                month = sig["date"][:7]
                if sig["stocks"]:
                    by_month[month].append(sig)

        result = {
            "username": username,
            "total_signals": len(sigs),
            "returns_7d": compute_stats(all_returns_7d),
            "returns_30d": compute_stats(all_returns_30d),
            "by_stock": {},
            "by_topic": {},
            "by_month": {},
        }

        for ticker, entries in by_stock.items():
            r7d = [e["7d"] for e in entries if "7d" in e]
            r30d = [e["30d"] for e in entries if "30d" in e]
            result["by_stock"][ticker] = {
                "signals": len(entries),
                "returns_7d": compute_stats(r7d),
                "returns_30d": compute_stats(r30d),
            }

        # by_topic：按 topic 分组，计算每个 topic 的 30 日收益
        topic_returns: dict[str, list[float]] = defaultdict(list)
        for sig in sigs:
            topic = sig.get("topic", "未知")
            for ticker in sig["stocks"]:
                ret = returns_from(prices, ticker, sig["date"], 30)
                if ret is not None:
                    topic_returns[topic].append(ret)
        for topic, rets in topic_returns.items():
            result["by_topic"][topic] = compute_stats(rets)

        for month, month_sigs in by_month.items():
            result["by_month"][month] = {
                "signals": len(month_sigs),
            }

        out_path = OUTPUT_DIR / f"{username}_accuracy.json"
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n{'='*50}")
        print(f"📊 {username}")
        print(f"  买入/加仓信号: {result['total_signals']} 条")
        r7 = result["returns_7d"]
        r30 = result["returns_30d"]
        print(f"  7日胜率: {r7['win_rate']*100:.1f}% (n={r7['count']})  均收益: {r7['avg_return']*100:+.2f}%")
        print(f"  30日胜率: {r30['win_rate']*100:.1f}% (n={r30['count']}) 均收益: {r30['avg_return']*100:+.2f}%  夏普: {r30['sharpe']}")
        print(f"  最多赚: {r30['max_return']*100:+.1f}%  最惨亏: {r30['min_return']*100:+.1f}%")
        print(f"\n  按板块 TOP 5 (30日胜率):")
        top_topic = sorted(result["by_topic"].items(),
                           key=lambda x: x[1]["avg_return"] or -99, reverse=True)[:5]
        for topic, stats in top_topic:
            if stats["count"]:
                print(f"    {topic}: {stats['win_rate']*100:.0f}% ({stats['count']}次) +{stats['avg_return']*100:.1f}%")
        print(f"\n  按股票 TOP 5 (30日胜率):")
        top = sorted(result["by_stock"].items(),
                     key=lambda x: x[1]["returns_30d"]["avg_return"] or -99, reverse=True)[:5]
        for t, s in top:
            r30s = s["returns_30d"]
            if r30s["count"]:
                print(f"    {t}: {r30s['win_rate']*100:.0f}% ({r30s['count']}次) +{r30s['avg_return']*100:.1f}%")
        print(f"  → 已写入 {out_path}")


if __name__ == "__main__":
    main()
