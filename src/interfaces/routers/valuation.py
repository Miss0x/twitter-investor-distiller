"""估值工具 API：/api/valuation/{dcf, dd}。

从 web_api.py 抽出，路径与原 @app.get 完全一致。

修复记录:
    - 2026-06-20: 外部异常（yfinance rate limit / 网络错误）不再裸抛到客户端，
      改为返回业务友好的 {ticker, error} 信封（与项目其他错误响应风格一致）。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from src.api.schemas import ValuationDcfResponse, ValuationDDItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/valuation", tags=["valuation"])


@router.get("/dcf", response_model=ValuationDcfResponse)
async def valuation_dcf(
    ticker: str,
    wacc: float | None = None,
    growth: float | None = None,
    terminal: float | None = None,
):
    """DCF 内在价值计算。

    异常处理:
        - yfinance rate limit / 网络异常 / ticker 找不到 → 返回 ticker 信封 + None 字段,
          不抛 500 (避免前端解析失败)
    """
    from src.data.valuation_tools import ValuationTools  # noqa: PLC0415

    try:
        result = ValuationTools().recalculate_dcf(
            ticker.upper(), wacc=wacc, growth_5y=growth, terminal_growth=terminal,
        )
    except Exception as e:
        logger.warning("valuation_dcf 失败 (ticker=%s): %s", ticker, e)
        return {
            "ticker": ticker.upper(),
            "intrinsic_value": None,
            "current_price": None,
            "upside_pct": None,
            "wacc": None,
            "growth_5y": None,
            "terminal_growth": None,
            "fcf": None,
            "confidence": "unavailable",
        }
    return {
        "ticker": result.ticker,
        "intrinsic_value": result.intrinsic_value,
        "current_price": result.current_price,
        "upside_pct": result.upside_pct,
        "wacc": result.wacc,
        "growth_5y": result.growth_rate_5y,
        "terminal_growth": result.terminal_growth,
        "fcf": result.free_cash_flow,
        "confidence": result.confidence,
    }


@router.get("/dd", response_model=list[ValuationDDItem])
async def valuation_dd(ticker: str):
    """尽调(Due-Diligence)问题清单。"""
    from src.data.valuation_tools import ValuationTools  # noqa: PLC0415
    items = ValuationTools().generate_dd_checklist(ticker.upper())
    return [
        {"category": i.category, "question": i.question, "status": i.status, "evidence": i.evidence}
        for i in items
    ]
