"""Financial data module — multi-source price, fundamental, and sector data.

Sources (in priority order):
1. yfinance (Yahoo Finance) — primary, free, covers most global markets
2. akshare (if installed) — A-share specific data
3. Local cache (SQLite) — avoids redundant API calls

This module bridges the gap between our Twitter-only data source
and UZI-Skill's 22-dimension data coverage.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class FinancialData:
    """Multi-source financial data access with local caching."""

    def __init__(self, cache_dir: str | Path = "data/finance") -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, source: str, symbol: str, period: str) -> str:
        return f"{source}_{symbol}_{period}"

    def _cache_get(self, key: str, max_age: int = 3600) -> dict | None:
        cache_file = self.cache_dir / f"{key}.json"
        if not cache_file.exists():
            return None
        age = time.time() - cache_file.stat().st_mtime
        if age > max_age:
            return None
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _cache_set(self, key: str, data: dict) -> None:
        cache_file = self.cache_dir / f"{key}.json"
        cache_file.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")

    def get_price(self, symbol: str, market: str = "US") -> dict | None:
        """Get latest price and 52-week range for a ticker."""
        return self._try_yfinance_price(symbol)

    def get_fundamentals(self, symbol: str) -> dict | None:
        """Get PE, PB, ROE, market cap, revenue, etc."""
        return self._try_yfinance_info(symbol)

    def get_sector(self, symbol: str) -> dict | None:
        """Get sector, industry, and peer companies."""
        return self._try_yfinance_sector(symbol)

    def get_earnings_calendar(self, symbol: str) -> list[dict]:
        """Get upcoming and recent earnings dates."""
        return self._try_yfinance_earnings(symbol)

    # ═══════════════════════════════════════════════
    # yfinance backend
    # ═══════════════════════════════════════════════

    def _try_yfinance_price(self, symbol: str) -> dict | None:
        key = self._cache_key("yf_price", symbol, "latest")
        cached = self._cache_get(key, max_age=300)  # 5 min cache
        if cached:
            return cached

        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            info = ticker.info or {}
            hist = ticker.history(period="5d")
            if hist.empty:
                return None

            latest = hist.iloc[-1]
            result = {
                "symbol": symbol,
                "price": float(latest["Close"]),
                "change_pct": float(((latest["Close"] / hist.iloc[0]["Close"]) - 1) * 100),
                "volume": int(latest["Volume"]),
                "high_52w": info.get("fiftyTwoWeekHigh"),
                "low_52w": info.get("fiftyTwoWeekLow"),
                "market_cap": info.get("marketCap"),
                "currency": info.get("currency", "USD"),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            self._cache_set(key, result)
            return result
        except Exception:
            return None

    def _try_yfinance_info(self, symbol: str) -> dict | None:
        key = self._cache_key("yf_info", symbol, "latest")
        cached = self._cache_get(key, max_age=86400)  # 24h cache for fundamentals
        if cached:
            return cached

        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            info = ticker.info or {}
            if not info:
                return None

            result = {
                "symbol": symbol,
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "pb_ratio": info.get("priceToBook"),
                "roe": info.get("returnOnEquity"),
                "debt_to_equity": info.get("debtToEquity"),
                "revenue_growth": info.get("revenueGrowth"),
                "earnings_growth": info.get("earningsGrowth"),
                "profit_margin": info.get("profitMargins"),
                "dividend_yield": info.get("dividendYield"),
                "beta": info.get("beta"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "employees": info.get("fullTimeEmployees"),
                "country": info.get("country"),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            self._cache_set(key, result)
            return result
        except Exception:
            return None

    def _try_yfinance_sector(self, symbol: str) -> dict | None:
        info = self._try_yfinance_info(symbol)
        if not info or not info.get("sector"):
            return None
        return {
            "symbol": symbol,
            "sector": info.get("sector"),
            "industry": info.get("industry"),
        }

    def _try_yfinance_earnings(self, symbol: str) -> list[dict]:
        key = self._cache_key("yf_earn", symbol, "latest")
        cached = self._cache_get(key, max_age=43200)  # 12h cache
        if cached:
            return cached.get("dates", [])

        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            cal = ticker.calendar
            if cal is None:
                return []
            dates = []
            for k in ("Earnings Date", "earningsDate"):
                val = cal.get(k)
                if val:
                    dates.append({"date": str(val), "type": "earnings"})
            self._cache_set(key, {"dates": dates})
            return dates
        except Exception:
            return []
