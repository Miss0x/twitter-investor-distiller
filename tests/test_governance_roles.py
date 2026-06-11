"""Phase 4: Role Config and Panel Review tests."""
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


# ── role config tests ──

def test_role_config_loads_all_eight_groups():
    from src.governance.roles import load_role_config

    config = load_role_config()
    assert len(config.role_groups) == 8
    expected = {
        "value_quality",
        "growth_tech",
        "macro_liquidity",
        "trend_momentum",
        "hot_money_sentiment",
        "risk_control",
        "source_forensics",
        "ai_chokepoint",
    }
    assert set(config.role_groups.keys()) == expected


def test_every_role_group_has_objective_and_at_least_one_persona():
    from src.governance.roles import load_role_config

    config = load_role_config()
    for group in config.role_groups.values():
        assert group.objective, f"{group.id} missing objective"
        assert len(group.personas) >= 1, f"{group.id} has no personas"


def test_every_persona_has_required_evidence():
    from src.governance.roles import load_role_config

    config = load_role_config()
    for group in config.role_groups.values():
        for persona in group.personas:
            assert isinstance(persona.required_evidence, list), (
                f"{persona.id} required_evidence is not a list"
            )


# ── panel review tests ──

def test_panel_review_produces_reviews_for_all_personas():
    from src.governance.panel_review import run_panel_review
    from src.governance.roles import load_role_config

    config = load_role_config()
    candidate = _make_valid()
    result = run_panel_review(candidate, config)

    total_personas = sum(len(g.personas) for g in config.role_groups.values())
    assert len(result["reviews"]) == total_personas


def test_panel_review_aggregate_stance_is_valid():
    from src.governance.panel_review import run_panel_review

    candidate = _make_valid()
    result = run_panel_review(candidate)
    assert result["aggregate_stance"] in (
        "bullish", "bearish", "neutral", "avoid", "insufficient_data"
    )


def test_panel_review_returns_counts():
    from src.governance.panel_review import run_panel_review

    candidate = _make_valid()
    result = run_panel_review(candidate)
    total = (
        result["bullish_count"]
        + result["bearish_count"]
        + result["neutral_count"]
        + result["insufficient_data_count"]
    )
    assert total == len(result["reviews"])
