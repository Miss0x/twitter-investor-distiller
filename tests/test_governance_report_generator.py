"""Phase 9: HTML Report Generator tests."""
import json
from pathlib import Path

import pytest

sys_path_hack = str(Path(__file__).resolve().parent.parent)
import sys
sys.path.insert(0, sys_path_hack)

from src.governance.models import EvidenceRef, SignalCandidate, SignalPackage


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "governance"


def load_json_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _make_passed_package() -> SignalPackage:
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
        evidence=[EvidenceRef(**e) for e in raw.get("evidence", [])],
        raw_payload=raw.get("raw_payload", {}),
    )
    return SignalPackage(
        signal_id=candidate.signal_id,
        ticker=candidate.ticker,
        generated_at="2026-06-12T00:00:00",
        publish_status="pass",
        summary="Test summary: NVDA bullish signal",
        candidate=candidate,
        evidence=candidate.evidence,
    )


def _make_blocked_package() -> SignalPackage:
    return SignalPackage(
        signal_id="BLOCKED-001",
        ticker="FAKE",
        generated_at="2026-06-12T00:00:00",
        publish_status="block",
        summary="",
    )


# ── tests ──

def test_report_generator_refuses_blocked_package():
    from src.governance.report_generator import generate_html_report

    pkg = _make_blocked_package()
    result = generate_html_report(pkg)
    assert result is None


def test_report_generator_accepts_passed_package():
    from src.governance.report_generator import generate_html_report

    pkg = _make_passed_package()
    result = generate_html_report(pkg)
    assert result is not None
    html = result if isinstance(result, str) else ""
    assert "<html" in html.lower() or "NVDA" in html


def test_report_persists_to_governance_dir():
    from src.governance.report_generator import render_and_save_report
    from src.governance.repository import GovernanceRepository

    pkg = _make_passed_package()
    repo = GovernanceRepository(base_dir=PROJECT_ROOT / "data" / "governance")
    path = render_and_save_report(pkg, repo)

    assert path is not None
    assert path.is_file()
    assert "reports" in str(path)
    assert pkg.signal_id in str(path)


def test_report_contents_include_evidence_and_summary():
    from src.governance.report_generator import generate_html_report

    pkg = _make_passed_package()
    html = generate_html_report(pkg) or ""
    assert "NVDA" in html
    assert "bullish" in html.lower() or "Test summary" in html
