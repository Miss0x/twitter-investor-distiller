"""Governance runner — orchestrates the end-to-end signal governance chain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from src.governance.data_gaps import collect_data_gaps, save_acknowledged_gaps, save_gaps
from src.governance.debate import run_debate
from src.governance.models import AcknowledgedGap, SignalCandidate
from src.governance.package_builder import build_package
from src.governance.panel_review import run_panel_review
from src.governance.publish_gate import run_publish_gate
from src.governance.quality_gate import run_quality_gate
from src.governance.repository import GovernanceRepository
from src.governance.report_generator import render_and_save_report
from src.governance.risk_scan import run_risk_scan


@dataclass(frozen=True)
class GovernanceRunResult:
    """Structured result returned by a governance run."""

    signal_id: str
    status: str
    package_path: str | None
    report_path: str | None
    publish_status: str
    error: str | None = None


def run_governance_for_candidate(
    candidate: SignalCandidate,
    repo: GovernanceRepository | None = None,
    push_intent: Literal["dashboard", "strong_push"] = "dashboard",
    acknowledged_gaps: list[AcknowledgedGap] | None = None,
    generate_report: bool = False,
    extra_data_gaps: list | None = None,
) -> GovernanceRunResult:
    """Run the full deterministic governance chain for one SignalCandidate."""
    repo = repo or GovernanceRepository()
    acknowledged_gaps = acknowledged_gaps or []

    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{candidate.signal_id}"
    steps: list[dict] = []
    started_at = datetime.now(timezone.utc).isoformat()

    try:
        candidate_path = repo.save_candidate(candidate)
        steps.append({"name": "candidate", "status": "completed", "artifact": str(candidate_path)})

        collected_gaps = collect_data_gaps(candidate)
        extra_data_gaps = extra_data_gaps or []
        seen_gap_codes = {gap.code for gap in extra_data_gaps}
        data_gaps = extra_data_gaps + [gap for gap in collected_gaps if gap.code not in seen_gap_codes]
        gaps_path = save_gaps(repo, candidate.signal_id, data_gaps)
        ack_path = save_acknowledged_gaps(repo, candidate.signal_id, acknowledged_gaps)
        steps.append({"name": "data_gaps", "status": "completed", "artifact": str(gaps_path)})
        steps.append({"name": "acknowledged_gaps", "status": "completed", "artifact": str(ack_path)})

        quality = run_quality_gate(candidate, push_intent=push_intent)
        quality_path = repo.save_artifact("quality", candidate.signal_id, quality)
        steps.append({"name": "quality", "status": "completed", "artifact": str(quality_path)})
        panel = run_panel_review(candidate)
        panel_path = repo.save_artifact("panel", candidate.signal_id, panel)
        steps.append({"name": "panel", "status": "completed", "artifact": str(panel_path)})
        debate = run_debate(panel)
        debate_path = repo.save_artifact("debate", candidate.signal_id, debate)
        steps.append({"name": "debate", "status": "completed", "artifact": str(debate_path)})
        risk = run_risk_scan(candidate)
        risk_path = repo.save_artifact("risk", candidate.signal_id, risk)
        steps.append({"name": "risk", "status": "completed", "artifact": str(risk_path)})
        publish = run_publish_gate(
            quality=quality,
            panel=panel,
            debate=debate,
            risk=risk,
            data_gaps=data_gaps,
            acknowledged_gaps=acknowledged_gaps,
        )

        publish_path = repo.save_artifact("publish", candidate.signal_id, publish)
        steps.append({"name": "publish", "status": publish["status"], "artifact": str(publish_path)})

        package = build_package(
            candidate=candidate,
            quality=quality,
            data_gaps=data_gaps,
            acknowledged_gaps=acknowledged_gaps,
            panel=panel,
            debate=debate,
            risk=risk,
            publish_review=publish,
            repo=None,
        )

        report_path = None
        if generate_report and package.can_publish():
            report = render_and_save_report(package, repo)
            if report is not None:
                report_path = str(report)
                package.html_report_path = report_path

        package_path = repo.save_package(package)
        steps.append({"name": "package", "status": "completed", "artifact": str(package_path)})
        status = "blocked" if package.is_blocked() else "completed"
        repo.save_artifact(
            "runs",
            run_id,
            {
                "run_id": run_id,
                "signal_id": candidate.signal_id,
                "started_at": started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "status": status,
                "steps": steps,
                "error": None,
            },
        )
        return GovernanceRunResult(
            signal_id=candidate.signal_id,
            status=status,
            package_path=str(package_path),
            report_path=report_path,
            publish_status=package.publish_status,
        )
    except Exception as exc:
        repo.save_artifact(
            "runs",
            run_id,
            {
                "run_id": run_id,
                "signal_id": candidate.signal_id,
                "started_at": started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "status": "failed",
                "steps": steps,
                "error": str(exc),
            },
        )
        return GovernanceRunResult(
            signal_id=candidate.signal_id,
            status="failed",
            package_path=None,
            report_path=None,
            publish_status="failed",
            error=str(exc),
        )
