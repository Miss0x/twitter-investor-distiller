"""Risk Scan — detect promo scams, group-solicitation, template manipulation and other
risk signals in user questions and signal candidate text.

Inspired by UZI-Skill trap-detector. Runs as a deterministic weighted-rule system
with configurable trigger words. High-risk signals block strong push (Telegram).
"""

from __future__ import annotations

from typing import Literal

from src.governance.models import RiskLevel, SignalCandidate


# ── trigger word rules ──
# Each rule: (keyword, weight, dimension, description)
# Weights are additive; high_risk starts at 70.

USER_TEXT_TRIGGERS: list[tuple[str, float, str, str]] = [
    ("群里老师", 25.0, "group_teacher", "群内老师推荐信号"),
    ("必涨", 20.0, "guaranteed_gain", "必涨/必赚类承诺"),
    ("内幕", 25.0, "insider_claim", "内幕消息声称"),
    ("翻倍", 20.0, "multiplier_claim", "翻倍/暴利承诺"),
    ("推荐", 10.0, "recommendation", "推荐信号"),
    ("杀猪盘", 35.0, "pig_butchering", "杀猪盘警示"),
    ("庄家", 20.0, "market_manipulation", "庄家/操纵暗示"),
    ("稳赚", 25.0, "guaranteed_profit", "稳赚暗示"),
    ("打板", 10.0, "hit_limit_up", "打板/追涨停"),
    ("主力", 10.0, "institutional_flow", "主力资金暗示"),
    ("拉升", 15.0, "pump_signal", "拉升/拉盘信号"),
    ("出货", 15.0, "dump_signal", "出货信号"),
    ("涨停", 10.0, "limit_up", "涨停相关"),
]


def scan_user_text(text: str) -> dict:
    """Scan user text for risk triggers.

    Returns:
      risk_level: "safe" | "notice" | "caution" | "high_risk"
      total_score: summed weight
      triggers_hit: list of hit rules
    """
    if not text:
        return {"risk_level": "safe", "total_score": 0.0, "triggers_hit": []}

    total = 0.0
    hits: list[dict] = []

    for keyword, weight, dimension, desc in USER_TEXT_TRIGGERS:
        if keyword in text:
            total += weight
            hits.append(
                {
                    "keyword": keyword,
                    "weight": weight,
                    "dimension": dimension,
                    "description": desc,
                }
            )

    if total >= 70:
        level: RiskLevel = "high_risk"
    elif total >= 40:
        level = "caution"
    elif total >= 20:
        level = "notice"
    else:
        level = "safe"

    return {"risk_level": level, "total_score": total, "triggers_hit": hits}


def _extract_candidate_text(candidate: SignalCandidate) -> str:
    """Extract all evidence excerpts from a SignalCandidate for risk scanning."""
    parts = []
    for e in candidate.evidence:
        if e.excerpt:
            parts.append(e.excerpt)
    return " ".join(parts)


def run_risk_scan(
    candidate: SignalCandidate,
    user_question: str = "",
) -> dict:
    """Full risk scan combining user text and candidate content analysis.

    Returns dict with:
      risk_level: RiskLevel
      total_score: float
      triggering_signals: list of hit rule dicts
      allow_strong_push: bool — True only when safe or notice
    """
    # Scan user question text
    user_result = scan_user_text(user_question)

    # Scan candidate evidence text
    candidate_text = _extract_candidate_text(candidate)
    candidate_result = scan_user_text(candidate_text)

    total_score = user_result["total_score"] + candidate_result["total_score"]
    all_hits = user_result["triggers_hit"] + candidate_result["triggers_hit"]

    if total_score >= 70:
        level: RiskLevel = "high_risk"
    elif total_score >= 40:
        level = "caution"
    elif total_score >= 20:
        level = "notice"
    else:
        level = "safe"

    return {
        "risk_level": level,
        "total_score": total_score,
        "triggering_signals": all_hits,
        "allow_strong_push": level not in ("high_risk",),
    }
