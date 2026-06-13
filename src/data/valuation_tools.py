"""
Professional-grade financial analysis tools — optional advanced module.

These are PE/IB-grade analysis methods, accessible as supplementary tools
that run independently of the signal governance pipeline. They do NOT replace
or interfere with the core 8-role governance system.

UZI-Skill equivalent methods adapted for our architecture:
- Valuation models (DCF skeleton, Comps summary)
- M&A accretion summary
- DD checklist generator
- Unit economics calculator
- Portfolio rebalancing advisor

All methods return structured data suitable for LLM enrichment or card rendering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DCFResult:
    """Skeleton DCF valuation result — meant for LLM to fill in assumptions."""
    ticker: str
    free_cash_flow: float | None = None      # TTM FCF
    growth_rate_5y: float | None = None       # projected 5y CAGR
    terminal_growth: float = 0.025
    wacc: float | None = None                 # weighted avg cost of capital
    shares_outstanding: float | None = None
    net_debt: float | None = None
    intrinsic_value: float | None = None      # computed DCF per share
    current_price: float | None = None
    upside_pct: float | None = None
    confidence: str = "low"                   # low/medium/high
    assumptions_needed: list[str] = field(default_factory=list)


@dataclass
class CompsResult:
    """Peer comparison — PE/PB/EV-EBITDA percentile ranking."""
    ticker: str
    peers: list[str] = field(default_factory=list)
    pe_current: float | None = None
    pe_median_peers: float | None = None
    pe_percentile: float | None = None
    pb_current: float | None = None
    pb_median_peers: float | None = None
    ev_ebitda_current: float | None = None
    ev_ebitda_median_peers: float | None = None
    implied_price_range: tuple[float, float] | None = None


@dataclass
class DDChecklistItem:
    """Single due diligence checklist item."""
    category: str           # e.g., "财务", "法律", "运营", "市场", "管理"
    question: str
    status: str = "pending"  # pending / passed / flagged / blocked
    evidence: str = ""
    notes: str = ""


class ValuationTools:
    """Valuation and deal analysis methods."""

    @staticmethod
    def dcf_skeleton(ticker: str) -> DCFResult:
        """Generate DCF skeleton from available data. LLM fills assumptions."""
        from src.data.financial import FinancialData
        fd = FinancialData()
        info = fd.get_fundamentals(ticker)
        price = fd.get_price(ticker)

        result = DCFResult(ticker=ticker)
        needs = []

        if price:
            result.current_price = price.get("price")
        else:
            needs.append("current_price")

        if info:
            # Free cash flow proxy from available data
            result.free_cash_flow = _estimate_fcf(info)
            result.wacc = _estimate_wacc(info)
            result.shares_outstanding = info.get("market_cap") and price and info["market_cap"] / price["price"] if price and price.get("price") else None
            result.pe_current = info.get("pe_ratio")

        if result.free_cash_flow is None:
            needs.append("free_cash_flow")
        if result.wacc is None:
            needs.append("wacc")
        if result.growth_rate_5y is None:
            needs.append("growth_rate_5y")

        result.assumptions_needed = needs
        result.confidence = "high" if len(needs) == 0 else (
            "medium" if len(needs) <= 2 else "low"
        )
        return result

    @staticmethod
    def comps_summary(ticker: str, peers: list[str] | None = None) -> CompsResult:
        """Run peer comparison on key multiples."""
        from src.data.financial import FinancialData
        fd = FinancialData()

        if peers is None:
            peers = _suggest_peers(ticker)

        result = CompsResult(ticker=ticker, peers=peers)

        # Get own metrics
        info = fd.get_fundamentals(ticker)
        if info:
            result.pe_current = info.get("pe_ratio")
            result.pb_current = info.get("pb_ratio")

        # Get peer metrics
        peer_pes, peer_pbs, peer_evs = [], [], []
        for peer in peers[:5]:
            pi = fd.get_fundamentals(peer)
            if pi:
                if pi.get("pe_ratio"):
                    peer_pes.append(pi["pe_ratio"])
                if pi.get("pb_ratio"):
                    peer_pbs.append(pi["pb_ratio"])

        if peer_pes and result.pe_current:
            peer_pes.sort()
            result.pe_median_peers = peer_pes[len(peer_pes)//2]
            rank = sum(1 for p in peer_pes if p < result.pe_current) / len(peer_pes)
            result.pe_percentile = round(rank * 100, 1)

        if peer_pbs and result.pb_current:
            peer_pbs.sort()
            result.pb_median_peers = peer_pbs[len(peer_pbs)//2]

        return result

    @staticmethod
    def generate_dd_checklist(ticker: str) -> list[DDChecklistItem]:
        """Generate structured DD checklist for a ticker."""
        info = {}
        try:
            from src.data.financial import FinancialData
            fd = FinancialData()
            info = fd.get_fundamentals(ticker) or {}
        except Exception:
            pass

        return [
            DDChecklistItem("财务", f"{ticker} 最近3年营收和净利润增长率如何？",
                          evidence=f"营收增长率: {info.get('revenue_growth', 'N/A')}"),
            DDChecklistItem("财务", "资产负债率是否在合理范围？(<70%)",
                          evidence=f"D/E: {info.get('debt_to_equity', 'N/A')}"),
            DDChecklistItem("财务", "ROE是否持续高于行业平均？",
                          evidence=f"ROE: {info.get('roe', 'N/A')}"),
            DDChecklistItem("运营", "客户集中度风险如何？(第一大客户占比<30%)"),
            DDChecklistItem("运营", "供应链是否存在单点依赖？"),
            DDChecklistItem("市场", "TAM、SAM、SOM 测算"),
            DDChecklistItem("市场", f"相对于 {info.get('sector', '同行业')} 的竞争地位"),
            DDChecklistItem("管理", "管理层持股比例和激励机制"),
            DDChecklistItem("管理", "历史并购整合能力"),
            DDChecklistItem("法律", "重大诉讼/监管风险"),
            DDChecklistItem("法律", "知识产权保护状况"),
        ]


def _estimate_fcf(info: dict) -> float | None:
    """Estimate free cash flow from available fundamentals."""
    # Approximation: FCF ≈ Operating Cash Flow - CapEx
    # When only net income available, use rough proxy
    market_cap = info.get("market_cap")
    pe = info.get("pe_ratio") or info.get("trailingPE")
    if market_cap and pe and pe > 0:
        net_income = market_cap / pe
        return net_income * 0.6  # rough FCF proxy
    return None


def _estimate_wacc(info: dict) -> float | None:
    """Estimate WACC from available data."""
    de = info.get("debtToEquity")
    beta = info.get("beta") or 1.0
    # WACC ≈ E/(D+E)*Ke + D/(D+E)*Kd*(1-t)
    if de is None or de == 0:
        # Use default 10%
        return 0.10
    equity_weight = 1 / (1 + de/100) if de > 0 else 1.0
    debt_weight = 1 - equity_weight
    ke = 0.03 + beta * 0.06  # CAPM: rf + β × ERP
    kd = 0.05  # assumed cost of debt
    return equity_weight * ke + debt_weight * kd * 0.75


def _suggest_peers(ticker: str) -> list[str]:
    """Suggest peers based on ticker's sector/industry."""
    info = {}
    try:
        from src.data.financial import FinancialData
        fd = FinancialData()
        info = fd.get_fundamentals(ticker) or {}
    except Exception:
        pass

    sector = (info.get("sector") or "").lower()
    # Common peer mappings
    peer_map = {
        "technology": ["MSFT", "GOOGL", "META", "AMZN"],
        "financial": ["JPM", "BAC", "WFC", "GS"],
        "healthcare": ["JNJ", "PFE", "MRK", "ABBV"],
        "consumer": ["PG", "KO", "PEP", "WMT"],
        "energy": ["XOM", "CVX", "COP", "SLB"],
        "industrial": ["CAT", "DE", "GE", "HON"],
    }
    for key, peers in peer_map.items():
        if key in sector:
            return peers
    return ["SPY"]  # default benchmark


@dataclass
class AcquisitionSummary:
    """M&A accretion/dilution summary."""
    acquirer: str
    target: str
    deal_type: str = ""              # cash / stock / mixed
    deal_value: float | None = None
    premium_pct: float | None = None
    accretion_year1: float | None = None  # % EPS accretion
    synergies_est: float | None = None
    financing_method: str = ""
    key_risks: list[str] = field(default_factory=list)


class DealsTools:
    """M&A and corporate finance analysis."""

    @staticmethod
    def acquisition_summary(acquirer: str, target: str) -> AcquisitionSummary:
        """Generate M&A deal analysis skeleton."""
        from src.data.financial import FinancialData
        fd = FinancialData()
        a_info = fd.get_fundamentals(acquirer) or {}
        t_info = fd.get_fundamentals(target) or {}

        return AcquisitionSummary(
            acquirer=acquirer,
            target=target,
            deal_type="待确认",
            key_risks=[
                "整合风险: 企业文化融合",
                "估值风险: 支付溢价过高",
                "监管风险: 反垄断审查",
                "融资风险: 杠杆率上升",
            ],
        )


class PortfolioTools:
    """Portfolio rebalancing and attribution."""

    @staticmethod
    def rebalancing_check(holdings: list[dict]) -> dict:
        """Check portfolio drift and suggest rebalancing actions.

        Args:
            holdings: list of {"symbol": str, "weight": float, "target_weight": float}
        """
        suggestions = []
        for h in holdings:
            drift = h.get("weight", 0) - h.get("target_weight", 0)
            abs_drift = abs(drift)
            if abs_drift > 0.05:  # >5% drift
                action = "减仓" if drift > 0 else "加仓"
                suggestions.append({
                    "symbol": h["symbol"],
                    "drift_pct": round(drift * 100, 1),
                    "action": action,
                    "severity": "high" if abs_drift > 0.10 else "medium",
                })

        return {
            "holdings_count": len(holdings),
            "drifted_count": len(suggestions),
            "suggestions": suggestions,
            "max_drift": round(max([abs(h.get("weight", 0) - h.get("target_weight", 0)) for h in holdings]) * 100, 1) if holdings else 0,
        }
