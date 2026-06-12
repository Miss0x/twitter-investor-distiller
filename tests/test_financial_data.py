"""Tests for financial data module."""
import tempfile
from pathlib import Path

from src.data.financial import FinancialData


def test_cache_write_and_read():
    with tempfile.TemporaryDirectory() as td:
        fd = FinancialData(cache_dir=td)
        fd._cache_set("test_key", {"value": 42})
        cached = fd._cache_get("test_key", max_age=99999)
        assert cached == {"value": 42}


def test_cache_expiry():
    with tempfile.TemporaryDirectory() as td:
        fd = FinancialData(cache_dir=td)
        fd._cache_set("test_key", {"x": 1})
        expired = fd._cache_get("test_key", max_age=-1)  # force expired
        assert expired is None


def test_cache_miss():
    fd = FinancialData(cache_dir="/nonexistent/path/to/nowhere")
    result = fd._cache_get("never_cached", max_age=99999)
    assert result is None


def test_get_sector_uses_cache():
    """Sector lookup should reuse cached fundamentals."""
    with tempfile.TemporaryDirectory() as td:
        fd = FinancialData(cache_dir=td)
        fd._cache_set("yf_info_AAPL_latest", {"sector": "Technology", "industry": "Consumer Electronics"})
        result = fd.get_sector("AAPL")
        assert result is not None
        assert result["sector"] == "Technology"


def test_invalid_ticker_returns_none():
    """Invalid ticker should return None gracefully."""
    with tempfile.TemporaryDirectory() as td:
        fd = FinancialData(cache_dir=td)
        # This should not crash even if yfinance fails
        result = fd.get_price("NOTAREALSTOCK1234567")
        assert result is None  # cache miss, yfinance likely fails


def test_all_methods_handle_errors():
    """All methods should handle exceptions gracefully."""
    fd = FinancialData()
    assert isinstance(fd.get_earnings_calendar("INVALID"), list)
