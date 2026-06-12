from src.governance.models import EvidenceRef, SignalCandidate
from src.governance.panel_review import run_panel_review
from src.governance.roles import PersonaConfig, RoleConfig, RoleGroupConfig


class FakeReviewClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def review(self, *, candidate, group, persona):
        self.calls.append((candidate.signal_id, group.id, persona.id))
        if isinstance(self.responses[0], Exception):
            raise self.responses.pop(0)
        return self.responses.pop(0)


def _candidate():
    return SignalCandidate(
        signal_id="SIG-LLM-1",
        ticker="NVDA",
        generated_at="2026-06-12T00:00:00+00:00",
        source_tweet_ids=["tweet_1"],
        source_usernames=["researcher"],
        stance="bullish",
        evidence=[
            EvidenceRef(source_type="tweet", source_id="tweet_1", excerpt="需求强劲"),
            EvidenceRef(source_type="price", source_id="price_1", excerpt="价格背景存在"),
        ],
    )


def _config():
    persona = PersonaConfig(
        id="growth_investor",
        label="成长研究员",
        stance_bias="disruption_optimism",
        required_evidence=["tweet", "price"],
    )
    group = RoleGroupConfig(
        id="growth",
        label="成长派",
        objective="评估成长空间",
        personas=[persona],
    )
    return RoleConfig(version="test", role_groups={"growth": group})


def test_panel_review_uses_valid_llm_review_when_enabled():
    client = FakeReviewClient([
        {
            "stance": "bullish",
            "confidence": 72,
            "decision": "warn",
            "key_points": ["需求证据较强", "但仍需观察估值"],
            "evidence_used": ["tweet_1", "price_1"],
            "data_gaps": ["missing_earnings_context"],
            "risk_flags": ["valuation_risk"],
            "summary": "可以继续跟踪，但不适合直接作为强买入信号。",
        }
    ])

    panel = run_panel_review(_candidate(), config=_config(), llm_client=client)

    review = panel["reviews"][0]
    assert panel["review_mode"] == "llm"
    assert review["source"] == "llm"
    assert review["valid"] is True
    assert review["summary"] == "可以继续跟踪，但不适合直接作为强买入信号。"
    assert review["evidence_used"] == ["tweet_1", "price_1"]
    assert panel["needs_llm_summary"] is False


def test_llm_review_with_unknown_evidence_is_invalid_and_excluded_from_score():
    client = FakeReviewClient([
        {
            "stance": "bullish",
            "confidence": 90,
            "decision": "support",
            "key_points": ["引用了不存在证据"],
            "evidence_used": ["made_up_evidence"],
            "data_gaps": [],
            "risk_flags": [],
            "summary": "这条评审不能采信。",
        }
    ])

    panel = run_panel_review(_candidate(), config=_config(), llm_client=client)

    review = panel["reviews"][0]
    assert panel["review_mode"] == "fallback"
    assert review["source"] == "llm"
    assert review["valid"] is False
    assert review["invalid_reason"] == "unknown_evidence"
    assert panel["aggregate_stance"] == "insufficient_data"
    assert panel["aggregate_score"] == 0


def test_panel_review_falls_back_to_deterministic_when_llm_fails():
    client = FakeReviewClient([RuntimeError("timeout")])

    panel = run_panel_review(_candidate(), config=_config(), llm_client=client)

    review = panel["reviews"][0]
    assert panel["review_mode"] == "deterministic_fallback"
    assert review["source"] == "deterministic"
    assert review["valid"] is True
    assert review["score"] == 0.8
    assert panel["aggregate_stance"] == "bullish"
