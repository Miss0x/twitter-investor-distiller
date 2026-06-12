"""Phase 12: governance audit log tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from src.governance.models import DataGap, EvidenceRef, SignalCandidate, SignalPackage
from src.governance.repository import GovernanceRepository


def _package() -> SignalPackage:
    candidate = SignalCandidate(
        signal_id="SIG-AUDIT-1",
        ticker="NVDA",
        generated_at="2026-06-12T00:00:00+00:00",
        evidence=[EvidenceRef(source_type="tweet", source_id="tweet-1", excerpt="Demand remains strong")],
    )
    return SignalPackage(
        signal_id="SIG-AUDIT-1",
        ticker="NVDA",
        generated_at="2026-06-12T00:00:00+00:00",
        publish_status="block",
        candidate=candidate,
        data_gaps=[DataGap(code="missing_price_context", message="Missing price", severity="critical", required_for_publish=True)],
    )


def test_gap_acknowledge_and_revoke_append_audit_events(tmp_path):
    from src.governance.gap_actions import acknowledge_gap_for_signal, revoke_gap_acknowledgement

    repo = GovernanceRepository(base_dir=tmp_path / "governance")
    repo.save_package(_package())

    acknowledge_gap_for_signal(
        repo=repo,
        signal_id="SIG-AUDIT-1",
        gap_code="missing_price_context",
        reason="只作为观察线索",
        expires_in_hours=24,
        now=datetime(2026, 6, 12, tzinfo=timezone.utc),
    )
    revoke_gap_acknowledgement(
        repo=repo,
        signal_id="SIG-AUDIT-1",
        gap_code="missing_price_context",
        reason="重新阻断",
        now=datetime(2026, 6, 12, 1, tzinfo=timezone.utc),
    )

    paths = sorted((tmp_path / "governance" / "audit").glob("*/SIG-AUDIT-1.jsonl"))
    events = []
    for path in paths:
        events.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())

    events = sorted(events, key=lambda event: event["created_at"])
    assert [event["event_type"] for event in events] == ["gap_acknowledged", "gap_revoked"]
    assert events[0]["reason"] == "只作为观察线索"
    assert events[1]["reason"] == "重新阻断"
    assert events[0]["actor"] == "local_user"
