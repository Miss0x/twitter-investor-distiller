"""Evidence-constrained LLM reviewer helpers for governance panel review."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.governance.models import SignalCandidate
from src.governance.roles import PersonaConfig, RoleGroupConfig

ReviewStance = Literal["bullish", "bearish", "neutral", "avoid", "insufficient_data"]
ReviewDecision = Literal["support", "warn", "block"]

_ALLOWED_STANCES = {"bullish", "bearish", "neutral", "avoid", "insufficient_data"}
_ALLOWED_DECISIONS = {"support", "warn", "block"}


@dataclass(frozen=True)
class LLMReviewResult:
    """Validated LLM review payload."""

    valid: bool
    payload: dict
    invalid_reason: str | None = None


def _as_list(value: object) -> list:
    if isinstance(value, list):
        return value
    return []


def validate_llm_review(
    raw: dict,
    candidate: SignalCandidate,
    group: RoleGroupConfig,
    persona: PersonaConfig,
) -> LLMReviewResult:
    """Validate one LLM reviewer response against schema and evidence ids."""
    if not isinstance(raw, dict):
        return LLMReviewResult(valid=False, payload={}, invalid_reason="invalid_schema")

    evidence_used = [str(item) for item in _as_list(raw.get("evidence_used"))]
    known_evidence_ids = {e.source_id for e in candidate.evidence}
    if any(evidence_id not in known_evidence_ids for evidence_id in evidence_used):
        return LLMReviewResult(
            valid=False,
            payload={
                "group_id": group.id,
                "group_label": group.label,
                "persona_id": persona.id,
                "persona_label": persona.label,
                "stance": raw.get("stance", "insufficient_data"),
                "score": 0,
                "confidence": 0,
                "decision": "block",
                "key_points": _as_list(raw.get("key_points")),
                "evidence_used": evidence_used,
                "data_gaps": _as_list(raw.get("data_gaps")),
                "risk_flags": _as_list(raw.get("risk_flags")),
                "summary": str(raw.get("summary") or "这条评审引用了不存在的证据，不能采信。"),
                "source": "llm",
                "valid": False,
                "invalid_reason": "unknown_evidence",
            },
            invalid_reason="unknown_evidence",
        )

    stance = str(raw.get("stance") or "neutral")
    if stance not in _ALLOWED_STANCES:
        stance = "neutral"

    decision = str(raw.get("decision") or "warn")
    if decision not in _ALLOWED_DECISIONS:
        decision = "warn"

    try:
        confidence = int(raw.get("confidence", 50))
    except (TypeError, ValueError):
        confidence = 50
    confidence = max(0, min(confidence, 100))

    payload = {
        "group_id": group.id,
        "group_label": group.label,
        "persona_id": persona.id,
        "persona_label": persona.label,
        "stance": stance,
        "score": round(confidence / 100, 3),
        "confidence": confidence,
        "decision": decision,
        "key_points": [str(item) for item in _as_list(raw.get("key_points"))][:5],
        "evidence_used": evidence_used,
        "data_gaps": [str(item) for item in _as_list(raw.get("data_gaps"))],
        "risk_flags": [str(item) for item in _as_list(raw.get("risk_flags"))],
        "summary": str(raw.get("summary") or "暂无明确结论。"),
        "source": "llm",
        "valid": True,
    }
    return LLMReviewResult(valid=True, payload=payload)


def run_llm_review(
    *,
    client,
    candidate: SignalCandidate,
    group: RoleGroupConfig,
    persona: PersonaConfig,
) -> LLMReviewResult:
    """Run and validate one LLM reviewer call through an injected client."""
    raw = client.review(candidate=candidate, group=group, persona=persona)
    return validate_llm_review(raw, candidate, group, persona)
