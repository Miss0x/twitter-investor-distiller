"""Phase 12: governance data gap action tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.governance.models import DataGap, EvidenceRef, SignalCandidate, SignalPackage
from src.governance.repository import GovernanceRepository


def _candidate(signal_id: str = "SIG-GAP-ACTION") -> SignalCandidate:
    return SignalCandidate(
        signal_id=signal_id,
        ticker="NVDA",
        generated_at="2026-06-12T00:00:00+00:00",
        evidence=[EvidenceRef(source_type="tweet", source_id="tweet-1", excerpt="Demand remains strong")],
    )


def _blocked_package(signal_id: str = "SIG-GAP-ACTION") -> SignalPackage:
    return SignalPackage(
        signal_id=signal_id,
        ticker="NVDA",
        generated_at="2026-06-12T00:00:00+00:00",
        publish_status="block",
        candidate=_candidate(signal_id),
        data_gaps=[
            DataGap(
                code="missing_price_context",
                message="Missing price context",
                severity="critical",
                required_for_publish=True,
            )
        ],
    )


def test_acknowledge_gap_requires_reason(tmp_path):
    from src.governance.gap_actions import acknowledge_gap_for_signal

    repo = GovernanceRepository(base_dir=tmp_path / "governance")
    repo.save_package(_blocked_package())

    with pytest.raises(ValueError, match="请简单说明为什么暂时接受这个风险"):
        acknowledge_gap_for_signal(
            repo=repo,
            signal_id="SIG-GAP-ACTION",
            gap_code="missing_price_context",
            reason=" ",
            expires_in_hours=72,
        )


def test_acknowledge_gap_records_reason_and_reruns_governance(tmp_path):
    from src.governance.gap_actions import acknowledge_gap_for_signal

    repo = GovernanceRepository(base_dir=tmp_path / "governance")
    repo.save_package(_blocked_package())

    result = acknowledge_gap_for_signal(
        repo=repo,
        signal_id="SIG-GAP-ACTION",
        gap_code="missing_price_context",
        reason="只作为观察线索，不作为正式买入依据",
        expires_in_hours=72,
        now=datetime(2026, 6, 12, tzinfo=timezone.utc),
    )

    assert result["ok"] is True
    package = repo.load_package("SIG-GAP-ACTION")
    assert package.acknowledged_gaps[0].reason == "只作为观察线索，不作为正式买入依据"
    assert package.acknowledged_gaps[0].expires_at == "2026-06-15T00:00:00+00:00"
    assert package.publish_status in {"pass", "warn"}


def test_revoke_gap_acknowledgement_reruns_and_blocks_again(tmp_path):
    from src.governance.gap_actions import acknowledge_gap_for_signal, revoke_gap_acknowledgement

    repo = GovernanceRepository(base_dir=tmp_path / "governance")
    repo.save_package(_blocked_package())
    acknowledge_gap_for_signal(
        repo=repo,
        signal_id="SIG-GAP-ACTION",
        gap_code="missing_price_context",
        reason="只作为观察线索，不作为正式买入依据",
        expires_in_hours=72,
        now=datetime(2026, 6, 12, tzinfo=timezone.utc),
    )

    result = revoke_gap_acknowledgement(
        repo=repo,
        signal_id="SIG-GAP-ACTION",
        gap_code="missing_price_context",
        reason="后续发现影响较大，重新阻断",
    )

    assert result["ok"] is True
    package = repo.load_package("SIG-GAP-ACTION")
    assert package.acknowledged_gaps == []
    assert package.publish_status == "block"
