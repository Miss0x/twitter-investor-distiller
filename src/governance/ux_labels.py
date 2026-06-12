"""Human-readable governance labels for Dashboard UX.

Internal governance codes stay stable for storage and tests, while Web pages
show natural language labels. Keep this module presentation-only.
"""

from __future__ import annotations

from datetime import datetime

from src.governance.data_gaps import _is_ack_active
from src.governance.models import AcknowledgedGap, DataGap


_GAP_LABELS = {
    "no_evidence": {
        "title": "缺少原始证据",
        "description": "这条信号还没有可追溯的推文、分析或行情证据。",
        "suggested_action": "先补充证据，再重新检查。",
    },
    "missing_price_context": {
        "title": "缺少价格背景",
        "description": "需要确认这条观点出现时，相关标的的价格和波动情况。",
        "suggested_action": "补充行情数据，或只作为观察线索暂时接受风险。",
    },
    "missing_earnings_context": {
        "title": "缺少最新财报背景",
        "description": "需要确认这条观点是否和最近业绩变化一致。",
        "suggested_action": "补充财报信息，或暂时保留为观察信号。",
    },
}

_SEVERITY_LABELS = {
    "info": "提示",
    "warning": "需要注意",
    "critical": "关键",
}


def _active_ack_for_gap(
    gap: DataGap,
    acknowledged_gaps: list[AcknowledgedGap],
    now: datetime | None = None,
) -> tuple[AcknowledgedGap | None, bool]:
    matching = [ack for ack in acknowledged_gaps if ack.code == gap.code]
    if not matching:
        return None, False
    latest = matching[-1]
    return latest, _is_ack_active(latest, now=now)


def gap_to_display(
    gap: DataGap,
    acknowledged_gaps: list[AcknowledgedGap] | None = None,
    now: datetime | None = None,
) -> dict:
    """Convert one DataGap into natural-language Dashboard display data."""
    labels = _GAP_LABELS.get(gap.code, {})
    acknowledged_gaps = acknowledged_gaps or []
    ack, active = _active_ack_for_gap(gap, acknowledged_gaps, now=now)

    if ack is None:
        status = "pending"
        status_label = "待处理"
    elif active:
        status = "acknowledged"
        status_label = "已暂时接受"
    else:
        status = "expired"
        status_label = "已过期，需要重新确认"

    return {
        "code": gap.code,
        "title": labels.get("title", "未知问题，请查看日志"),
        "description": labels.get("description", "系统发现了一个暂时无法解释的问题。"),
        "severity": gap.severity,
        "severity_label": _SEVERITY_LABELS.get(gap.severity, "需要注意"),
        "required_for_publish": gap.required_for_publish,
        "publish_impact_label": "会影响正式发布" if gap.required_for_publish else "不阻断观察",
        "status": status,
        "status_label": status_label,
        "reason": ack.reason if ack else "",
        "expires_at": ack.expires_at if ack else None,
        "suggested_action": labels.get("suggested_action") or gap.suggested_fix or "请补充信息后重新检查。",
        "action_label": "我知道这里缺数据，暂时接受这个风险",
        "revoke_label": "不再接受这个风险",
        "reason_label": "为什么暂时接受？",
        "reason_placeholder": "例如：只作为观察线索，不作为正式买入依据",
        "expires_label": "这个决定多久后失效？",
    }
