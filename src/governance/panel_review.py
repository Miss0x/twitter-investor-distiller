"""Panel Review engine — runs each role group persona against a SignalCandidate.

Produces structured review output with stances, scores, evidence refs, and
missing evidence. Currently deterministic; LLM summarization is a future
hook point.
"""

from __future__ import annotations

from src.governance.llm_review import run_llm_review
from src.governance.models import EvidenceRef, PanelStance, SignalCandidate
from src.governance.roles import RoleConfig, load_role_config


def _check_evidence_coverage(
    required: list[str],
    available_evidence: list[EvidenceRef],
) -> tuple[list[str], list[str]]:
    """Given required evidence types, return (covered, missing).

    This is a simplified check: for now we key on source_type strings.
    Future versions can do richer mapping.
    """
    available_types = {e.source_type for e in available_evidence}
    covered = [r for r in required if r in available_types]
    missing = [r for r in required if r not in available_types]
    return covered, missing


def _deterministic_review(candidate: SignalCandidate, group_id: str, group, persona) -> dict:
    covered, missing = _check_evidence_coverage(persona.required_evidence, candidate.evidence)

    if not persona.required_evidence:
        score = 0.5
        stance: PanelStance = "neutral"
    elif len(missing) == 0:
        score = 0.8
        bias = persona.stance_bias
        if bias in ("quality_first", "disruption_optimism", "supply_chain_focused"):
            stance = "bullish"
        elif bias in ("risk_seeking", "skeptical"):
            stance = "bearish"
        elif bias == "cycle_aware":
            stance = "neutral"
        elif bias in ("trend_biased", "sentiment_driven"):
            stance = "bullish"
        else:
            stance = "neutral"
    elif len(covered) > 0:
        score = 0.5
        stance = "neutral"
    else:
        score = 0.1
        stance = "insufficient_data"

    return {
        "group_id": group_id,
        "group_label": group.label,
        "persona_id": persona.id,
        "persona_label": persona.label,
        "stance": stance,
        "score": score,
        "evidence_used": [e.source_id for e in candidate.evidence if e.source_type in covered],
        "missing_evidence": missing,
        "source": "deterministic",
        "valid": True,
    }


def _aggregate_reviews(reviews: list[dict]) -> dict:
    valid_reviews = [r for r in reviews if r.get("valid", True)]
    stances = [str(r.get("stance", "insufficient_data")) for r in valid_reviews]

    bullish = stances.count("bullish")
    bearish = stances.count("bearish")
    neutral = stances.count("neutral")
    avoid = stances.count("avoid")
    insufficient = stances.count("insufficient_data")

    if not valid_reviews:
        aggregate_stance = "insufficient_data"
    elif insufficient >= len(valid_reviews) * 0.5:
        aggregate_stance = "insufficient_data"
    elif avoid > 0 and avoid >= bullish:
        aggregate_stance = "avoid"
    elif bearish > bullish and bearish > neutral:
        aggregate_stance = "bearish"
    elif bullish > bearish and bullish > neutral:
        aggregate_stance = "bullish"
    else:
        aggregate_stance = "neutral"

    avg_score = sum(float(r.get("score", 0)) for r in valid_reviews) / max(len(valid_reviews), 1)
    return {
        "aggregate_stance": aggregate_stance,
        "aggregate_score": round(avg_score, 3),
        "bullish_count": bullish,
        "bearish_count": bearish,
        "neutral_count": neutral,
        "avoid_count": avoid,
        "insufficient_data_count": insufficient,
    }


def run_panel_review(
    candidate: SignalCandidate,
    config: RoleConfig | None = None,
    llm_client=None,
) -> dict:
    """Run deterministic panel review on a SignalCandidate.

    Returns structured output ready for Publish Gate and SignalPackage.

    Each role group persona contributes:
      - group_id, persona_id
      - stance (PanelStance)
      - score (float 0-1)
      - evidence_used (list of EvidenceRef source_ids)
      - missing_evidence (list of required evidence types not found)

    LLM summarization hook: set `needs_llm_summary=True` in output when
    a future phase adds LLM synthesis.
    """
    if config is None:
        config = load_role_config()

    reviews: list[dict] = []
    used_llm = llm_client is not None
    fallback_used = False
    invalid_llm = False

    for group_id, group in config.role_groups.items():
        for persona in group.personas:
            if llm_client is None:
                reviews.append(_deterministic_review(candidate, group_id, group, persona))
                continue

            try:
                llm_result = run_llm_review(
                    client=llm_client,
                    candidate=candidate,
                    group=group,
                    persona=persona,
                )
            except Exception:
                fallback_used = True
                reviews.append(_deterministic_review(candidate, group_id, group, persona))
                continue

            reviews.append(llm_result.payload)
            if not llm_result.valid:
                invalid_llm = True

    aggregate = _aggregate_reviews(reviews)
    if fallback_used:
        review_mode = "deterministic_fallback"
    elif invalid_llm:
        review_mode = "fallback"
    elif used_llm:
        review_mode = "llm"
    else:
        review_mode = "deterministic"

    return {
        "reviews": reviews,
        **aggregate,
        "review_mode": review_mode,
        "needs_llm_summary": False,
    }
