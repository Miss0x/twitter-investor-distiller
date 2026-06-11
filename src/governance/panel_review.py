"""Panel Review engine — runs each role group persona against a SignalCandidate.

Produces structured review output with stances, scores, evidence refs, and
missing evidence. Currently deterministic; LLM summarization is a future
hook point.
"""

from __future__ import annotations

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


def run_panel_review(
    candidate: SignalCandidate,
    config: RoleConfig | None = None,
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
    stances: list[str] = []

    for group_id, group in config.role_groups.items():
        for persona in group.personas:
            covered, missing = _check_evidence_coverage(
                persona.required_evidence, candidate.evidence
            )

            # Deterministic stance scoring:
            # - If all required evidence covered → score >= 0.7, stance based on bias
            # - If some covered → score 0.4-0.6
            # - If none covered → score 0.1, "insufficient_data"
            if not persona.required_evidence:
                score = 0.5
                stance: PanelStance = "neutral"
            elif len(missing) == 0:
                score = 0.8
                # Map stance_bias to PanelStance
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

            review = {
                "group_id": group_id,
                "group_label": group.label,
                "persona_id": persona.id,
                "persona_label": persona.label,
                "stance": stance,
                "score": score,
                "evidence_used": [e.source_id for e in candidate.evidence if e.source_type in covered],
                "missing_evidence": missing,
            }
            reviews.append(review)
            stances.append(stance)

    # Aggregate stance
    bullish = stances.count("bullish")
    bearish = stances.count("bearish")
    neutral = stances.count("neutral")
    avoid = stances.count("avoid")
    insufficient = stances.count("insufficient_data")

    if insufficient >= len(reviews) * 0.5:
        aggregate_stance = "insufficient_data"
    elif bearish > bullish and bearish > neutral:
        aggregate_stance = "bearish"
    elif bullish > bearish and bullish > neutral:
        aggregate_stance = "bullish"
    else:
        aggregate_stance = "neutral"

    avg_score = sum(r["score"] for r in reviews) / max(len(reviews), 1)

    return {
        "reviews": reviews,
        "aggregate_stance": aggregate_stance,
        "aggregate_score": round(avg_score, 3),
        "bullish_count": bullish,
        "bearish_count": bearish,
        "neutral_count": neutral,
        "insufficient_data_count": insufficient,
        "needs_llm_summary": False,
    }
