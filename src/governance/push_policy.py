"""Telegram push policy — prevent risky signals from reaching strong push channels.

High-risk signals and blocked packages must not be pushed to Telegram.
Only pass/warn signals with safe/notice risk levels may be pushed.
"""

from __future__ import annotations


def should_allow_strong_push(
    publish_status: str,
    risk_level: str,
) -> tuple[bool, str]:
    """Determine if a signal may be pushed to Telegram as a strong alert.

    Returns (allowed, reason).
    """
    if not publish_status or publish_status == "block":
        return False, "Signal is blocked by Publish Gate"

    if publish_status == "failed":
        return False, "Governance pipeline failed"

    if risk_level == "high_risk":
        return False, "High-risk signal blocked from strong push"

    allowed_states = {("pass", "safe"), ("pass", "notice"), ("warn", "safe"), ("warn", "notice")}
    if (publish_status, risk_level) in allowed_states:
        if publish_status == "warn":
            return True, "Warn status — push with warning label"
        return True, "Clean signal — normal push"

    return False, "Unknown or caution state blocked from strong push"
