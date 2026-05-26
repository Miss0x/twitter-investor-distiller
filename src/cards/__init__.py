"""卡片注册表 — 所有模块化页面卡片的统一入口。

新增卡片只需 import 到 CARDS 列表中。
Dashboard 会遍历 CARDS，按 tab 分组渲染。
"""
from __future__ import annotations

from .base import Card

CARDS: list[Card] = []


def register(card_cls):
    instance = card_cls()
    CARDS.append(instance)
    return card_cls


def get_cards_by_tab(tab: str) -> list[Card]:
    return [c for c in CARDS if c.tab == tab]


def get_card(name: str) -> Card | None:
    for c in CARDS:
        if c.name == name:
            return c
    return None


# 导入所有卡片模块以触发注册
from . import accuracy       # noqa: E402, F401
from . import data_cards     # noqa: E402, F401
from . import interactive_cards  # noqa: E402, F401
from . import pipeline_control   # noqa: E402, F401
from . import tool_cards     # noqa: E402, F401
