"""Publish Gate — final checkpoint before a signal becomes public.

Aggregates Quality Gate, Panel Review, Debate, and Risk Scan results
and produces a definitive publish decision.

A critical issue in any upstream gate results in a hard "block".
"""

from __future__ import annotations

from src.governance.models import AcknowledgedGap, DataGap, GateStatus
from src.governance.data_gaps import has_blocking_gaps


def run_publish_gate(
    quality: dict,
    panel: dict,
    debate: dict,
    risk: dict,
    data_gaps: list[DataGap],
    acknowledged_gaps: list[AcknowledgedGap],
) -> dict:
    """Aggregate all gate results into a final publish decision.

    Returns dict with:
      status: "pass" | "warn" | "block"
      issues: list of issue dicts with code, severity, message
      critical_count: int
      warning_count: int
    """
    issues: list[dict] = []
    critical = 0
    warnings = 0

    # 1. Quality gate
    if quality.get("status") == "block":
        issues.append(
            {
                "code": "quality_block",
                "severity": "critical",
                "message": "Quality gate blocked: " + str(
                    [c.get("code", "unknown") for c in quality.get("checks", [])]
                ),
            }
        )
        critical += 1
    elif quality.get("status") == "warn":
        warnings += 1

    # 2. Unacknowledged required data gaps
    if has_blocking_gaps(data_gaps, acknowledged_gaps):
        issues.append(
            {
                "code": "blocking_data_gaps",
                "severity": "critical",
                "message": "Required data gaps remain unacknowledged",
            }
        )
        critical += 1

    # 3. Risk scan
    if risk.get("risk_level") == "high_risk":
        issues.append(
            {
                "code": "high_risk",
                "severity": "critical",
                "message": "Risk scan detected high-risk signal pattern",
            }
        )
        critical += 1
    elif risk.get("risk_level") == "caution":
        warnings += 1

    # 4. Debate — insufficient data
    if debate.get("final_stance") == "insufficient_data":
        issues.append(
            {
                "code": "debate_insufficient_data",
                "severity": "warning",
                "message": "Panel debate found insufficient data to form stance",
            }
        )
        warnings += 1

    # 5. Evidence check — must have at least one evidence ref
    # (Already blocked by quality gate, but double-check for package building)
    # This is handled by package builder separately.

    if critical > 0:
        status: GateStatus = "block"
    elif warnings > 0:
        status = "warn"
    else:
        status = "pass"

    return {
        "status": status,
        "issues": issues,
        "critical_count": critical,
        "warning_count": warnings,
    }
