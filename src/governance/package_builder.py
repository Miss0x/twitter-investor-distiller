"""SignalPackage builder — assembles the final governance output.

SignalPackage is the single source of truth for all downstream consumers
(Dashboard, RAG, Telegram, HTML report).
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.governance.models import (
    AcknowledgedGap,
    DataGap,
    SignalCandidate,
    SignalPackage,
)
from src.governance.repository import GovernanceRepository


def build_package(
    candidate: SignalCandidate,
    quality: dict,
    data_gaps: list[DataGap],
    acknowledged_gaps: list[AcknowledgedGap],
    panel: dict,
    debate: dict,
    risk: dict,
    publish_review: dict,
    repo: GovernanceRepository | None = None,
) -> SignalPackage:
    """Assemble a SignalPackage from all governance results.

    If repo is provided, the package JSON is persisted to
    data/governance/packages/YYYY-MM-DD/{signal_id}.json.
    """
    package = SignalPackage(
        signal_id=candidate.signal_id,
        ticker=candidate.ticker,
        generated_at=datetime.now(timezone.utc),
        publish_status=publish_review["status"],
        summary=_build_summary(candidate, debate, risk),
        candidate=candidate,
        quality=quality,
        data_gaps=data_gaps,
        acknowledged_gaps=acknowledged_gaps,
        panel=panel,
        debate=debate,
        risk=risk,
        publish_review=publish_review,
        evidence=candidate.evidence,
    )

    if repo is not None:
        repo.save_package(package)

    return package


def _build_summary(candidate: SignalCandidate, debate: dict, risk: dict) -> str:
    parts = []
    if candidate.stance:
        parts.append(f"Signal stance: {candidate.stance}")
    if debate.get("final_stance"):
        parts.append(f"Debate conclusion: {debate['final_stance']}")
    if risk.get("risk_level"):
        parts.append(f"Risk level: {risk['risk_level']}")
    if candidate.signal_score is not None:
        parts.append(f"Score: {candidate.signal_score}")
    return "; ".join(parts) if parts else "No summary available"
