"""User-facing governance gap actions.

These functions implement manual risk acceptance/revocation and always rerun
GovernanceRunner so Web state never diverges from backend gate results.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.governance.audit import append_gap_event
from src.governance.models import AcknowledgedGap
from src.governance.repository import GovernanceRepository
from src.governance.runner import run_governance_for_candidate


_MAX_EXPIRES_HOURS = 168


def _require_reason(reason: str) -> str:
    cleaned = (reason or "").strip()
    if not cleaned:
        raise ValueError("请简单说明为什么暂时接受这个风险")
    return cleaned


def _expires_at(now: datetime, expires_in_hours: int) -> str:
    try:
        hours = int(expires_in_hours)
    except (TypeError, ValueError) as exc:
        raise ValueError("请选择重新检查时间") from exc
    if hours < 1 or hours > _MAX_EXPIRES_HOURS:
        raise ValueError("重新检查时间必须在 1 到 168 小时之间")
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now + timedelta(hours=hours)).isoformat()


def _load_current_package(repo: GovernanceRepository, signal_id: str):
    package = repo.load_latest_package_for_signal(signal_id)
    if package is None:
        raise ValueError("还没有可处理的信号，请先运行一次治理检查")
    if package.candidate is None:
        raise ValueError("这条信号缺少原始信息，无法重新检查")
    return package


def _ensure_gap_exists(package, gap_code: str) -> None:
    if not any(gap.code == gap_code for gap in package.data_gaps):
        raise ValueError("没有找到需要处理的数据问题")


def acknowledge_gap_for_signal(
    repo: GovernanceRepository,
    signal_id: str,
    gap_code: str,
    reason: str,
    expires_in_hours: int,
    acknowledged_by: str = "local_user",
    now: datetime | None = None,
) -> dict:
    """Acknowledge one data gap, then rerun governance for the signal."""
    now = now or datetime.now(timezone.utc)
    cleaned_reason = _require_reason(reason)
    package = _load_current_package(repo, signal_id)
    _ensure_gap_exists(package, gap_code)

    existing = [ack for ack in package.acknowledged_gaps if ack.code != gap_code]
    existing.append(
        AcknowledgedGap(
            code=gap_code,
            reason=cleaned_reason,
            acknowledged_by=acknowledged_by,
            acknowledged_at=now.isoformat(),
            expires_at=_expires_at(now, expires_in_hours),
        )
    )

    append_gap_event(
        repo,
        "gap_acknowledged",
        signal_id,
        gap_code,
        cleaned_reason,
        actor=acknowledged_by,
        created_at=now,
    )
    result = run_governance_for_candidate(
        package.candidate,
        repo=repo,
        acknowledged_gaps=existing,
        extra_data_gaps=package.data_gaps,
        now=now,
    )
    if result.error:
        raise ValueError("操作没有保存成功")
    return {"ok": True, "signal_id": signal_id, "publish_status": result.publish_status}


def revoke_gap_acknowledgement(
    repo: GovernanceRepository,
    signal_id: str,
    gap_code: str,
    reason: str,
    acknowledged_by: str = "local_user",
    now: datetime | None = None,
) -> dict:
    """Remove an active acknowledgement and rerun governance."""
    cleaned_reason = _require_reason(reason)
    package = _load_current_package(repo, signal_id)
    _ensure_gap_exists(package, gap_code)

    now = now or datetime.now(timezone.utc)
    remaining = [ack for ack in package.acknowledged_gaps if ack.code != gap_code]
    append_gap_event(repo, "gap_revoked", signal_id, gap_code, cleaned_reason, actor=acknowledged_by, created_at=now)
    result = run_governance_for_candidate(
        package.candidate,
        repo=repo,
        acknowledged_gaps=remaining,
        extra_data_gaps=package.data_gaps,
        now=now,
    )
    if result.error:
        raise ValueError("操作没有保存成功")
    return {"ok": True, "signal_id": signal_id, "publish_status": result.publish_status}
