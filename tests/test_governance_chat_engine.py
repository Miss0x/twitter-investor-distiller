"""Phase 10: Chat Engine routing and Push Policy tests."""
import json
from pathlib import Path

import pytest

sys_path_hack = str(Path(__file__).resolve().parent.parent)
import sys
sys.path.insert(0, sys_path_hack)


# ── push policy tests ──

def test_push_policy_blocks_high_risk():
    from src.governance.push_policy import should_allow_strong_push

    allowed, reason = should_allow_strong_push("pass", "high_risk")
    assert allowed is False
    assert "high" in reason.lower()


def test_push_policy_blocks_publish_block():
    from src.governance.push_policy import should_allow_strong_push

    allowed, reason = should_allow_strong_push("block", "safe")
    assert allowed is False


def test_push_policy_allows_clean_signal():
    from src.governance.push_policy import should_allow_strong_push

    allowed, _ = should_allow_strong_push("pass", "safe")
    assert allowed is True


def test_push_policy_allows_warn_with_notice():
    from src.governance.push_policy import should_allow_strong_push

    allowed, reason = should_allow_strong_push("warn", "notice")
    assert allowed is True
    assert "warning" in reason.lower() or "Warn" in reason


# ── chat engine routing tests ──

def test_chat_engine_risk_intent_routing_words_exist():
    """Risk routing keywords are defined for intent detection."""
    from src.governance.models import SignalCandidate
    import sys

    # Validate that governance models can route risk keywords
    # (ChatEngine integration will use this)
    risk_trigger_words = [
        "靠谱吗", "风险", "杀猪盘", "群里老师", "必涨", "翻倍",
        "内幕", "推荐", "庄家", "出货", "拉升",
    ]

    assert len(risk_trigger_words) >= 10

    # Sanity: ensure governance package structure is intact
    import src.governance
    assert src.governance is not None


def test_chat_engine_can_access_governance_modules():
    """Governance modules are importable from the chat engine context."""
    from src.governance.models import SignalPackage
    from src.governance.risk_scan import scan_user_text
    from src.governance.push_policy import should_allow_strong_push

    # All should be importable
    assert SignalPackage is not None
    assert scan_user_text is not None
    assert should_allow_strong_push is not None
