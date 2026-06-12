"""Governance context provider for investment-judgment RAG questions."""

from __future__ import annotations

from src.governance.repository import GovernanceRepository

_INVESTMENT_KEYWORDS = (
    "买",
    "卖",
    "看多",
    "看空",
    "风险",
    "机会",
    "信号",
    "推荐",
    "仓位",
    "目标价",
    "止损",
    "能不能投",
    "是否值得",
)


def is_investment_judgment_question(question: str) -> bool:
    """Return True if the question asks for investment judgment rather than lookup."""
    return any(keyword in question for keyword in _INVESTMENT_KEYWORDS)


def build_governance_context(
    question: str,
    repo: GovernanceRepository | None = None,
    limit: int = 5,
) -> str:
    """Build context from publishable SignalPackages only."""
    repo = repo or GovernanceRepository()
    packages = [p for p in repo.list_latest_packages(limit=limit) if p.publish_status in {"pass", "warn"}]
    if not packages:
        return "当前没有通过发布门禁的治理信号。"

    lines = ["通过发布门禁的治理信号："]
    for package in packages:
        lines.append(
            "\n".join(
                [
                    f"信号: {package.signal_id} / {package.ticker}",
                    f"发布状态: {package.publish_status}",
                    f"风险等级: {package.risk.get('risk_level', 'unknown')}",
                    f"角色共识: {package.panel.get('aggregate_stance', 'unknown')}",
                    f"多空结论: {package.debate.get('final_stance', 'unknown')}",
                    f"摘要: {package.summary or '无摘要'}",
                    "证据: " + ", ".join(f"{e.source_type}:{e.source_id}" for e in package.evidence),
                ]
            )
        )
    return "\n\n".join(lines)
