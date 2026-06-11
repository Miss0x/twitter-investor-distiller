"""Quality Gate — deterministic pre-check before panel review and publish.

The Quality Gate is the first governance module that inspects a SignalCandidate.
It produces machine-readable checks with codes, severity, and messages.
Rules are deterministic and do NOT call LLM.
"""

from __future__ import annotations

from typing import Literal

from src.governance.models import GateStatus, SignalCandidate

PushIntent = Literal["dashboard", "strong_push"]


def run_quality_gate(
    candidate: SignalCandidate,
    push_intent: PushIntent = "dashboard",
) -> dict:
    """Run quality gate on a SignalCandidate.

    Returns a dict with:
      status: "pass" | "warn" | "block"
      checks: list of {"code": str, "severity": str, "message": str, "blocking": bool}
      data_gap_ref: path reference to independent data_gaps artifact (future)
    """
    checks: list[dict] = []
    blocking = False

    # Check 1: Zero evidence
    if not candidate.has_evidence():
        checks.append(
            {
                "code": "no_evidence",
                "severity": "critical",
                "message": "Signal candidate has zero evidence references",
                "blocking": True,
            }
        )
        return {
            "status": "block",
            "checks": checks,
        }

    # Check 2: Missing price context
    has_price = any(e.source_type == "price" for e in candidate.evidence)
    if not has_price:
        check = {
            "code": "missing_price_context",
            "severity": "warning",
            "message": "No market price data in evidence — conclusions may lack price context",
            "blocking": False,
        }
        if push_intent == "strong_push":
            check["severity"] = "critical"
            check["blocking"] = True
            check["message"] += " (blocking for strong push)"
            blocking = True
        checks.append(check)

    # Future: Check 3+ — source reliability, time freshness, ticker mapping confidence

    # Determine overall status
    if blocking:
        status: GateStatus = "block"
    elif any(c["severity"] == "warning" for c in checks):
        status = "warn"
    else:
        status = "pass"

    return {
        "status": status,
        "checks": checks,
    }
