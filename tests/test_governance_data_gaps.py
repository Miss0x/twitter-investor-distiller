"""Phase 1: DataGap Registry tests."""
import json
import uuid
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
    path = FIXTURES / name
    return json.loads(path.read_text(encoding="utf-8"))


def _make_candidate_no_price() -> SignalCandidate:
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


def _make_candidate_no_evidence() -> SignalCandidate:
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


# ── tests ──

def test_collect_data_gaps_detects_missing_price():
    from src.governance.data_gaps import collect_data_gaps

    candidate = _make_candidate_no_price()
    gaps = collect_data_gaps(candidate)

    assert len(gaps) >= 1
    missing_price = [g for g in gaps if g.code == "missing_price_context"]
    assert len(missing_price) == 1
    assert missing_price[0].required_for_publish is False


def test_collect_data_gaps_detects_no_evidence():
    from src.governance.data_gaps import collect_data_gaps

    candidate = _make_candidate_no_evidence()
    gaps = collect_data_gaps(candidate)

    no_evidence = [g for g in gaps if g.code == "no_evidence"]
    assert len(no_evidence) == 1
    assert no_evidence[0].required_for_publish is True


def test_required_open_gaps_block_publish_readiness():
    from src.governance.data_gaps import collect_data_gaps, has_blocking_gaps

    candidate = _make_candidate_no_evidence()
    gaps = collect_data_gaps(candidate)

    # no acknowledged gaps => blocking gaps should block
    assert has_blocking_gaps(gaps, []) is True


def test_acknowledged_required_gaps_allow_publish():
    from src.governance.data_gaps import collect_data_gaps, has_blocking_gaps

    candidate = _make_candidate_no_evidence()
    gaps = collect_data_gaps(candidate)

    acknowledged = [
        AcknowledgedGap(
            code="no_evidence",
            reason="Only 1 tweet available, cannot get more sources",
            acknowledged_by="user",
            acknowledged_at=datetime.now(timezone.utc).isoformat(),
        )
    ]
    assert has_blocking_gaps(gaps, acknowledged) is False


def test_acknowledge_gap_creates_artifact():
    from src.governance.data_gaps import acknowledge_gap

    ack = acknowledge_gap(
        signal_id="test-ack-001",
        gap_code="missing_price_context",
        reason="No price feed for this asset",
        acknowledged_by="user",
    )
    assert ack.code == "missing_price_context"
    assert ack.acknowledged_by == "user"
    assert ack.reason is not None


def test_gap_artifacts_persist_to_governance_dir():
    from src.governance.data_gaps import save_gaps, save_acknowledged_gaps, collect_data_gaps
    from src.governance.repository import GovernanceRepository

    repo = GovernanceRepository(base_dir=PROJECT_ROOT / "data" / "governance")
    candidate = _make_candidate_no_price()
    gaps = collect_data_gaps(candidate)

    gap_path = save_gaps(repo, candidate.signal_id, gaps)
    assert gap_path is not None
    assert gap_path.is_file()

    ack = AcknowledgedGap(
        code="missing_price_context",
        reason="test",
        acknowledged_by="test",
        acknowledged_at=datetime.now(timezone.utc).isoformat(),
    )
    ack_path = save_acknowledged_gaps(repo, candidate.signal_id, [ack])
    assert ack_path is not None
    assert ack_path.is_file()

    # verify paths are inside data/governance/
    assert "data" in str(gap_path)
    assert "governance" in str(gap_path)
    assert "data_gaps" in str(gap_path)
    assert "acknowledged_gaps" in str(ack_path)
