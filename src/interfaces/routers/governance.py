"""治理 Gap API：/api/governance/gaps/{acknowledge, revoke}。

从 web_api.py 抽出，路径与原 @app.post 完全一致。
"""
from __future__ import annotations

from fastapi import APIRouter

from src.interfaces.routers.cards import invalidate_card_cache

router = APIRouter(prefix="/api/governance/gaps", tags=["governance"])


@router.post("/acknowledge")
async def acknowledge_governance_gap(payload: dict):
    """Temporarily accept a governance data issue and rerun checks."""
    try:
        from src.governance.gap_actions import acknowledge_gap_for_signal  # noqa: PLC0415
        from src.governance.repository import GovernanceRepository  # noqa: PLC0415

        result = acknowledge_gap_for_signal(
            repo=GovernanceRepository(),
            signal_id=str(payload.get("signal_id") or ""),
            gap_code=str(payload.get("gap_code") or ""),
            reason=str(payload.get("reason") or ""),
            expires_in_hours=int(payload.get("expires_in_hours") or 72),
        )
        invalidate_card_cache("quality_gate", "publish_review")
        return result
    except Exception as e:
        return {"ok": False, "error": str(e) or "操作没有保存成功"}


@router.post("/revoke")
async def revoke_governance_gap(payload: dict):
    """Stop accepting a governance data issue and rerun checks."""
    try:
        from src.governance.gap_actions import revoke_gap_acknowledgement  # noqa: PLC0415
        from src.governance.repository import GovernanceRepository  # noqa: PLC0415

        result = revoke_gap_acknowledgement(
            repo=GovernanceRepository(),
            signal_id=str(payload.get("signal_id") or ""),
            gap_code=str(payload.get("gap_code") or ""),
            reason=str(payload.get("reason") or "重新检查这个风险"),
        )
        invalidate_card_cache("quality_gate", "publish_review")
        return result
    except Exception as e:
        return {"ok": False, "error": str(e) or "操作没有保存成功"}
