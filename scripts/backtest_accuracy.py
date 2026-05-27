"""#2 准确率回溯 — Phase 1 核心模块

从 analyzed_cleaned 提取买入/加仓信号，匹配股价做事件研究 (Event Study)，
输出每人胜率 / 超额收益 / 夏普比率，按股票按月分组。

事件研究方法：
1. 事件日 = 推文发布日期（买入/加仓信号）
2. 事件窗口：7 日、30 日（HORIZONS 配置）
3. 持有期收益 = (PT - P0) / P0，其中 P0 = 事件日收盘价，PT = 事件日+T 日收盘价
4. 对比基准：无（绝对收益），可扩展为相对 SPY/QQQ 的超额收益

所有数字均从 data/prices.json 和 data/pipeline/*_analyzed_cleaned.json 直接读取。

用法：
    python scripts/backtest_accuracy.py
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

PRICES_PATH = Path("data/prices.json")          # Polygon 股价数据
PIPELINE_DIR = Path("data/pipeline")             # analyzed_cleaned 结果
OUTPUT_DIR = Path("data/accuracy")               # 准确率统计输出
HORIZONS = [("7d", 7), ("30d", 30)]              # 回测时间窗口


def load_prices() -> dict:
    """加载 Polygon 股价快照。

    从 data/prices.json 读取，只保留包含 "results" 字段的有效条目。
    ticker 统一转大写以确保匹配一致性。

    Returns:
        dict: {ticker: [{t, o, h, l, c, v, ...}, ...]}
    """
    raw = json.loads(PRICES_PATH.read_text(encoding="utf-8"))
    prices = {}
    for ticker, snap in raw.items():
        if not isinstance(snap, dict) or "results" not in snap:
            continue
        prices[ticker.upper()] = snap["results"]
    return prices


def price_on(results: list[dict], target_date: str) -> float | None:
    """返回 target_date 或其后最近交易日的收盘价。

    用途：事件研究的 P0（买入价）和 PT（窗口结束价）。
    如果 target_date 是非交易日，则使用下一个交易日的价格。

    Polygon 数据格式：t 字段为毫秒级 Unix 时间戳，c 为收盘价。

    Args:
        results: 某股票的 K 线数据列表（按时间升序排列）
        target_date: 目标日期，格式 "YYYY-MM-DD"

    Returns:
        float | None: 收盘价，找不到匹配数据返回 None
    """
    best = None
    for bar in results:
        t_ms = bar.get("t", 0)
        if t_ms == 0:
            continue
        from datetime import datetime, timezone
        bar_date = datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%d"
        )
        if bar_date < target_date:
            continue
        # 记录 >= target_date 的最早日期的收盘价
        if best is None or bar_date < best[0]:
            best = (bar_date, bar["c"])
    return best[1] if best else None


def returns_from(prices: dict, ticker: str, entry_date: str, days: int) -> float | None:
    """计算事件研究的持有期收益率。

    公式：(P{entry_date + days} - P{entry_date}) / P{entry_date}

    步骤：
    1. 获取 entry_date 的收盘价 P0
    2. 计算目标日期 = entry_date + days
    3. 获取目标日期的收盘价 PT
    4. 返回 (PT - P0) / P0

    Args:
        prices: 股票价格字典 {ticker: [{c, t, ...}]}
        ticker: 股票代码
        entry_date: 事件日（推文发布日期），格式 "YYYY-MM-DD"
        days: 持有天数

    Returns:
        float | None: 持有期收益率（小数），缺少任一端数据返回 None
    """
    bars = prices.get(ticker.upper())
    if not bars:
        return None

    # 获取事件日收盘价 (P0)
    p0 = price_on(bars, entry_date)
    if p0 is None or p0 == 0:
        return None

    # 计算目标日期并获取 PT
    from datetime import datetime, timedelta
    target_dt = datetime.strptime(entry_date, "%Y-%m-%d") + timedelta(days=days)
    target = target_dt.strftime("%Y-%m-%d")
    pN = price_on(bars, target)
    if pN is None:
        return None

    return (pN - p0) / p0


def collect_signals() -> dict[str, list[dict]]:
    """读取所有 analyzed_cleaned 文件，提取可回测的买入/加仓信号。

    只提取 action_hint 为"买入"或"加仓"的记录（看多方向的明确操作），
    且必须包含股票代码和日期信息。

    Returns:
        dict[str, list[dict]]: {username: [{date, stocks: [ticker], text, tweet_id}]}
    """
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
            # 筛选条件：买入/加仓 + 有明确股票 + 有日期
            if ah in ("买入", "加仓") and stocks and created:
                all_signals[username].append({
                    "date": created,
                    "stocks": [s["ticker"].upper() for s in stocks if s.get("ticker")],
                    "text": (r.get("text") or "")[:80],  # 截断长文本
                    "tweet_id": r.get("tweet_id"),
                })
    return all_signals


def collect_signals_with_topic() -> dict[str, list[dict]]:
    """同 collect_signals，但额外附带 topic 字段用于按板块分组。

    板块分组比按股票分组更宏观，可评估分析师在不同领域的擅长程度。
    例如：某分析师可能在"AI半导体"板块胜率 80%，但在"消费"板块只有 30%。

    Returns:
        dict[str, list[dict]]: 同上，但每条记录额外包含 topic 字段
    """
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
    """计算一组收益率序列的描述性统计量。

    统计指标：
    - count: 样本数
    - win_rate: 胜率（收益 > 0 的比例）
    - avg_return: 平均收益率
    - sharpe: 年化夏普比率（基于 30 日持有期，年化因子 sqrt(252/30)）
    - max_return: 最大单次收益
    - min_return: 最大单次亏损

    Args:
        returns_list: 收益率序列（小数形式，如 0.05 表示 5%）

    Returns:
        dict: 统计量字典，空列表返回 count=0，各指标为 None
    """
    if not returns_list:
        return {
            "count": 0,
            "win_rate": None,
            "avg_return": None,
            "sharpe": None,
            "max_return": None,
            "min_return": None,
        }
    n = len(returns_list)
    wins = sum(1 for r in returns_list if r > 0)        # 正收益次数
    avg = sum(returns_list) / n                          # 算术平均
    var = sum((r - avg) ** 2 for r in returns_list) / n if n > 1 else 0  # 总体方差
    std = math.sqrt(var)
    # 年化夏普：avg/std × sqrt(252/30)
    # 假设 30 日持有期，年化因子 ≈ sqrt(252/30) ≈ 2.90
    sharpe = (avg / std) * math.sqrt(252 / 30) if std > 0 else 0
    return {
        "count": n,
        "win_rate": round(wins / n, 4),
        "avg_return": round(avg, 4),
        "sharpe": round(sharpe, 2),
        "max_return": round(max(returns_list), 4),
        "min_return": round(min(returns_list), 4),
    }


def main():
    """准确率回溯主流程。

    执行步骤：
    1. 加载全部股价数据
    2. 收集所有分析师的买入/加仓信号（附 topic 用于板块分组）
    3. 对每位分析师：
       a. 逐信号计算 7 日和 30 日持有期收益率
       b. 按股票分组统计：哪些股票上的推荐更赚钱
       c. 按板块分组统计：哪个板块的分析更准确
       d. 按月分组：跟踪策略在时间上的稳定性
       e. 计算胜率、平均收益、夏普比率等综合指标
    4. 输出到 data/accuracy/{username}_accuracy.json
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_prices()
    print(f"加载股价：{len(prices)} 只")

    # 使用带 topic 的版本以支持板块分组
    signals = collect_signals_with_topic()
    for user, sigs in signals.items():
        print(f"{user}: {len(sigs)} 条买入/加仓信号")

    # 按分析师分别计算
    for username, sigs in signals.items():
        all_returns_7d: list[float] = []
        all_returns_30d: list[float] = []
        by_stock = defaultdict(list)     # {ticker: [{date, 7d: ret, 30d: ret}]}
        by_topic = defaultdict(list)     # {topic: [sig]}
        by_month = defaultdict(list)     # {"YYYY-MM": [sig]}

        # 逐信号逐股票计算持有期收益
        for sig in sigs:
            for ticker in sig["stocks"]:
                # 对每条信号-股票对，计算两个窗口的收益
                for label, days in HORIZONS:
                    ret = returns_from(prices, ticker, sig["date"], days)
                    if ret is None:
                        continue
                    if days == 7:
                        all_returns_7d.append(ret)
                    else:
                        all_returns_30d.append(ret)
                    by_stock[ticker].append({label: ret, "date": sig["date"]})

                # 按 topic 分组
                topic = sig.get("topic", "未知")
                if sig["stocks"]:
                    by_topic[topic].append(sig)

                # 按月分组
                month = sig["date"][:7]  # "YYYY-MM"
                if sig["stocks"]:
                    by_month[month].append(sig)

        # 组装结果
        result = {
            "username": username,
            "total_signals": len(sigs),
            "returns_7d": compute_stats(all_returns_7d),
            "returns_30d": compute_stats(all_returns_30d),
            "by_stock": {},
            "by_topic": {},
            "by_month": {},
        }

        # 按股票明细
        for ticker, entries in by_stock.items():
            r7d = [e["7d"] for e in entries if "7d" in e]
            r30d = [e["30d"] for e in entries if "30d" in e]
            result["by_stock"][ticker] = {
                "signals": len(entries),
                "returns_7d": compute_stats(r7d),
                "returns_30d": compute_stats(r30d),
            }

        # 按 topic（板块）分组：计算每个板块的 30 日收益
        topic_returns: dict[str, list[float]] = defaultdict(list)
        for sig in sigs:
            topic = sig.get("topic", "未知")
            for ticker in sig["stocks"]:
                ret = returns_from(prices, ticker, sig["date"], 30)
                if ret is not None:
                    topic_returns[topic].append(ret)
        for topic, rets in topic_returns.items():
            result["by_topic"][topic] = compute_stats(rets)

        # 按月分组
        for month, month_sigs in by_month.items():
            result["by_month"][month] = {
                "signals": len(month_sigs),
            }

        # 写入 JSON 文件
        out_path = OUTPUT_DIR / f"{username}_accuracy.json"
        out_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # ---- 控制台输出 ---- 
        print(f"\n{'='*50}")
        print(f"{username}")
        print(f"  买入/加仓信号: {result['total_signals']} 条")

        r7 = result["returns_7d"]
        r30 = result["returns_30d"]
        # 胜率输出（安全处理 None 值）
        wr7 = f"{r7['win_rate']*100:.1f}%" if r7.get("win_rate") is not None else "N/A"
        wr30 = f"{r30['win_rate']*100:.1f}%" if r30.get("win_rate") is not None else "N/A"
        ar7 = f"{r7['avg_return']*100:+.2f}%" if r7.get("avg_return") is not None else "N/A"
        ar30 = f"{r30['avg_return']*100:+.2f}%" if r30.get("avg_return") is not None else "N/A"

        print(f"  7日胜率: {wr7} (n={r7['count']})  均收益: {ar7}")
        print(f"  30日胜率: {wr30} (n={r30['count']}) 均收益: {ar30}  夏普: {r30['sharpe']}")
        print(f"  最多赚: {r30['max_return']*100:+.1f}%  最惨亏: {r30['min_return']*100:+.1f}%")

        # 按板块 TOP 5
        print(f"\n  按板块 TOP 5 (30日胜率):")
        top_topic = sorted(
            result["by_topic"].items(),
            key=lambda x: x[1]["avg_return"] or -99,
            reverse=True,
        )[:5]
        for topic, stats in top_topic:
            if stats["count"]:
                print(
                    f"    {topic}: {stats['win_rate']*100:.0f}% "
                    f"({stats['count']}次) +{stats['avg_return']*100:.1f}%"
                )

        # 按股票 TOP 5
        print(f"\n  按股票 TOP 5 (30日胜率):")
        top = sorted(
            result["by_stock"].items(),
            key=lambda x: x[1]["returns_30d"]["avg_return"] or -99,
            reverse=True,
        )[:5]
        for t, s in top:
            r30s = s["returns_30d"]
            if r30s["count"]:
                print(
                    f"    {t}: {r30s['win_rate']*100:.0f}% "
                    f"({r30s['count']}次) +{r30s['avg_return']*100:.1f}%"
                )

        print(f"  -> 已写入 {out_path}")


if __name__ == "__main__":
    main()
