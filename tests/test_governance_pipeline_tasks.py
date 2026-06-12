"""Phase 7: PipelineTask Integration tests."""
import json
from pathlib import Path

import pytest

sys_path_hack = str(Path(__file__).resolve().parent.parent)
import sys
sys.path.insert(0, sys_path_hack)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "governance"


def load_json_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ── tests ──

def test_governance_task_types_are_recognized_but_fail_closed_without_payload():
    """All governance task types are recognized, but missing payload fails closed."""
    from src.pipeline.task_executor import _dispatch_governance_task

    known_types = [
        "governance_candidate",
        "governance_quality",
        "governance_risk",
        "governance_panel",
        "governance_debate",
        "governance_publish",
        "governance_report",
        "governance_run",
    ]
    for task_type in known_types:
        result = _dispatch_governance_task(task_type, {})
        assert "error" in result, f"{task_type} should fail closed without payload"
        assert "未知治理任务类型" not in result["error"]


def test_governance_full_pipeline_from_candidate_to_package():
    """End-to-end: create a SignalCandidate, run full governance, get SignalPackage."""
    from src.governance.models import EvidenceRef, SignalCandidate
    from src.governance.data_gaps import collect_data_gaps
    from src.governance.quality_gate import run_quality_gate
    from src.governance.panel_review import run_panel_review
    from src.governance.debate import run_debate
    from src.governance.risk_scan import run_risk_scan
    from src.governance.publish_gate import run_publish_gate
    from src.governance.package_builder import build_package

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

    gaps = collect_data_gaps(candidate)
    quality = run_quality_gate(candidate)
    panel = run_panel_review(candidate)
    debate = run_debate(panel)
    risk = run_risk_scan(candidate)
    publish_review = run_publish_gate(quality, panel, debate, risk, gaps, [])
    package = build_package(candidate, quality, gaps, [], panel, debate, risk, publish_review)

    assert package.signal_id == candidate.signal_id
    assert package.publish_status in ("pass", "warn", "block")
    assert len(package.evidence) == 3
    assert package.summary != ""


def test_unknown_task_type_still_errors():
    """Existing behavior: unknown task types return error."""
    from src.pipeline.task_executor import _dispatch_governance_task

    result = _dispatch_governance_task("unknown_type_xyz", {})
    assert "error" in result
