"""Earnings calendar + Price alert cards."""
from __future__ import annotations
from src.cards.base import Card
from src.cards import register


@register
class EarningsCalendarCard(Card):
    name = "earnings_calendar"
    display_title = "财报日历"
    template = "earnings_calendar.html"

    def get_data(self) -> dict:
        try:
            from src.admin.auth import get_current_user
            from src.multi_tenant.config import PerUserConfig
            import contextvars as _cv
            req = _cv.ContextVar("earn_req", default=None).get()
            tenant_id = "default"
            if req is not None:
                user = get_current_user(req)
                if user:
                    tenant_id = str(user.id)
            cfg = PerUserConfig(tenant_id)
            watchlist = cfg.load().get("watchlist", [])
            if not watchlist:
                return {"tickers": [], "earnings": []}

            from src.data.financial import FinancialData
            fd = FinancialData()
            earnings = []
            for ticker in watchlist[:10]:
                info = fd.get_fundamentals(ticker)
                cal = fd.get_earnings_calendar(ticker)
                price = fd.get_price(ticker)
                if info and price:
                    earnings.append({
                        "ticker": ticker,
                        "date": cal[0]["date"][:10] if cal else "待确认",
                        "expected_eps": f"${info.get('revenue_growth', 'N/A')}",
                        "price": price.get("price"),
                        "pe": info.get("pe_ratio"),
                    })
            return {"tickers": watchlist, "earnings": earnings}
        except Exception:
            return {"tickers": [], "earnings": [], "error": True}


@register
class PriceAlertsCard(Card):
    name = "price_alerts"
    display_title = "价格预警"
    template = "price_alerts.html"

    def get_data(self) -> dict:
        try:
            from src.admin.auth import get_current_user
            from src.multi_tenant.config import PerUserConfig
            import contextvars as _cv
            req = _cv.ContextVar("alert_req", default=None).get()
            tenant_id = "default"
            if req is not None:
                user = get_current_user(req)
                if user:
                    tenant_id = str(user.id)
            cfg = PerUserConfig(tenant_id)
            return {"alerts": cfg.load().get("price_alerts", [])}
        except Exception:
            return {"alerts": []}
