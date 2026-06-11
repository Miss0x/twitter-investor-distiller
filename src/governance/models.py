"""
信号治理层数据模型

本模块定义所有治理相关的核心数据类型，全部使用 dataclass，
保证 JSON 可序列化、不可变性与 Python 类型安全。

实体关系：

  SignalCandidate  - 治理的输入，来自现有分析/共识/行情
  EvidenceRef      - 可追溯的证据引用（tweet / price / analysis / ...）
  DataGap          - 被检测到的数据缺口（独立落盘，不嵌入其他结果）
  AcknowledgedGap  - 对无法补齐缺口的显式承认
  SignalPackage    - 通过所有门禁后的最终信号包
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

# ── literal types ──

Severity = Literal["info", "warning", "critical"]
GateStatus = Literal["pass", "warn", "block", "failed"]
RiskLevel = Literal["safe", "notice", "caution", "high_risk", "unknown"]
PanelStance = Literal["bullish", "bearish", "neutral", "avoid", "insufficient_data"]
GapStatus = Literal["open", "resolved", "acknowledged"]


# ── entities ──

@dataclass(frozen=True)
class EvidenceRef:
    """一条可追溯的证据引用。

    证据来源可以是 tweet、price、analysis、consensus、risk、panel 或 manual。
    每条引用必须包含 source_type 和 source_id，其他字段可选。
    """

    source_type: Literal["tweet", "price", "analysis", "consensus", "risk", "panel", "manual"]
    source_id: str
    url: str | None = None
    title: str | None = None
    excerpt: str | None = None
    timestamp: str | None = None
    reliability: float | None = None


@dataclass(frozen=True)
class DataGap:
    """一条被检测到的数据缺口。

    缺口独立于 QualityAssessment 独立落盘，便于审计和 user/agent 复检。
    required_for_publish=True 的缺口必须补齐或 acknowledged 才能通过 Publish Gate。
    """

    code: str
    message: str
    severity: Severity = "warning"
    required_for_publish: bool = False
    suggested_fix: str | None = None
    evidence_needed: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AcknowledgedGap:
    """对一条无法补齐的数据缺口的显式承认。

    承认不代表缺口消失，仅代表在当前条件下接受此缺口继续后续流程。
    可以有 expires_at 以强制未来重新检查。
    """

    code: str
    reason: str
    acknowledged_by: str
    acknowledged_at: str
    expires_at: str | None = None


@dataclass
class SignalCandidate:
    """治理管线的输入信号。

    SignalCandidate 由现有分析/共识/行情流程生成，是治理层的唯一入口。
    注意：此 dataclass 为 mutable（包含 raw_payload dict），
    以兼容现有分析系统的 JSON 产物直接反序列化。
    """

    signal_id: str
    ticker: str
    generated_at: datetime | str
    source_tweet_ids: list[str] = field(default_factory=list)
    source_usernames: list[str] = field(default_factory=list)
    asset_name: str | None = None
    stance: str | None = None
    signal_score: float | None = None
    confidence: str | None = None
    evidence: list[EvidenceRef] = field(default_factory=list)
    raw_payload: dict = field(default_factory=dict)

    def has_evidence(self) -> bool:
        """是否有任何证据引用。"""
        return len(self.evidence) > 0


@dataclass
class SignalPackage:
    """通过所有治理门禁后的最终信号包。

    SignalPackage 是 Dashboard / RAG / Telegram / HTML report 的唯一数据来源。
    publish_status 为 "block" 时，不得进入强推送或生成 HTML 报告。
    """

    signal_id: str
    ticker: str
    generated_at: datetime | str
    publish_status: GateStatus
    summary: str = ""
    candidate: SignalCandidate | None = None
    quality: dict = field(default_factory=dict)
    data_gaps: list[DataGap] = field(default_factory=list)
    acknowledged_gaps: list[AcknowledgedGap] = field(default_factory=list)
    panel: dict = field(default_factory=dict)
    debate: dict = field(default_factory=dict)
    risk: dict = field(default_factory=dict)
    publish_review: dict = field(default_factory=dict)
    evidence: list[EvidenceRef] = field(default_factory=list)
    html_report_path: str | None = None

    def can_publish(self) -> bool:
        """是否可以通过发布门禁。"""
        return self.publish_status in ("pass", "warn")

    def is_blocked(self) -> bool:
        """是否被发布门禁阻断。"""
        return self.publish_status in ("block", "failed")
