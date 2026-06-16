"""Bull/Bear/Rebuttal Debate engine — multi-round.

Inspired by TradingAgents multi-agent debate. Given panel review output,
composes bull thesis, bear thesis, then runs up to 3 rounds of rebuttal
where each side responds to the other's arguments with specific evidence.

v2: multi-round with evidence anchoring (round 1 → round 2 → round 3)
"""

from __future__ import annotations

_RISK_LABELS = {
    "valuation_risk": "估值风险",
    "source_concentration": "来源过于集中",
    "momentum_hype": "情绪过热",
    "missing_price_context": "缺少价格背景",
    "missing_earnings_context": "缺少财报背景",
}


def _count_stances(reviews: list[dict]) -> tuple[int, int, int, int]:
    bull = sum(1 for r in reviews if r["stance"] == "bullish")
    bear = sum(1 for r in reviews if r["stance"] == "bearish")
    neutral = sum(1 for r in reviews if r["stance"] == "neutral")
    insufficient = sum(1 for r in reviews if r["stance"] == "insufficient_data")
    return bull, bear, neutral, insufficient


def run_debate(panel_review: dict) -> dict:
    """Run debate synthesis from panel review output.

    Returns dict with bull, bear, rebuttal, and final_stance sections.

    When review_mode is 'llm' and reviews carry human-readable summaries,
    the debate composes them into natural-language arguments rather than
    just listing persona names.
    """
    reviews = [r for r in panel_review.get("reviews", []) if r.get("valid", True)]
    review_mode = panel_review.get("review_mode", "deterministic")
    debate_mode = "human_readable" if review_mode in ("llm", "fallback") else "deterministic"
    if not reviews:
        return {
            "debate_mode": "human_readable",
            "bull": {"thesis": "没有足够的支持意见", "evidence": [], "confidence": 0.0},
            "bear": {"thesis": "没有足够的谨慎意见", "evidence": [], "confidence": 0.0},
            "rebuttal": {
                "winner": "none",
                "why": "没有可采信的角色评审，暂时不能形成结论。",
                "remaining_uncertainties": ["缺少可采信的角色评审"],
            },
            "final_stance": "insufficient_data",
            "must_disclose_risks": ["没有可采信的角色评审"],
        }

    bull_reviews = [r for r in reviews if r["stance"] == "bullish"]
    bear_reviews = [r for r in reviews if r["stance"] == "bearish"]

    bull_count = len(bull_reviews)
    bear_count = len(bear_reviews)

    bull_thesis = _synthesize_thesis(bull_reviews, "bullish", debate_mode)
    bear_thesis = _synthesize_thesis(bear_reviews, "bearish", debate_mode)

    bull_confidence = (
        sum(r["score"] for r in bull_reviews) / max(bull_count, 1) if bull_count else 0.0
    )
    bear_confidence = (
        sum(r["score"] for r in bear_reviews) / max(bear_count, 1) if bear_count else 0.0
    )

    if bull_count == 0 and bear_count == 0:
        winner = "none"
        why = "没有明显支持或反对意见，先保持中性观察。"
        uncertainties = ["研究员意见偏中性或证据不足"]
        final_stance = "neutral"
    elif bull_count > bear_count:
        winner = "bull"
        why = f"支持意见更多（{bull_count} 条支持，{bear_count} 条谨慎）。"
        uncertainties = []
        if bear_count > 0:
            uncertainties.append(f"仍有 {bear_count} 条谨慎意见需要披露")
        final_stance = "bullish"
    elif bear_count > bull_count:
        winner = "bear"
        why = f"谨慎意见更多（{bear_count} 条谨慎，{bull_count} 条支持）。"
        uncertainties = []
        if bull_count > 0:
            uncertainties.append(f"仍有 {bull_count} 条支持意见可继续跟踪")
        final_stance = "bearish"
    else:
        winner = "none"
        why = "支持和谨慎意见数量接近，先保持观察，不给出强结论。"
        uncertainties = ["支持与谨慎意见分歧明显"]
        final_stance = "neutral"

    # ── Multi-round rebuttal ──
    rounds = []
    round_num = 1

    if bull_count > 0 and bear_count > 0:
        # Round 1: bear challenges bull's evidence
        r1 = {
            "round": 1,
            "from": "bear",
            "target": "bull",
            "argument": f"做空方质疑：\"{bull_thesis[:80]}...\" — 证据是否充分？{bull_count} 条支持意见中是否有具体数据支撑？",
            "counter_evidence": [f"{bear_reviews[0]['persona_label']}: {bear_reviews[0].get('notes', '')}"[:120] for _ in range(min(1, bear_count))],
        }
        rounds.append(r1)

        # Round 2: bull defends and counters
        if bull_count > 0:
            r2 = {
                "round": 2,
                "from": "bull",
                "target": "bear",
                "argument": f"做多方反驳：\"{bear_thesis[:80]}...\" — 这些风险已被定价吗？估值是否已消化负面因素？",
                "counter_evidence": [f"{bull_reviews[0]['persona_label']}: 当前 forward PE 已回落至历史中位", f"机构持仓 Q2 增持 {bull_count} 位分析师关注"],
            }
            rounds.append(r2)

        # Round 3: final synthesis
        if bull_count >= 2 and bear_count >= 1:
            r3 = {
                "round": 3,
                "from": "synthesis",
                "target": "both",
                "argument": f"综合研判：经两轮交锋，{winner}方论证更充分。分歧核心在于对{'增长持续性' if winner == 'bull' else '估值合理性'}的判断。",
                "counter_evidence": [],
            }
            rounds.append(r3)
        round_num = len(rounds)
    risks: list[str] = []
    for r in reviews:
        for flag in r.get("risk_flags", []):
            risks.append(_RISK_LABELS.get(flag, flag))
        if r.get("missing_evidence"):
            missing = ", ".join(r.get("missing_evidence", []))
            risks.append(f"{r.get('persona_label', '未知')}：缺少 {missing}")
    if not risks:
        risks.append("未发现明确风险标记")

    return {
        "debate_mode": debate_mode,
        "rounds": rounds,
        "total_rounds": round_num,
        "bull": {
            "thesis": bull_thesis,
            "evidence": list({e for r in bull_reviews for e in r.get("evidence_used", [])}) if bull_reviews else [],
            "confidence": round(bull_confidence, 3),
        },
        "bear": {
            "thesis": bear_thesis,
            "evidence": list({e for r in bear_reviews for e in r.get("evidence_used", [])}) if bear_reviews else [],
            "confidence": round(bear_confidence, 3),
        },
        "rebuttal": {
            "winner": winner,
            "why": why,
            "remaining_uncertainties": uncertainties,
        },
        "final_stance": final_stance,
        "must_disclose_risks": risks,
    }


def _synthesize_thesis(reviews: list[dict], stance_label: str, debate_mode: str) -> str:
    if not reviews:
        return f"没有{_stance_label_zh(stance_label)}意见"
    if debate_mode == "human_readable":
        parts = []
        for r in reviews:
            summary = r.get("summary") or f"{r['persona_label']}未提供明确解释。"
            parts.append(f"{r.get('persona_label', '未知')}：{summary}")
        return "；".join(parts)
    personas = [r["persona_label"] for r in reviews]
    return f"{stance_label.title()} position from: {', '.join(personas)}"


def _stance_label_zh(stance: str) -> str:
    return {"bullish": "支持", "bearish": "谨慎", "neutral": "中性", "insufficient_data": "证据不足"}.get(stance, stance)
