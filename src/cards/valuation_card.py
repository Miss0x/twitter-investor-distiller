"""Valuation tools card — DCF, Comps, DD checklist."""
from __future__ import annotations

from src.cards.base import Card
from src.cards import register


@register
class ValuationProCard(Card):
    name = "valuation_pro"
    display_title = "估值工具"
    template = "valuation_pro.html"

    def get_data(self) -> dict:
        return {"ticker": ""}
