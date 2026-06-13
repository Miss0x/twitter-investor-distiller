"""Financial data module — multi-source price, fundamental, and sector data.

Sources (in priority order):
1. yfinance (Yahoo Finance) — primary, free, covers most global markets
2. akshare (if installed) — A-share specific data
3. Local JSON cache — avoids redundant API calls

Dimensions (matching UZI-Skill lite tier +):
1. 实时行情 (price, volume, 52w range, market cap)
2. 财报 (PE, PB, ROE, growth, margins, D/E, dividend yield)
3. 行业 (sector, industry, peers)
4. 技术指标 (RSI, MACD, SMA, volatility)
5. 机构评级 (analyst consensus, target price)
6. 资金流向 (net inflows A-share only)
7. 财报日历 (earnings dates)
8. 新闻情绪 (yf news sentiment proxy)
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

    def get_technical_indicators(self, symbol: str) -> dict | None:
        """Get RSI, MACD, SMA, volatility indicators."""
        key = self._cache_key("yf_tech", symbol, "latest")
        cached = self._cache_get(key, max_age=300)
        if cached:
            return cached

        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="6mo")
            if len(hist) < 20:
                return None

            close = hist["Close"]
            # RSI(14)
            delta = close.diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta).clip(lower=0).rolling(14).mean()
            rs = gain / loss.replace(0, 1e-10)
            rsi = 100 - (100 / (1 + rs.iloc[-1]))

            # MACD
            ema12 = close.ewm(span=12).mean()
            ema26 = close.ewm(span=26).mean()
            macd = ema12.iloc[-1] - ema26.iloc[-1]
            signal = (ema12 - ema26).ewm(span=9).mean().iloc[-1]

            # SMA
            sma20 = close.rolling(20).mean().iloc[-1]
            sma50 = close.rolling(min(50, len(close))).mean().iloc[-1]

            # Volatility
            returns = close.pct_change().dropna()
            vol = float(returns.std() * (252**0.5))  # annualized

            result = {
                "symbol": symbol,
                "rsi_14": round(float(rsi), 1),
                "macd": round(float(macd), 4),
                "macd_signal": round(float(signal), 4),
                "sma_20": round(float(sma20), 2),
                "sma_50": round(float(sma50), 2),
                "price_vs_sma20": round(float(close.iloc[-1] / sma20 - 1) * 100, 1),
                "volatility_annual": round(vol * 100, 1),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            self._cache_set(key, result)
            return result
        except Exception:
            return None

    def get_analyst_ratings(self, symbol: str) -> dict | None:
        """Get analyst consensus, target price, and recommendation trend."""
        key = self._cache_key("yf_rating", symbol, "latest")
        cached = self._cache_get(key, max_age=86400)
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
                "recommendation": info.get("recommendationKey"),
                "target_mean": info.get("targetMeanPrice"),
                "target_high": info.get("targetHighPrice"),
                "target_low": info.get("targetLowPrice"),
                "num_analysts": info.get("numberOfAnalystOpinions"),
                "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            if result["current_price"] and result["target_mean"]:
                result["upside_pct"] = round(
                    (result["target_mean"] / result["current_price"] - 1) * 100, 1
                )
            self._cache_set(key, result)
            return result
        except Exception:
            return None

    def get_news_sentiment(self, symbol: str) -> dict | None:
        """Get recent news count and basic sentiment proxy."""
        key = self._cache_key("yf_news", symbol, "latest")
        cached = self._cache_get(key, max_age=3600)
        if cached:
            return cached

        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            news = ticker.news or []
            if not news:
                return {"symbol": symbol, "recent_articles": 0, "source": "yfinance"}

            # Simple sentiment proxy: count recent articles
            result = {
                "symbol": symbol,
                "recent_articles": len(news),
                "titles": [n.get("title", "")[:100] for n in news[:5]],
                "source": "yfinance",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            self._cache_set(key, result)
            return result
        except Exception:
            return None

    def get_all_dimensions(self, symbol: str, depth: str = "standard") -> dict:
        """Get all available dimensions for a ticker.

        Args:
            symbol: Ticker symbol (e.g., "AAPL")
            depth: "lite" (7 dims) / "standard" (8 dims) / "deep" (8 dims + fundamentals)

        Returns dict with section keys: price, fundamentals, sector, technical,
               analyst, earnings, news, plus meta.depth and meta.coverage_pct
        """
        result: dict[str, Any] = {"_meta": {"symbol": symbol, "depth": depth, "fetched": 0, "total": 0}}

        dims = [
            ("price", self.get_price(symbol)),
            ("fundamentals", self.get_fundamentals(symbol)),
            ("sector", self.get_sector(symbol)),
            ("technical", self.get_technical_indicators(symbol)),
            ("analyst", self.get_analyst_ratings(symbol)),
            ("earnings", self.get_earnings_calendar(symbol)),
            ("news", self.get_news_sentiment(symbol)),
        ]

        total = 0
        fetched = 0
        for name, data in dims:
            if depth == "lite" and name in ("earnings", "news"):
                continue  # lite 只拿核心 5 维
            total += 1
            result[name] = data
            if data is not None:
                fetched += 1

        result["_meta"]["total"] = total
        result["_meta"]["fetched"] = fetched
        result["_meta"]["coverage_pct"] = round(fetched / total * 100, 1) if total else 0
        return result

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
