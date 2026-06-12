from src.governance.debate import run_debate


def test_debate_uses_reviewer_summaries_as_human_readable_arguments():
    panel = {
        "reviews": [
            {
                "persona_label": "成长研究员",
                "stance": "bullish",
                "score": 0.72,
                "summary": "需求证据较强，但需要继续观察估值。",
                "evidence_used": ["tweet_1", "price_1"],
                "risk_flags": ["valuation_risk"],
            },
            {
                "persona_label": "风控研究员",
                "stance": "bearish",
                "score": 0.66,
                "summary": "估值风险还没有被充分解释，不适合强推。",
                "evidence_used": ["price_1"],
                "risk_flags": ["valuation_risk"],
            },
        ],
        "review_mode": "llm",
    }

    debate = run_debate(panel)

    assert debate["debate_mode"] == "human_readable"
    assert debate["bull"]["thesis"] == "成长研究员：需求证据较强，但需要继续观察估值。"
    assert debate["bear"]["thesis"] == "风控研究员：估值风险还没有被充分解释，不适合强推。"
    assert debate["rebuttal"]["why"] == "支持和谨慎意见数量接近，先保持观察，不给出强结论。"
    assert "valuation_risk" not in " ".join(debate["must_disclose_risks"])
    assert "估值风险" in " ".join(debate["must_disclose_risks"])


def test_debate_filters_invalid_reviews():
    panel = {
        "reviews": [
            {
                "persona_label": "无效研究员",
                "stance": "bullish",
                "score": 1,
                "summary": "这条不该进入辩论。",
                "valid": False,
            }
        ]
    }

    debate = run_debate(panel)

    assert debate["final_stance"] == "insufficient_data"
    assert debate["rebuttal"]["why"] == "没有可采信的角色评审，暂时不能形成结论。"
