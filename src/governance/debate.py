"""Bull/Bear/Rebuttal Debate engine.

Inspired by TradingAgents multi-agent debate. Given panel review output,
composes bull thesis from bullish reviewers and bear thesis from bearish
reviewers, then produces a rebuttal that resolves to a final stance.

Deterministic composition; future versions may add LLM synthesis.
"""

from __future__ import annotations


def _count_stances(reviews: list[dict]) -> tuple[int, int, int, int]:
    bull = sum(1 for r in reviews if r["stance"] == "bullish")
    bear = sum(1 for r in reviews if r["stance"] == "bearish")
    neutral = sum(1 for r in reviews if r["stance"] == "neutral")
    insufficient = sum(1 for r in reviews if r["stance"] == "insufficient_data")
    return bull, bear, neutral, insufficient


def run_debate(panel_review: dict) -> dict:
    """Run debate synthesis from panel review output.

    Returns dict with bull, bear, rebuttal, and final_stance sections.
    """
    reviews = panel_review.get("reviews", [])
    if not reviews:
        return {
            "bull": {"thesis": "No reviews available", "evidence": [], "confidence": 0.0},
            "bear": {"thesis": "No reviews available", "evidence": [], "confidence": 0.0},
            "rebuttal": {
                "winner": "none",
                "why": "Insufficient panel review data",
                "remaining_uncertainties": ["no reviews"],
            },
            "final_stance": "insufficient_data",
            "must_disclose_risks": ["No panel review data available"],
        }

    bull_reviews = [r for r in reviews if r["stance"] == "bullish"]
    bear_reviews = [r for r in reviews if r["stance"] == "bearish"]

    bull_count = len(bull_reviews)
    bear_count = len(bear_reviews)

    bull_thesis = _synthesize_thesis(bull_reviews, "bullish")
    bear_thesis = _synthesize_thesis(bear_reviews, "bearish")

    bull_confidence = (
        sum(r["score"] for r in bull_reviews) / max(bull_count, 1) if bull_count else 0.0
    )
    bear_confidence = (
        sum(r["score"] for r in bear_reviews) / max(bear_count, 1) if bear_count else 0.0
    )

    # Rebuttal: compare counts and average scores
    if bull_count == 0 and bear_count == 0:
        winner = "none"
        why = "No bullish or bearish positions expressed"
        uncertainties = ["All reviewers neutral or insufficient_data"]
        final_stance = "neutral"
    elif bull_count > bear_count:
        winner = "bull"
        why = f"Bullish majority ({bull_count} vs {bear_count} bearish)"
        uncertainties = []
        if bear_count > 0:
            uncertainties.append(f"Bear concerns from {bear_count} reviewer(s)")
        final_stance = "bullish"
    elif bear_count > bull_count:
        winner = "bear"
        why = f"Bearish majority ({bear_count} vs {bull_count} bullish)"
        uncertainties = []
        if bull_count > 0:
            uncertainties.append(f"Bull concerns from {bull_count} reviewer(s)")
        final_stance = "bearish"
    else:
        winner = "none"
        why = f"Split vote ({bull_count} bull vs {bear_count} bear)"
        uncertainties = ["Evenly split between bull and bear"]
        final_stance = "neutral"

    # Collect risks
    risks = []
    risk_reviews = [r for r in reviews if r.get("group_id") == "risk_control" or r.get("stance") == "bearish"]
    for r in risk_reviews:
        if r.get("missing_evidence"):
            risks.append(f"{r['persona_label']}: missing {', '.join(r['missing_evidence'])}")

    if not risks:
        risks.append("No explicit risk concerns raised")

    return {
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


def _synthesize_thesis(reviews: list[dict], stance_label: str) -> str:
    if not reviews:
        return f"No {stance_label} positions"
    personas = [r["persona_label"] for r in reviews]
    return f"{stance_label.title()} position from: {', '.join(personas)}"
