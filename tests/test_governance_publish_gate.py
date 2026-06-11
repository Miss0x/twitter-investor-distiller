"""Phase 5-6: Debate, Publish Gate, and Package Builder tests."""
import json
from pathlib import Path
from datetime import datetime, timezone

import pytest

sys_path_hack = str(Path(__file__).resolve().parent.parent)
import sys
sys.path.insert(0, sys_path_hack)

from src.governance.models import (
    AcknowledgedGap,
    DataGap,
    EvidenceRef,
    SignalCandidate,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "governance"


def load_json_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _make_valid() -> SignalCandidate:
    raw = load_json_fixture("signal_candidate_valid.json")
    return SignalCandidate(
        signal_id=raw["signal_id"],
        ticker=raw["ticker"],
        asset_name=raw.get("asset_name"),
        generated_at=raw["generated_at"],
        source_tweet_ids=raw["source_tweet_ids"],
        source_usernames=raw["source_usernames"],
        stance=raw.get("stance"),
        signal_score=raw.get("signal_score"),
        confidence=raw.get("confidence"),
        evidence=[EvidenceRef(**e) for e in raw.get("evidence", [])],
        raw_payload=raw.get("raw_payload", {}),
    )


def _make_no_evidence() -> SignalCandidate:
    raw = load_json_fixture("signal_candidate_no_evidence.json")
    return SignalCandidate(
        signal_id=raw["signal_id"],
        ticker=raw["ticker"],
        asset_name=raw.get("asset_name"),
        generated_at=raw["generated_at"],
        source_tweet_ids=raw["source_tweet_ids"],
        source_usernames=raw["source_usernames"],
        stance=raw.get("stance"),
        signal_score=raw.get("signal_score"),
        confidence=raw.get("confidence"),
        evidence=[EvidenceRef(**e) for e in raw.get("evidence", [])],
        raw_payload=raw.get("raw_payload", {}),
    )


def _mock_panel() -> dict:
    return {
        "reviews": [
            {"group_id": "value_quality", "persona_label": "Buffett", "stance": "bullish", "score": 0.8, "evidence_used": ["tweet_001"]},
            {"group_id": "growth_tech", "persona_label": "Cathie", "stance": "bullish", "score": 0.75, "evidence_used": ["tweet_001"]},
            {"group_id": "risk_control", "persona_label": "Devil", "stance": "bearish", "score": 0.6, "evidence_used": [], "missing_evidence": ["valuation"]},
            {"group_id": "source_forensics", "persona_label": "Inspector", "stance": "neutral", "score": 0.5, "evidence_used": ["tweet_001"]},
        ],
        "aggregate_stance": "bullish",
        "aggregate_score": 0.66,
    }


def _mock_quality_pass() -> dict:
    return {"status": "pass", "checks": []}


def _mock_quality_block() -> dict:
    return {"status": "block", "checks": [{"code": "no_evidence", "severity": "critical"}]}


def _mock_risk_safe() -> dict:
    return {"risk_level": "safe", "total_score": 0, "allow_strong_push": True}


# ── debate tests ──

def test_debate_splits_into_bull_and_bear_from_panel():
    from src.governance.debate import run_debate

    panel = _mock_panel()
    result = run_debate(panel)
    assert "bull" in result
    assert "bear" in result
    assert result["bull"]["confidence"] > 0
    assert result["bear"]["confidence"] > 0


def test_debate_produces_final_stance():
    from src.governance.debate import run_debate

    result = run_debate(_mock_panel())
    assert result["final_stance"] in ("bullish", "bearish", "neutral", "insufficient_data")


def test_debate_includes_uncertainties():
    from src.governance.debate import run_debate

    result = run_debate(_mock_panel())
    assert isinstance(result["rebuttal"]["remaining_uncertainties"], list)


# ── publish gate tests ──

def test_publish_gate_blocks_on_quality_block():
    from src.governance.publish_gate import run_publish_gate

    result = run_publish_gate(
        quality=_mock_quality_block(),
        panel=_mock_panel(),
        debate={"final_stance": "neutral"},
        risk=_mock_risk_safe(),
        data_gaps=[DataGap(code="no_evidence", message="test", severity="critical", required_for_publish=True)],
        acknowledged_gaps=[],
    )
    assert result["status"] == "block"


def test_publish_gate_blocks_on_unacknowledged_gaps():
    from src.governance.publish_gate import run_publish_gate

    result = run_publish_gate(
        quality=_mock_quality_pass(),
        panel=_mock_panel(),
        debate={"final_stance": "neutral"},
        risk=_mock_risk_safe(),
        data_gaps=[DataGap(code="no_evidence", message="test", severity="critical", required_for_publish=True)],
        acknowledged_gaps=[],
    )
    assert result["status"] == "block"


def test_publish_gate_passes_clean_signal():
    from src.governance.publish_gate import run_publish_gate

    result = run_publish_gate(
        quality=_mock_quality_pass(),
        panel=_mock_panel(),
        debate={"final_stance": "bullish"},
        risk=_mock_risk_safe(),
        data_gaps=[],
        acknowledged_gaps=[],
    )
    assert result["status"] == "pass"


# ── package builder tests ──

def test_package_builder_produces_signal_package():
    from src.governance.package_builder import build_package

    candidate = _make_valid()
    quality = _mock_quality_pass()
    publish_review = {"status": "pass", "issues": [], "critical_count": 0}

    package = build_package(
        candidate=candidate,
        quality=quality,
        data_gaps=[],
        acknowledged_gaps=[],
        panel=_mock_panel(),
        debate={"final_stance": "bullish"},
        risk=_mock_risk_safe(),
        publish_review=publish_review,
    )

    assert package.signal_id == candidate.signal_id
    assert package.publish_status == "pass"
    assert len(package.evidence) == len(candidate.evidence)
    assert package.can_publish() is True


def test_package_builder_persists_with_repo():
    from src.governance.package_builder import build_package
    from src.governance.repository import GovernanceRepository

    candidate = _make_valid()
    repo = GovernanceRepository(base_dir=PROJECT_ROOT / "data" / "governance")
    publish_review = {"status": "pass", "issues": [], "critical_count": 0}

    package = build_package(
        candidate=candidate,
        quality=_mock_quality_pass(),
        data_gaps=[],
        acknowledged_gaps=[],
        panel=_mock_panel(),
        debate={"final_stance": "bullish"},
        risk=_mock_risk_safe(),
        publish_review=publish_review,
        repo=repo,
    )

    # Reload
    loaded = repo.load_package(package.signal_id)
    assert loaded.signal_id == candidate.signal_id
    assert loaded.publish_status == "pass"


def test_blocked_package_cannot_publish():
    from src.governance.package_builder import build_package

    candidate = _make_valid()
    publish_review = {"status": "block", "issues": [{"code": "critical"}], "critical_count": 1}

    package = build_package(
        candidate=candidate,
        quality=_mock_quality_pass(),
        data_gaps=[],
        acknowledged_gaps=[],
        panel={},
        debate={},
        risk=_mock_risk_safe(),
        publish_review=publish_review,
    )

    assert package.can_publish() is False
    assert package.is_blocked() is True
