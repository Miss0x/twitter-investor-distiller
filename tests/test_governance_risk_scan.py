"""Phase 3: Risk Scan tests."""
from pathlib import Path
import json

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


# ── tests ──

def test_risk_scan_detects_user_text_triggers():
    from src.governance.risk_scan import scan_user_text

    result = scan_user_text("群里老师说这只票必涨，内幕消息翻倍")
    assert result["risk_level"] in ("caution", "high_risk")
    assert len(result["triggers_hit"]) >= 2


def test_risk_scan_clean_text_is_safe():
    from src.governance.risk_scan import scan_user_text

    result = scan_user_text("NVDA 最新的 earnings 表现如何")
    assert result["risk_level"] == "safe"


def test_risk_scan_candidate_with_clean_signal_is_safe_or_notice():
    from src.governance.risk_scan import run_risk_scan

    candidate = _make_valid()
    result = run_risk_scan(candidate)
    assert result["risk_level"] in ("safe", "notice")


def test_risk_scan_output_has_machine_readable_dimensions():
    from src.governance.risk_scan import run_risk_scan

    candidate = _make_valid()
    result = run_risk_scan(candidate)
    assert "triggering_signals" in result
    assert "risk_level" in result
    assert "total_score" in result


def test_high_risk_blocks_strong_push():
    from src.governance.risk_scan import run_risk_scan

    # Create a candidate that triggers high risk
    candidate = _make_valid()
    result = run_risk_scan(candidate, user_question="老师推荐的必涨十倍股，已经在群里通知了")
    # If multiple triggers fire, total_score should be higher
    assert isinstance(result["total_score"], (int, float))
    # high_risk should mean no strong push
    if result["risk_level"] == "high_risk":
        assert not result.get("allow_strong_push", True)
    # The field must exist
    assert "allow_strong_push" in result


def test_scan_candidate_text_extracts_excerpts():
    from src.governance.risk_scan import _extract_candidate_text

    candidate = _make_valid()
    text = _extract_candidate_text(candidate)
    assert "NVDA" in text.upper()
