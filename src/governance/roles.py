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
