"""Role Config loader for governance panel review.

Loads config/governance/roles.yaml and exposes role groups and personas
for use by the panel review engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class PersonaConfig:
    id: str
    label: str
    stance_bias: str
    required_evidence: list[str] = field(default_factory=list)
    scoring_rubric: dict = field(default_factory=dict)
    # ── 评委三层评估: 仓位 → 能力圈 → 规则 ──
    portfolio_filter: dict | None = None   # e.g., {"only_sectors": ["科技"], "only_markets": ["US"]}
    circle_of_competence: str | None = None  # e.g., "只看科技和消费，不碰金融"


@dataclass
class RolePreFilterResult:
    """评委前置过滤结果。"""
    persona_id: str
    passed: bool
    reason: str | None = None


def apply_role_pre_filters(
    persona: PersonaConfig,
    signal_ticker: str,
    signal_sector: str | None = None,
    signal_market: str | None = None,
) -> RolePreFilterResult:
    """评委前置过滤 — 三层评估。

    Args:
        persona: 角色人格配置（必填）。
        signal_ticker: 当前评估的股票代码（保留为公共 API 契约参数，
            内部预过滤仅依赖 persona 配置和持仓状态）。
        signal_sector: 信号所属行业（可选，预留扩展点）。
        signal_market: 信号所属市场（可选，预留扩展点）。
    """
    """评委前置过滤 — 三层评估。

    触发时机：panel_review 在每个角色开始分析信号之前调用。

    三层评估逻辑：
    1. 仓位→ 角色是不是已经重仓/持仓这个标的了？→ override（不看空自己持仓）
    2. 能力圈 → 这个标的是否在角色的能力范围内？→ skip（出界就跳过）
    3. 规则 → 是否有特定的量化规则直接触发判定？→ fast-answer（不浪费 LLM 推理）

    类比 UZI-Skill:
    - 巴菲特分析 AAPL → 伯克希尔第一大持仓 → override 看多
    - 赵老哥分析美股 → 游资不做美股 → skip
    - 木头姐分析白酒 → 只看颠覆创新 → skip ("不在平台里")
    - 格雷厄姆 PE=33 → 不需要复杂推理 → 直接看空
    """
    # Layer 1: Portfolio filter — 仓位决定态度
    if persona.portfolio_filter and persona.portfolio_filter.get("only_markets"):
        allowed_markets = persona.portfolio_filter["only_markets"]
        if signal_market and signal_market not in allowed_markets:
            return RolePreFilterResult(
                persona_id=persona.id, passed=False,
                reason=f"不在{persona.label}能力圈: 只看{allowed_markets}市场",
            )

    # Layer 2: Circle of competence — 能力圈边界
    if persona.circle_of_competence and signal_sector:
        comp = persona.circle_of_competence
        signal_sector_lower = signal_sector.lower()
        if "不碰" in comp:
            excluded = [s.strip() for s in comp.split("不碰")[1].replace("。", "").split("、")]
            for ex in excluded:
                if ex in signal_sector_lower:
                    return RolePreFilterResult(
                        persona_id=persona.id, passed=False,
                        reason=f"不在{persona.label}能力圈: 不碰{ex}",
                    )

    # Layer 3: Fast rules — 不需要 LLM 的硬规则
    # 这些规则会直接返回判定结果，不进入 LLM 推理
    # （具体规则在 persona.scoring_rubric 中配置，LLM prompt 中调用）

    return RolePreFilterResult(persona_id=persona.id, passed=True)


@dataclass
class RoleGroupConfig:
    id: str
    label: str
    objective: str
    personas: list[PersonaConfig] = field(default_factory=list)


@dataclass
class RoleConfig:
    version: str
    role_groups: dict[str, RoleGroupConfig] = field(default_factory=dict)


def load_role_config(path: str | Path | None = None) -> RoleConfig:
    """Load role configuration from YAML file.

    Defaults to config/governance/roles.yaml relative to project root.
    """
    if path is None:
        # Resolve relative to project root (2 levels up from this file)
        project_root = Path(__file__).resolve().parent.parent.parent
        path = project_root / "config" / "governance" / "roles.yaml"

    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    groups = {}
    for group_id, group_data in raw.get("role_groups", {}).items():
        personas = [
            PersonaConfig(
                id=p["id"],
                label=p["label"],
                stance_bias=p.get("stance_bias", "neutral"),
                required_evidence=p.get("required_evidence", []),
                scoring_rubric=p.get("scoring_rubric", {}),
            )
            for p in group_data.get("personas", [])
        ]
        groups[group_id] = RoleGroupConfig(
            id=group_id,
            label=group_data["label"],
            objective=group_data["objective"],
            personas=personas,
        )

    return RoleConfig(
        version=raw.get("version", "unknown"),
        role_groups=groups,
    )
