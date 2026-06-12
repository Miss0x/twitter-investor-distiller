"""Phase 11: end-to-end governance closure contract tests."""

from __future__ import annotations

from dataclasses import is_dataclass
from datetime import datetime, timedelta, timezone

import pytest

from src.governance.data_gaps import has_blocking_gaps
from src.governance.models import AcknowledgedGap, DataGap, EvidenceRef, SignalCandidate, SignalPackage
from src.governance.push_policy import should_allow_strong_push
from src.governance.report_generator import generate_html_report
from src.governance.repository import GovernanceRepository


def _repo(tmp_path) -> GovernanceRepository:
    return GovernanceRepository(base_dir=tmp_path / "governance")


def _valid_candidate(signal_id: str = "SIG-E2E-VALID") -> SignalCandidate:
    return SignalCandidate(
        signal_id=signal_id,
        ticker="NVDA",
        asset_name="NVIDIA",
        generated_at="2026-06-12T00:00:00+00:00",
        source_tweet_ids=["tweet-1"],
        source_usernames=["TJ_Research"],
        stance="bullish",
        signal_score=0.82,
        confidence="high",
        evidence=[
            EvidenceRef(
                source_type="tweet",
                source_id="tweet-1",
                url="https://x.com/TJ_Research/status/tweet-1",
                title="Original tweet",
                excerpt="NVDA demand remains strong.",
                timestamp="2026-06-12T00:00:00+00:00",
                reliability=0.8,
            ),
            EvidenceRef(
                source_type="analysis",
                source_id="analysis-1",
                title="LLM analysis",
                excerpt="The author is bullish with concrete demand comments.",
                reliability=0.7,
            ),
            EvidenceRef(
                source_type="price",
                source_id="price-1",
                title="Price context",
                excerpt="Price context exists for the signal window.",
                reliability=0.9,
            ),
        ],
        raw_payload={"source": "test"},
    )


def _no_evidence_candidate() -> SignalCandidate:
    return SignalCandidate(
        signal_id="SIG-E2E-NO-EVIDENCE",
        ticker="FAKE",
        generated_at="2026-06-12T00:00:00+00:00",
        source_tweet_ids=[],
        source_usernames=[],
        stance="bullish",
        evidence=[],
    )


def test_valid_signal_flows_to_publishable_package(tmp_path):
    from src.governance.runner import run_governance_for_candidate

    repo = _repo(tmp_path)
    result = run_governance_for_candidate(_valid_candidate(), repo=repo, generate_report=True)

    assert result.error is None
    assert result.publish_status in {"pass", "warn"}
    assert result.package_path is not None

    package = repo.load_package("SIG-E2E-VALID")
    assert package.can_publish()
    assert package.candidate is not None
    assert all(is_dataclass(gap) for gap in package.data_gaps)
    assert all(is_dataclass(ack) for ack in package.acknowledged_gaps)


def test_missing_evidence_blocks_all_downstream_outputs(tmp_path):
    from src.governance.runner import run_governance_for_candidate

    repo = _repo(tmp_path)
    result = run_governance_for_candidate(_no_evidence_candidate(), repo=repo, generate_report=True)

    assert result.publish_status == "block"
    package = repo.load_package("SIG-E2E-NO-EVIDENCE")
    assert package.is_blocked()
    assert package.quality["status"] == "block"
    assert generate_html_report(package) is None
    allowed, _reason = should_allow_strong_push(package.publish_status, package.risk.get("risk_level", "unknown"))
    assert allowed is False


def test_acknowledged_required_gap_allows_publish_until_expiry():
    gap = DataGap(code="no_evidence", message="Missing evidence", severity="critical", required_for_publish=True)
    ack = AcknowledgedGap(
        code="no_evidence",
        reason="Accepted for manual review",
        acknowledged_by="tester",
        acknowledged_at="2026-06-12T00:00:00+00:00",
        expires_at="2026-06-13T00:00:00+00:00",
    )

    assert has_blocking_gaps([gap], [ack], now=datetime(2026, 6, 12, tzinfo=timezone.utc)) is False


def test_expired_acknowledged_gap_blocks_again():
    gap = DataGap(code="no_evidence", message="Missing evidence", severity="critical", required_for_publish=True)
    ack = AcknowledgedGap(
        code="no_evidence",
        reason="Accepted for manual review",
        acknowledged_by="tester",
        acknowledged_at="2026-06-12T00:00:00+00:00",
        expires_at="2026-06-12T01:00:00+00:00",
    )

    assert has_blocking_gaps([gap], [ack], now=datetime(2026, 6, 12, 2, tzinfo=timezone.utc)) is True


def test_high_risk_package_never_strong_pushes():
    allowed, reason = should_allow_strong_push("pass", "high_risk")

    assert allowed is False
    assert "risk" in reason.lower()


def test_unknown_state_never_strong_pushes():
    allowed, reason = should_allow_strong_push("unknown", "unknown")

    assert allowed is False
    assert reason


def test_html_report_escapes_untrusted_evidence():
    candidate = _valid_candidate("SIG-E2E-XSS")
    candidate.evidence = [
        EvidenceRef(
            source_type="tweet",
            source_id="tweet-xss",
            url="javascript:alert(1)",
            title="<b>bad</b>",
            excerpt='<script>alert("x")</script>',
        )
    ]
    package = SignalPackage(
        signal_id=candidate.signal_id,
        ticker="<NVDA>",
        generated_at="2026-06-12T00:00:00+00:00",
        publish_status="pass",
        summary='<img src=x onerror=alert("x")>',
        candidate=candidate,
        evidence=candidate.evidence,
    )

    html = generate_html_report(package) or ""

    assert "<script>" not in html
    assert "javascript:alert" not in html
    assert "&lt;script&gt;" in html


def test_pipeline_governance_task_runs_real_chain(tmp_path):
    from src.pipeline.task_executor import _dispatch_governance_task

    result = _dispatch_governance_task(
        "governance_run",
        {"candidate": _valid_candidate("SIG-E2E-PIPELINE"), "repo_base_dir": str(tmp_path / "governance")},
    )

    assert result["ok"] is True
    assert result["publish_status"] in {"pass", "warn"}
    assert "桩实现" not in result.get("message", "")
    assert result["package_path"]


def test_dashboard_cards_read_latest_package_artifacts(tmp_path, monkeypatch):
    from src.governance.runner import run_governance_for_candidate
    from src.cards.governance_cards import PanelReviewCard, PublishReviewCard, QualityGateCard, RiskAlertsCard

    repo = _repo(tmp_path)
    run_governance_for_candidate(_valid_candidate("SIG-E2E-CARDS"), repo=repo)
    monkeypatch.setattr("src.cards.governance_cards.GovernanceRepository", lambda: repo)

    quality = QualityGateCard().get_data()
    risk = RiskAlertsCard().get_data()
    panel = PanelReviewCard().get_data()
    publish = PublishReviewCard().get_data()

    assert quality["empty"] is False
    assert quality["signal_id"] == "SIG-E2E-CARDS"
    assert risk["empty"] is False
    assert panel["empty"] is False
    assert publish["empty"] is False
    assert publish["status"] in {"pass", "warn"}
