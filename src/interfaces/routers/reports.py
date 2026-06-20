"""信号质量报告 API：/api/reports/signal-quality。

从 web_api.py 抽出，路径与原 @app.get 完全一致。
"""
from __future__ import annotations

from fastapi import APIRouter

from src.api.schemas import SignalQualityReportResponse

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/signal-quality", response_model=SignalQualityReportResponse)
async def signal_quality_report(days: int = 7):
    """导出信号质量报告（JSON 格式）。"""
    from src.governance.audit import GovernanceAuditor  # noqa: PLC0415
    auditor = GovernanceAuditor()
    metrics = auditor.get_quality_metrics(days=days)
    return {
        "period_days": days,
        "total_signals": metrics.get("total", 0),
        "passed_gate": metrics.get("passed", 0),
        "pass_rate": round(metrics.get("passed", 0) / max(metrics.get("total", 1), 1) * 100, 1),
        "avg_confidence": metrics.get("avg_confidence", 0),
        "risk_flags": metrics.get("risk_flags", 0),
        "panel_consensus": metrics.get("consensus", {}),
        "generated_at": str(__import__("datetime").datetime.now()),
    }