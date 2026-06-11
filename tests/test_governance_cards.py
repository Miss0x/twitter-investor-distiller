"""Phase 8: Dashboard Governance Cards tests."""
from pathlib import Path

import pytest

sys_path_hack = str(Path(__file__).resolve().parent.parent)
import sys
sys.path.insert(0, sys_path_hack)


# ── tests ──

def test_governance_cards_registered_in_card_config():
    from src.cards.cards_config import CARD_CONFIG, CARD_DISPLAY

    expected = {"quality_gate", "risk_alerts", "panel_review", "publish_review"}
    for name in expected:
        assert name in CARD_CONFIG, f"{name} missing from CARD_CONFIG"
        assert name in CARD_DISPLAY, f"{name} missing from CARD_DISPLAY"


def test_governance_cards_have_correct_tabs():
    from src.cards.cards_config import CARD_CONFIG

    assert CARD_CONFIG["quality_gate"][0] == "signals"
    assert CARD_CONFIG["risk_alerts"][0] == "signals"
    assert CARD_CONFIG["panel_review"][0] == "decisions"
    assert CARD_CONFIG["publish_review"][0] == "data"


def test_quality_gate_card_returns_empty_state():
    from src.cards.governance_cards import QualityGateCard

    card = QualityGateCard()
    data = card.get_data()
    assert data["empty"] is True
    assert "passed" in data


def test_risk_alerts_card_returns_empty_state():
    from src.cards.governance_cards import RiskAlertsCard

    card = RiskAlertsCard()
    data = card.get_data()
    assert data["empty"] is True
    assert data["risk_level"] == "unknown"


def test_panel_review_card_returns_empty_state():
    from src.cards.governance_cards import PanelReviewCard

    card = PanelReviewCard()
    data = card.get_data()
    assert data["empty"] is True
    assert data["reviews"] == []


def test_publish_review_card_returns_empty_state():
    from src.cards.governance_cards import PublishReviewCard

    card = PublishReviewCard()
    data = card.get_data()
    assert data["empty"] is True
    assert data["status"] == "unknown"


def test_governance_cards_use_jinja2_templates():
    from src.cards.governance_cards import (
        PanelReviewCard,
        PublishReviewCard,
        QualityGateCard,
        RiskAlertsCard,
    )

    assert QualityGateCard.template == "quality_gate.html"
    assert RiskAlertsCard.template == "risk_alerts.html"
    assert PanelReviewCard.template == "panel_review.html"
    assert PublishReviewCard.template == "publish_review.html"


def test_governance_cards_loaded_in_registry():
    from src.cards import CARDS

    names = {c.name for c in CARDS}
    assert "quality_gate" in names
    assert "risk_alerts" in names
    assert "panel_review" in names
    assert "publish_review" in names


def test_card_count_includes_governance():
    from src.cards import CARDS

    # Previously 20 cards, now 24 with governance
    all_names = {c.name for c in CARDS}
    assert len(all_names) >= 20
    assert len(all_names) == len(CARDS), "card names should be unique"
