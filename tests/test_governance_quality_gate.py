"""Phase 2: Quality Gate tests."""
import json
from pathlib import Path

import pytest

sys_path_hack = str(Path(__file__).resolve().parent.parent)
import sys
sys.path.insert(0, sys_path_hack)

from src.governance.models import EvidenceRef, SignalCandidate


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


def _make_missing_price() -> SignalCandidate:
    raw = load_json_fixture("signal_candidate_missing_price.json")
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


# ── tests ──

def test_quality_gate_blocks_no_evidence():
    from src.governance.quality_gate import run_quality_gate

    result = run_quality_gate(_make_no_evidence())
    assert result["status"] == "block"
    assert any("evidence" in str(c).lower() for c in result["checks"])


def test_quality_gate_warns_missing_price_for_dashboard():
    from src.governance.quality_gate import run_quality_gate

    result = run_quality_gate(_make_missing_price(), push_intent="dashboard")
    assert result["status"] in ("pass", "warn")
    # At least one check should mention price
    assert any("price" in str(c).lower() for c in result["checks"])


def test_quality_gate_blocks_missing_price_for_strong_push():
    from src.governance.quality_gate import run_quality_gate

    result = run_quality_gate(_make_missing_price(), push_intent="strong_push")
    assert result["status"] == "block"


def test_quality_gate_passes_valid_candidate():
    from src.governance.quality_gate import run_quality_gate

    result = run_quality_gate(_make_valid())
    assert result["status"] == "pass"


def test_quality_gate_output_has_machine_readable_checks():
    from src.governance.quality_gate import run_quality_gate

    result = run_quality_gate(_make_no_evidence())
    assert isinstance(result["checks"], list)
    for check in result["checks"]:
        assert "code" in check
        assert "severity" in check
        assert "message" in check


def test_quality_gate_output_references_data_gap_codes():
    from src.governance.quality_gate import run_quality_gate

    result = run_quality_gate(_make_no_evidence())
    # The no_evidence gap code should appear in the quality gate output
    has_no_evidence = any(
        "no_evidence" in str(c) for c in result["checks"]
    )
    assert has_no_evidence
