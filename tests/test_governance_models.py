"""Phase 0: Governance baseline models and repository tests."""
import json
import os
from pathlib import Path

import pytest

# Force project root on path so src/governance imports work
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "governance"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ── helpers ──

def load_json_fixture(name: str) -> dict:
    path = FIXTURES / name
    assert path.is_file(), f"missing fixture {path}"
    return json.loads(path.read_text(encoding="utf-8"))


# ── tests ──

def test_gitignore_blocks_governance_data_dir():
    """data/governance/ must be in .gitignore so runtime artifacts are never committed."""
    gi = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/governance" in gi, ".gitignore must contain data/governance"


def test_models_importable():
    from src.governance.models import (
        AcknowledgedGap,
        DataGap,
        EvidenceRef,
        SignalCandidate,
        SignalPackage,
    )
    # All symbols exist
    assert AcknowledgedGap is not None
    assert DataGap is not None
    assert EvidenceRef is not None
    assert SignalCandidate is not None
    assert SignalPackage is not None


def test_valid_candidate_loads_from_fixture():
    from src.governance.models import EvidenceRef, SignalCandidate

    raw = load_json_fixture("signal_candidate_valid.json")
    candidate = SignalCandidate(
        signal_id=raw["signal_id"],
        ticker=raw["ticker"],
        asset_name=raw.get("asset_name"),
        generated_at=raw["generated_at"],
        source_tweet_ids=raw["source_tweet_ids"],
        source_usernames=raw["source_usernames"],
        stance=raw.get("stance"),
        signal_score=raw.get("signal_score"),
        confidence=raw.get("confidence"),
        evidence=[
            EvidenceRef(**e) for e in raw.get("evidence", [])
        ],
        raw_payload=raw.get("raw_payload", {}),
    )
    assert candidate.signal_id == "NVDA-20260612-001"
    assert candidate.ticker == "NVDA"
    assert len(candidate.evidence) == 3
    assert candidate.stance == "bullish"


def test_no_evidence_candidate_is_valid_but_cannot_generate_package():
    from src.governance.models import EvidenceRef, SignalCandidate

    raw = load_json_fixture("signal_candidate_no_evidence.json")
    candidate = SignalCandidate(
        signal_id=raw["signal_id"],
        ticker=raw["ticker"],
        asset_name=raw.get("asset_name"),
        generated_at=raw["generated_at"],
        source_tweet_ids=raw["source_tweet_ids"],
        source_usernames=raw["source_usernames"],
        stance=raw.get("stance"),
        signal_score=raw.get("signal_score"),
        confidence=raw.get("confidence"),
        evidence=[
            EvidenceRef(**e) for e in raw.get("evidence", [])
        ],
        raw_payload=raw.get("raw_payload", {}),
    )
    # Candidate itself is still valid as a data structure
    assert candidate.signal_id == "NVDA-20260612-003"
    # But evidence is empty — a future gate MUST block package generation
    assert len(candidate.evidence) == 0


def test_repository_saves_and_loads_candidate():
    """Repository can persist and reload a SignalCandidate via JSON artifact."""
    import uuid
    from datetime import datetime, timezone

    from src.governance.models import EvidenceRef, SignalCandidate
    from src.governance.repository import GovernanceRepository

    repo = GovernanceRepository(base_dir=PROJECT_ROOT / "data" / "governance")
    candidate = SignalCandidate(
        signal_id=f"test-{uuid.uuid4().hex[:8]}",
        ticker="AAPL",
        asset_name="Apple Inc.",
        generated_at=datetime.now(timezone.utc),
        source_tweet_ids=["t_1"],
        source_usernames=["test_user"],
        stance="neutral",
        signal_score=0.55,
        confidence="moderate",
        evidence=[
            EvidenceRef(
                source_type="tweet",
                source_id="t_1",
            ),
        ],
        raw_payload={},
    )
    saved_path = repo.save_candidate(candidate)
    assert saved_path.is_file()

    loaded = repo.load_candidate(candidate.signal_id)
    assert loaded.signal_id == candidate.signal_id
    assert loaded.ticker == "AAPL"
    assert len(loaded.evidence) == 1


def test_repository_base_dir_is_inside_data_governance():
    from src.governance.repository import GovernanceRepository

    repo = GovernanceRepository(base_dir=PROJECT_ROOT / "data" / "governance")
    assert "data" in str(repo.base_dir)
    assert "governance" in str(repo.base_dir)
