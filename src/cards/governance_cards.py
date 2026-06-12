"""Governance Dashboard cards — display signal quality, risk, panel review, and publish gate results.

All cards follow existing project rules:
- API returns {html, data, error}
- No Python-generated onclick
- DOM ids use card name prefix
- Empty/loading/error states exist
"""

from __future__ import annotations

from datetime import datetime

from src.cards.base import Card
from src.cards import register
from src.governance.repository import GovernanceRepository
from src.governance.ux_labels import gap_to_display


@register
class QualityGateCard(Card):
    """Show today's signal quality gate results."""

    name = "quality_gate"
    display_title = "信号质量门禁"
    template = "quality_gate.html"

    def get_data(self, now: datetime | None = None) -> dict:
        package = GovernanceRepository().load_latest_package()
        if package is None:
            return {"passed": 0, "warned": 0, "blocked": 0, "checks": [], "data_gaps": [], "empty": True}
        return {
            "empty": False,
            "signal_id": package.signal_id,
            "ticker": package.ticker,
            "status": package.quality.get("status", package.publish_status),
            "checks": package.quality.get("checks", []),
            "data_gaps": [gap_to_display(g, package.acknowledged_gaps, now=now) for g in package.data_gaps],
            "acknowledged_gaps": [a.__dict__ for a in package.acknowledged_gaps],
        }


@register
class RiskAlertsCard(Card):
    """Show risk scan results and prevent strong push for high_risk signals."""

    name = "risk_alerts"
    display_title = "风险提示"
    template = "risk_alerts.html"

    def get_data(self) -> dict:
        package = GovernanceRepository().load_latest_package()
        if package is None:
            return {"risk_level": "unknown", "total_score": 0, "triggers": [], "empty": True}
        return {
            "empty": False,
            "signal_id": package.signal_id,
            "ticker": package.ticker,
            "risk_level": package.risk.get("risk_level", "unknown"),
            "total_score": package.risk.get("total_score", 0),
            "triggers": package.risk.get("triggers", []),
        }


@register
class PanelReviewCard(Card):
    """Show multi-role panel review for the latest signal."""

    name = "panel_review"
    display_title = "多角色评审"
    template = "panel_review.html"

    def get_data(self) -> dict:
        package = GovernanceRepository().load_latest_package()
        if package is None:
            return {"aggregate_stance": "unknown", "aggregate_score": 0, "reviews": [], "debate": {}, "empty": True}
        panel = package.panel
        return {
            "empty": False,
            "signal_id": package.signal_id,
            "ticker": package.ticker,
            "aggregate_stance": panel.get("aggregate_stance", "unknown"),
            "aggregate_score": panel.get("aggregate_score", 0),
            "review_mode": panel.get("review_mode", "deterministic"),
            "bullish_count": panel.get("bullish_count", 0),
            "bearish_count": panel.get("bearish_count", 0),
            "neutral_count": panel.get("neutral_count", 0),
            "insufficient_data_count": panel.get("insufficient_data_count", 0),
            "reviews": panel.get("reviews", []),
            "debate": package.debate,
        }


@register
class PublishReviewCard(Card):
    """Show final publish gate decision."""

    name = "publish_review"
    display_title = "发布审核"
    template = "publish_review.html"

    def get_data(self) -> dict:
        package = GovernanceRepository().load_latest_package()
        if package is None:
            return {"status": "unknown", "issues": [], "empty": True}
        return {
            "empty": False,
            "signal_id": package.signal_id,
            "ticker": package.ticker,
            "status": package.publish_status,
            "issues": package.publish_review.get("issues", []),
            "html_report_path": package.html_report_path,
        }
