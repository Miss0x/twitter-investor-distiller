"""Governance Dashboard cards — display signal quality, risk, panel review, and publish gate results.

All cards follow existing project rules:
- API returns {html, data, error}
- No Python-generated onclick
- DOM ids use card name prefix
- Empty/loading/error states exist
"""

from __future__ import annotations

from pathlib import Path

from src.cards.base import Card
from src.cards import register


@register
class QualityGateCard(Card):
    """Show today's signal quality gate results."""

    name = "quality_gate"
    display_title = "信号质量门禁"
    template = "quality_gate.html"

    def get_data(self) -> dict:
        # Governance data not yet wired — return empty state
        return {
            "passed": 0,
            "warned": 0,
            "blocked": 0,
            "checks": [],
            "empty": True,
        }


@register
class RiskAlertsCard(Card):
    """Show risk scan results and prevent strong push for high_risk signals."""

    name = "risk_alerts"
    display_title = "风险提示"
    template = "risk_alerts.html"

    def get_data(self) -> dict:
        return {
            "risk_level": "unknown",
            "total_score": 0,
            "triggers": [],
            "empty": True,
        }


@register
class PanelReviewCard(Card):
    """Show multi-role panel review for the latest signal."""

    name = "panel_review"
    display_title = "多角色评审"
    template = "panel_review.html"

    def get_data(self) -> dict:
        return {
            "aggregate_stance": "unknown",
            "aggregate_score": 0,
            "reviews": [],
            "empty": True,
        }


@register
class PublishReviewCard(Card):
    """Show final publish gate decision."""

    name = "publish_review"
    display_title = "发布审核"
    template = "publish_review.html"

    def get_data(self) -> dict:
        return {
            "status": "unknown",
            "issues": [],
            "empty": True,
        }
