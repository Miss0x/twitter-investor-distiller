"""DataGap registry — detect and manage data gaps independently from quality assessment.

This module implements UZI-Skill's "data gaps as independent artifacts" design.
Gaps are collected, persisted as JSON files under data/governance/data_gaps/YYYY-MM-DD/,
and used by Publish Gate to determine whether a signal can proceed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.governance.models import AcknowledgedGap, DataGap, SignalCandidate
from src.governance.repository import GovernanceRepository


def collect_data_gaps(candidate: SignalCandidate) -> list[DataGap]:
    """Inspect a SignalCandidate and produce a list of detected data gaps.

    Callers can extend this with additional checks (price freshness,
    ticker mapping, analysis output existence, etc.).
    """
    gaps: list[DataGap] = []

    # No evidence at all — critical
    if not candidate.has_evidence():
        gaps.append(
            DataGap(
                code="no_evidence",
                message="Signal candidate has zero evidence references",
                severity="critical",
                required_for_publish=True,
                suggested_fix="Run analysis/pipeline to generate evidence",
            )
        )
        return gaps  # no point checking further

    # Missing price context
    has_price = any(e.source_type == "price" for e in candidate.evidence)
    if not has_price:
        gaps.append(
            DataGap(
                code="missing_price_context",
                message="No market price data available for this signal",
                severity="warning",
                required_for_publish=False,
                suggested_fix="Run price fetch pipeline for this ticker",
            )
        )

    # Missing analysis context (placeholder for future analysis integration)
    # has_analysis = any(e.source_type == "analysis" for e in candidate.evidence)
    # if not has_analysis:
    #     gaps.append(DataGap(...))

    return gaps


def acknowledge_gap(
    signal_id: str,
    gap_code: str,
    reason: str,
    acknowledged_by: str,
    expires_at: str | None = None,
) -> AcknowledgedGap:
    """Create an acknowledgment for a gap that cannot be resolved now."""
    return AcknowledgedGap(
        code=gap_code,
        reason=reason,
        acknowledged_by=acknowledged_by,
        acknowledged_at=datetime.now(timezone.utc).isoformat(),
        expires_at=expires_at,
    )


def _is_ack_active(ack: AcknowledgedGap, now: datetime | None = None) -> bool:
    """Return True when an acknowledged gap has not expired."""
    if not ack.expires_at:
        return True
    now = now or datetime.now(timezone.utc)
    try:
        expires_at = datetime.fromisoformat(ack.expires_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > now


def has_blocking_gaps(
    gaps: list[DataGap],
    acknowledged: list[AcknowledgedGap],
    now: datetime | None = None,
) -> bool:
    """Return True if there are required gaps that have NOT been acknowledged.

    A gap with required_for_publish=True blocks publish readiness unless
    there is a matching, non-expired AcknowledgedGap with the same code.
    """
    acked_codes = {a.code for a in acknowledged if _is_ack_active(a, now=now)}
    for gap in gaps:
        if not gap.required_for_publish:
            continue
        if gap.code not in acked_codes:
            return True
    return False


def save_gaps(
    repo: GovernanceRepository,
    signal_id: str,
    gaps: list[DataGap],
) -> Path:
    """Persist gap artifacts to data/governance/data_gaps/YYYY-MM-DD/{signal_id}.json."""
    return repo.save_artifact("data_gaps", signal_id, gaps)


def save_acknowledged_gaps(
    repo: GovernanceRepository,
    signal_id: str,
    acknowledged: list[AcknowledgedGap],
) -> Path:
    """Persist acknowledged gap artifacts to data/governance/acknowledged_gaps/YYYY-MM-DD/{signal_id}.json."""
    return repo.save_artifact("acknowledged_gaps", signal_id, acknowledged)
