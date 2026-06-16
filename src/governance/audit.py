"""Append-only audit events for governance user actions + quality metrics."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.governance.repository import GovernanceRepository


def append_gap_event(
    repo: GovernanceRepository,
    event_type: str,
    signal_id: str,
    gap_code: str,
    reason: str,
    actor: str = "local_user",
    created_at: datetime | None = None,
) -> None:
    created_at = created_at or datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    repo.append_audit_event(
        signal_id,
        {
            "event_type": event_type,
            "signal_id": signal_id,
            "gap_code": gap_code,
            "actor": actor,
            "reason": reason,
            "created_at": created_at.isoformat(),
        },
        signal_date=created_at.date().isoformat(),
    )


class GovernanceAuditor:
    """审计与质量报告生成器。

    从治理管线产出物中聚合信号质量指标，供 /api/reports/signal-quality 使用。
    """

    def __init__(self, base_dir: str | Path = "data/governance") -> None:
        self.base_dir = Path(base_dir)

    def get_quality_metrics(self, days: int = 7) -> dict:
        """汇总最近 N 天的信号质量指标。

        Returns:
            dict: {
                "total": int,       # 信号总数
                "passed": int,      # 通过发布门禁的信号数
                "avg_confidence": float,  # 平均置信度 (0-100)
                "risk_flags": int,  # 风险标记总数
                "consensus": dict,  # 角色共识分布 {role: count}
            }
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        total = 0
        passed = 0
        avg_confidence = 0.0
        risk_flags = 0
        consensus: dict[str, int] = {}

        # 扫描 quality/ 目录获取信号质量
        quality_dir = self.base_dir / "quality"
        if quality_dir.exists():
            for date_dir in quality_dir.iterdir():
                if not date_dir.is_dir():
                    continue
                try:
                    dt = datetime.strptime(date_dir.name, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                if dt < cutoff:
                    continue
                for signal_file in date_dir.iterdir():
                    if signal_file.suffix != ".json":
                        continue
                    total += 1
                    try:
                        data = json.loads(signal_file.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        continue
                    c = data.get("confidence", 50)
                    avg_confidence += c
                    if data.get("passed", False):
                        passed += 1
                    rf = data.get("risk_flags", 0) or 0
                    risk_flags += rf
                    for role in data.get("panel_consensus", {}):
                        consensus[role] = consensus.get(role, 0) + 1

        if total > 0:
            avg_confidence = round(avg_confidence / total, 1)

        return {
            "total": total,
            "passed": passed,
            "avg_confidence": avg_confidence,
            "risk_flags": risk_flags,
            "consensus": consensus,
        }
