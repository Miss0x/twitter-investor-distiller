"""#1 信号量化 — Phase 2 核心模块

将分析师推文的 LLM 分析结果量化为 0-100 分信号，写入 signal_score 字段。

信号组成（4 维度加权）：
1. Stance 立场分 (40%): 看多/加仓 → 正分, 看空/卖出 → 负分
2. Confidence 置信度 (35%): LLM 判定的 high/medium/low，经贝叶斯校准
3. K线共振 (15%): 当前价格相对 SMA20 的 Z-score，反映趋势一致性
4. 多股票覆盖 (10%): 提到的股票数越多，覆盖面越广但信号越分散

关键设计：
- 贝叶斯校准：原始置信度 × 分析师历史 30日胜率，降低"嘴炮"型信号
- K线共振：信号在趋势方向上的"顺风车"加成（顺势更好，逆势更低）
- 所有输入数据从 data/prices.json 和 data/accuracy/*.json 读取

用法：
    python scripts/compute_signals.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

# 数据路径配置
PIPELINE_DIR = Path("data/pipeline")          # analyzed_cleaned 结果目录
PRICES_PATH = Path("data/prices.json")        # Polygon 股价快照
ACCURACY_DIR = Path("data/accuracy")           # 各分析师准确率统计

# ---- 因子权重（总和 1.0） ----
W_STANCE = 0.40        # 立场方向的权重最大——"看多还是看空"是信号核心
W_CONFIDENCE = 0.35    # 置信度权重次之——高质量判断更有参考价值
W_RESONANCE = 0.15     # K线共振——逆势信号需警惕，顺势信号更可信
W_MULTI_STOCK = 0.10   # 多股票覆盖——覆盖面广但信号分散

# ---- stance 文本 → 数值映射 ----
# 正数 = 看多/建仓方向，负数 = 看空/减仓方向，0 = 中性/观望
STANCE_MAP = {
    "看多": 1.0,         # 明确看多
    "加仓": 0.9,         # 建议加仓
    "建仓|加仓": 0.8,    # 建仓/加仓
    "持有": 0.3,         # 继续持有（温和看多）
    "定投": 0.2,         # 定投策略（温和看多）
    "观望": 0.0,         # 观望
    "卖出/观望": -0.3,   # 卖出或观望（轻微看空）
    "减仓|观望": -0.4,   # 减仓或观望
    "无明确方向": 0.0,   # 无方向
    "中性": 0.0,          # 中性
    "减仓": -0.8,        # 减仓（看空）
    "卖出": -1.0,        # 明确看空
    "做空": -1.0,        # 做空
    "离场": -1.0,        # 离场
}

# ---- confidence 文本 → 数值映射 ----
# LLM 输出的置信度等级映射为 0-1 区间的先验值
CONF_MAP = {"high": 1.0, "medium": 0.5, "low": 0.2}


def load_accuracy() -> dict[str, float]:
    """加载每个分析师的 30 日历史胜率，用于贝叶斯校准。

    读取 data/accuracy/{username}_accuracy.json 中的 returns_30d.win_rate 字段。
    胜率越高的分析师，其置信度的折扣越小。

    注意：returns_30d 字段已经过事件研究回测计算，非编造数据。

    Returns:
        dict[str, float]: {username: win_rate} 映射，胜率范围 0.0-1.0。
                          如果某分析师没有 accuracy 文件，则不出现在字典中，
                          后续贝叶斯校准会使用 0.5 作为无信息先验。
    """
    win_rates: dict[str, float] = {}
    for fp in ACCURACY_DIR.glob("*_accuracy.json"):
        username = fp.stem.replace("_accuracy", "")
        d = json.loads(fp.read_text(encoding="utf-8"))
        wr = d.get("returns_30d", {}).get("win_rate")
        if wr is not None:
            win_rates[username] = wr
    return win_rates


def load_prices() -> dict:
    """加载股价数据。

    从 data/prices.json 读取 Polygon API 的聚合 K 线数据。
    只保留包含 "results" 字段的有效条目。

    Returns:
        dict: {ticker: [{t, o, h, l, c, v, ...}, ...]} 的格式
              ticker 统一转为大写
    """
    raw = json.loads(PRICES_PATH.read_text(encoding="utf-8"))
    prices = {}
    for ticker, snap in raw.items():
        if isinstance(snap, dict) and "results" in snap:
            prices[ticker.upper()] = snap["results"]
    return prices


def price_on(results: list[dict], target_date: str) -> tuple[str, float] | None:
    """在 K 线数据中查找 >= target_date 的第一个交易日的 (日期, 收盘价)。

    如果 target_date 为非交易日（如周末），返回下一个交易日的价格。
    Polygon 数据中 t 字段为毫秒级 Unix 时间戳。

    Args:
        results: 某股票的历史 K 线数据（按时间升序排列）
        target_date: 目标日期，格式为 "YYYY-MM-DD"

    Returns:
        tuple | None: (实际日期, 收盘价)，找不到数据返回 None
    """
    from datetime import datetime, timezone
    best = None
    for bar in results:
        t_ms = bar.get("t", 0)
        if t_ms == 0:
            continue
        d = datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        if d < target_date:
            continue
        # 记录最早匹配的交易日（>= target_date 的最小日期）
        if best is None or d < best[0]:
            best = (d, bar["c"])
    return best


def compute_sma(results: list[dict], end_date_str: str, window: int = 20) -> float | None:
    """计算 end_date 前 window 个交易日的简单移动平均线 (SMA)。

    SMA20 是主要的趋势参考线：价格在 SMA20 上方 → 短期偏多，下方 → 短期偏空。

    Args:
        results: 历史 K 线数据
        end_date_str: 截止日期（不含该日），格式 "YYYY-MM-DD"
        window: 窗口大小，默认 20（约一个月交易日）

    Returns:
        float | None: SMA 值，数据不足 window 条时返回 None
    """
    from datetime import datetime, timezone
    closes: list[float] = []
    for bar in results:
        d = datetime.fromtimestamp(bar["t"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        if d >= end_date_str:
            break  # 只取 end_date 之前的数据
        closes.append(bar["c"])
    if len(closes) < window:
        return None
    return sum(closes[-window:]) / window


def compute_sma_std(results: list[dict], end_date_str: str, window: int = 20) -> float | None:
    """计算 end_date 前 window 个交易日收盘价的标准差。

    标准差用于归一化价格偏离度（Z-score 的分母），衡量波动性。

    Args:
        results: 历史 K 线数据
        end_date_str: 截止日期（不含该日），格式 "YYYY-MM-DD"
        window: 窗口大小，默认 20

    Returns:
        float | None: 标准差，数据不足时返回 None
    """
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
    """K 线共振因子 — 价格偏离 SMA20 的 Z-score。

    计算逻辑：
    1. 获取 entry_date 或其后最近交易日的收盘价
    2. 计算 entry_date 之前的 SMA20 和标准差
    3. Z = (close - SMA20) / std20
    4. 钳位到 [-2.0, 2.0] 防止异常值扭曲信号

    含义：
    - Z > 0: 价格高于均线 → 趋势向上，看多信号获得"顺风"加成
    - Z < 0: 价格低于均线 → 趋势向下，看多信号受到抑制
    - Z ≈ 0: 价格在均线附近，无共振效应

    Args:
        results: 历史 K 线数据
        entry_date: 推文发布日期，格式 "YYYY-MM-DD"
        window: SMA 窗口大小，默认 20

    Returns:
        float: Z-score，钳位到 [-2.0, 2.0]
    """
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
    """贝叶斯校准：用分析师历史胜率修正原始置信度。

    原理：
    - 如果分析师历史胜率 > 50%（比随机好），置信度保持或略降
    - 如果分析师历史胜率 < 50%（比随机差），置信度显著打折
    - 无胜率数据时使用 0.5（均匀先验，即"我什么都不知道"）

    公式：calibrated_confidence = raw_confidence × win_rate

    这本质上是一个简化的贝叶斯更新：将分析师的历史表现作为先验信息
    融合到当前信号的置信度中。

    Args:
        raw_confidence: 原始置信度数值（high=1.0, medium=0.5, low=0.2）
        analyst_win_rate: 该分析师 30 日历史胜率，None 表示无数据

    Returns:
        float: 校准后的置信度，范围 [0, 1]
    """
    prior = analyst_win_rate if analyst_win_rate is not None else 0.5
    return raw_confidence * prior


def compute_score(
    stance_raw: float,
    conf_calibrated: float,
    resonance: float,
    stock_count: int,
    conf_raw: float,
) -> tuple[float, dict]:
    """计算 0-100 的综合信号分。

    四因子加权汇总：
    - stance_score = stance_raw × 100   (范围 -100 ~ +100)
    - conf_score = conf_calibrated × 100 (范围 0 ~ 100)
    - resonance_score = resonance × 100  (范围 -200 ~ +200，经钳位)
    - multi_bonus = min(stock_count, 3) / 3 × 100  (1只=33, 3只+=100)

    final_signal = W_STANCE × stance_score + W_CONFIDENCE × conf_score
                   + W_RESONANCE × resonance_score + W_MULTI_STOCK × multi_bonus

    最终钳位到 [0, 100]。

    注意：多股票加分并非"越多越好"——提到 1 只说明专注，提到多只说明
    覆盖面广。此处使用渐进式加权（1只=33分, 3只=100分）而非线性加权。

    Args:
        stance_raw: 立场数值（来自 STANCE_MAP，范围 -1.0 ~ 1.0）
        conf_calibrated: 贝叶斯校准后的置信度（范围 0 ~ 1.0）
        resonance: K线共振 Z-score（钳位到 [-2.0, 2.0]）
        stock_count: 推文中提到的股票数量
        conf_raw: 原始置信度数值（用于记录，不参与最终计算）

    Returns:
        tuple[float, dict]:
            - float: 最终信号分 (0-100)
            - dict: 各因子得分明细，包含 stance_raw / stance_score / confidence_raw /
                    confidence_calibrated / confidence_score / resonance_z /
                    resonance_score / multi_stock_score
    """
    stance_score = stance_raw * 100          # -100 ~ +100，看多方向为正
    conf_score = conf_calibrated * 100       # 0 ~ 100
    resonance_score = resonance * 100        # -200 ~ +200，钳位后的共振 Z × 100

    # 多股票加分：min(stock_count, 3) / 3 × 100
    # 1只股票 ≈ 33分, 2只 ≈ 67分, 3只及以上 = 100分（边际递减）
    multi_bonus = min(stock_count, 3) / 3 * 100

    # 加权汇总
    signal = (
        W_STANCE * stance_score
        + W_CONFIDENCE * conf_score
        + W_RESONANCE * resonance_score
        + W_MULTI_STOCK * multi_bonus
    )

    # 钳位到 [0, 100]（信号分不应为负或超大，保持可解释性）
    signal = max(0.0, min(100.0, signal))

    # 各因子得分明细（用于前端展示和调试）
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
    """信号计算主流程。

    执行步骤：
    1. 加载各分析师历史胜率（用于贝叶斯校准）
    2. 加载股价数据（用于 K 线共振计算）
    3. 遍历所有 analyzed_cleaned JSON 文件
    4. 对每条记录：
       a. 数值化 stance 和 confidence
       b. 贝叶斯校准置信度
       c. 计算 K 线共振（取第一条股票的共振值）
       d. 加权计算 0-100 信号分
       e. 回写 signal_score 和 signal_components 到记录
    5. 保存文件 + 输出统计
    6. 展示 TOP 5 高信号和底部样例
    """
    # 加载输入数据
    win_rates = load_accuracy()
    prices = load_prices()
    print(f"分析师胜率: {win_rates}")
    print(f"股价: {len(prices)} 只")

    total = 0      # 处理记录总数
    scored = 0     # 有非零信号的记录数

    # 遍历每个分析师的 analyzed_cleaned 结果文件
    for fp in sorted(PIPELINE_DIR.glob("*_analyzed_cleaned.json")):
        # 从文件名提取用户名（如 TJ_Research_analyzed_cleaned.json → TJ_Research）
        username = fp.stem.split("_")[0]
        if username == "TJ":
            username = "TJ_Research"

        # 获取该分析师的 30 日胜率
        wr = win_rates.get(username)
        data = json.loads(fp.read_text(encoding="utf-8"))
        modified = False

        # 逐条处理分析结果
        for r in data:
            total += 1

            # 提取关键字段
            stance_raw = r.get("stance", "无明确方向")
            confidence_raw = r.get("confidence", "low")
            created = r.get("created_at", "")[:10]  # 只取日期部分
            stocks = r.get("stock_details", [])

            # --- 步骤 1: 数值化 ---
            stance_val = STANCE_MAP.get(stance_raw, 0.0)
            conf_val = CONF_MAP.get(confidence_raw, 0.2)

            # --- 步骤 2: 贝叶斯校准 ---
            # 用分析师历史胜率修正置信度
            conf_cal = bayesian_calibrate(conf_val, wr)

            # --- 步骤 3: K 线共振 ---
            # 取第一条股票的 K 线共振值（多条时暂取第一条）
            resonance = 0.0
            ticker = ""
            if stocks and created:
                ticker = stocks[0].get("ticker", "").upper()
                bars = prices.get(ticker, [])
                if bars:
                    resonance = momentum_z(bars, created)

            # --- 步骤 4: 计算综合信号 ---
            signal, components = compute_score(
                stance_val, conf_cal, resonance, len(stocks), conf_val
            )

            # --- 步骤 5: 写入信号到分析结果 ---
            r["signal_score"] = signal
            r["signal_components"] = components

            # 统计：有非零信号或非中性立场的记录
            if signal > 0 or stance_val != 0:
                scored += 1
            modified = True

        # 保存修改后的文件
        if modified:
            fp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    # ---- 输出总结 ----
    print(f"\n处理: {total} 条, 有信号: {scored} 条 ({scored/total*100:.0f}%)" if total > 0 else "\n无数据")

    # ---- 展示 TOP 5 信号样例 ----
    # 收集所有带信号分的记录并按信号分降序排列
    all_scored = []
    for fp in PIPELINE_DIR.glob("*_analyzed_cleaned.json"):
        for r in json.loads(fp.read_text(encoding="utf-8")):
            if "signal_score" in r:
                all_scored.append(r)
    all_scored.sort(key=lambda x: x["signal_score"], reverse=True)

    print(f"\nTOP 5 信号:")
    for r in all_scored[:5]:
        sc = r["signal_components"]
        print(
            f"  [{r['signal_score']:.0f}] {r.get('action_hint', '?')} "
            f"{r.get('stance', '?')} | {r.get('text', '')[:50]}..."
        )
        print(
            f"      stance={sc['stance_score']:.0f} conf={sc['confidence_score']:.0f} "
            f"resonance={sc['resonance_score']:.0f} multi={sc['multi_stock_score']:.0f}"
        )

    # 文件覆盖确认
    print(
        f"\n已写入: {len(list(PIPELINE_DIR.glob('*_analyzed_cleaned.json')))} 个文件"
    )


if __name__ == "__main__":
    main()
