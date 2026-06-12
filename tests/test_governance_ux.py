"""Phase 12: governance UX tests."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from src.governance.models import AcknowledgedGap, DataGap, EvidenceRef, SignalCandidate, SignalPackage
from src.governance.repository import GovernanceRepository


def _candidate(signal_id: str = "SIG-UX-1") -> SignalCandidate:
    return SignalCandidate(
        signal_id=signal_id,
        ticker="NVDA",
        generated_at="2026-06-12T00:00:00+00:00",
        evidence=[EvidenceRef(source_type="tweet", source_id="tweet-1", excerpt="Demand remains strong")],
    )


def _package(signal_id: str = "SIG-UX-1") -> SignalPackage:
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
                suggested_fix="Fetch price window",
                evidence_needed=["price"],
            ),
            DataGap(
                code="unknown_future_gap",
                message="Unknown internal gap",
                severity="warning",
                required_for_publish=False,
            ),
        ],
    )


def test_quality_gate_card_maps_gap_codes_to_natural_chinese(tmp_path, monkeypatch):
    from src.cards.governance_cards import QualityGateCard

    repo = GovernanceRepository(base_dir=tmp_path / "governance")
    repo.save_package(_package())
    monkeypatch.setattr("src.cards.governance_cards.GovernanceRepository", lambda: repo)

    data = QualityGateCard().get_data()

    assert data["empty"] is False
    assert data["data_gaps"][0]["title"] == "缺少价格背景"
    assert data["data_gaps"][0]["status_label"] == "待处理"
    assert data["data_gaps"][0]["action_label"] == "我知道这里缺数据，暂时接受这个风险"
    assert data["data_gaps"][0]["severity_label"] == "关键"
    assert data["data_gaps"][1]["title"] == "未知问题，请查看日志"
    html = QualityGateCard().render(data)
    visible_text = re.sub(r"<[^>]+>", " ", html)
    assert "missing_price_context" not in visible_text
    assert "unknown_future_gap" not in visible_text
    assert "缺少价格背景" in visible_text
    assert "我知道这里缺数据，暂时接受这个风险" in visible_text


def test_quality_gate_card_marks_active_acknowledgement(tmp_path, monkeypatch):
    from src.cards.governance_cards import QualityGateCard

    repo = GovernanceRepository(base_dir=tmp_path / "governance")
    package = _package("SIG-UX-ACK")
    package.acknowledged_gaps = [
        AcknowledgedGap(
            code="missing_price_context",
            reason="只作为观察线索，不作为正式买入依据",
            acknowledged_by="local_user",
            acknowledged_at=datetime.now(timezone.utc).isoformat(),
            expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        )
    ]
    repo.save_package(package)
    monkeypatch.setattr("src.cards.governance_cards.GovernanceRepository", lambda: repo)

    data = QualityGateCard().get_data()

    assert data["data_gaps"][0]["status_label"] == "已暂时接受"
    assert data["data_gaps"][0]["reason"] == "只作为观察线索，不作为正式买入依据"
    assert data["data_gaps"][0]["revoke_label"] == "不再接受这个风险"


def test_quality_gate_card_marks_expired_acknowledgement(tmp_path, monkeypatch):
    from src.cards.governance_cards import QualityGateCard

    repo = GovernanceRepository(base_dir=tmp_path / "governance")
    package = _package("SIG-UX-EXPIRED")
    package.acknowledged_gaps = [
        AcknowledgedGap(
            code="missing_price_context",
            reason="临时接受",
            acknowledged_by="local_user",
            acknowledged_at="2026-06-12T00:00:00+00:00",
            expires_at="2026-06-12T01:00:00+00:00",
        )
    ]
    repo.save_package(package)
    monkeypatch.setattr("src.cards.governance_cards.GovernanceRepository", lambda: repo)

    data = QualityGateCard().get_data(now=datetime(2026, 6, 12, 2, tzinfo=timezone.utc))

    assert data["data_gaps"][0]["status_label"] == "已过期，需要重新确认"
