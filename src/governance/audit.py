"""Append-only audit events for governance user actions."""

from __future__ import annotations

from datetime import datetime, timezone

from src.governance.repository import GovernanceRepository


def append_gap_event(
    repo: GovernanceRepository,
    event_type: str,
    signal_id: str,
    gap_code: str,
    reason: str,
    actor: str = "local_user",
    created_at: datetime | None = None,
) -> None:
    created_at = created_at or datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    repo.append_audit_event(
        signal_id,
        {
            "event_type": event_type,
            "signal_id": signal_id,
            "gap_code": gap_code,
            "actor": actor,
            "reason": reason,
            "created_at": created_at.isoformat(),
        },
        signal_date=created_at.date().isoformat(),
    )
