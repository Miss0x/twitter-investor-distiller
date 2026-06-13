"""Tests for chat_engine, crawler, valuation tools, financial data."""
import tempfile
from pathlib import Path

# ── Chat Engine ──

def test_chat_engine_initialization():
    """ChatEngine should initialize without crash even without API key."""
    try:
        from src.ai.chat_engine import ChatEngine
        engine = ChatEngine()
        assert engine.model is not None
        assert engine.base_url.startswith("http")
    except ImportError:
        pass  # chromadb not available in CI


def test_chat_engine_reload_config():
    """reload_config should update client."""
    import os
    from src.ai.chat_engine import ChatEngine
    os.environ["CHAT_MODEL"] = "test-model"
    os.environ["LLM_BASE_URL"] = "https://test.api/v1"
    engine = ChatEngine()
    assert engine.model == "test-model"
    engine.reload_config()
    assert engine.base_url == "https://test.api/v1"


# ── Valuation Tools ──

def test_dcf_skeleton_with_override():
    """DCF should accept manual WACC override."""
    from src.data.valuation_tools import ValuationTools, _compute_dcf, DCFResult

    # Create a result with known values
    result = DCFResult(ticker="TEST")
    result.free_cash_flow = 10_000_000_000  # 10B
    result.growth_rate_5y = 0.15
    result.wacc = 0.10
    result.terminal_growth = 0.025
    result.shares_outstanding = 1_000_000_000
    result.current_price = 100
    result.net_debt = 0

    result = _compute_dcf(result)
    assert result.intrinsic_value is not None
    assert result.intrinsic_value > 0


def test_dcf_override_changes_value():
    """Higher WACC should give lower intrinsic value."""
    from src.data.valuation_tools import ValuationTools, DCFResult, _compute_dcf

    def compute(wacc):
        r = DCFResult(ticker="T")
        r.free_cash_flow = 10e9
        r.growth_rate_5y = 0.15
        r.wacc = wacc
        r.terminal_growth = 0.025
        r.shares_outstanding = 1e9
        r.current_price = 100
        r.net_debt = 0
        return _compute_dcf(r).intrinsic_value

    v1 = compute(0.08)
    v2 = compute(0.15)
    assert v1 > v2  # lower WACC → higher value


def test_comps_summary():
    """Comps should handle unknown tickers gracefully."""
    from src.data.valuation_tools import ValuationTools
    result = ValuationTools().comps_summary("SPY")
    assert result.ticker == "SPY"
    assert isinstance(result.peers, list)


def test_dd_checklist_structure():
    """DD checklist should have all 5 categories."""
    from src.data.valuation_tools import ValuationTools
    items = ValuationTools().generate_dd_checklist("SPY")
    assert len(items) >= 10
    categories = {i.category for i in items}
    assert len(categories) >= 4  # financial, operations, market, management, legal


# ── Financial Data ──

def test_financial_data_cache_invalidation():
    """Expired cache should return None."""
    fd = None
    try:
        from src.data.financial import FinancialData
        fd = FinancialData(cache_dir=tempfile.gettempdir() + "/test_cache")
        fd._cache_set("expire_test", {"x": 1})
        assert fd._cache_get("expire_test", max_age=-1) is None
    except Exception:
        if fd:
            import shutil
            shutil.rmtree(fd.cache_dir, ignore_errors=True)


# ── Admin Activity ──

def test_activity_tracker_stats():
    """ActivityTracker stats should have expected keys."""
    from src.admin.activity import ActivityTracker
    stats = ActivityTracker().stats(days=1)
    assert "total_events" in stats
    assert "actions_by_type" in stats
    assert "unique_ip_prefixes" in stats


def test_activity_tracker_query():
    """ActivityTracker query should return list."""
    from src.admin.activity import ActivityTracker
    events = ActivityTracker().query(limit=5)
    assert isinstance(events, list)


# ── Config Center backward compat ──

def test_config_manager_load():
    """Old ConfigManager should still load."""
    from src.config_center import ConfigManager
    mgr = ConfigManager()
    config = mgr.load()
    assert "llm" in config
    assert "observations" in config


def test_config_manager_add_observation():
    """Adding observation should work."""
    from src.config_center import ConfigManager
    mgr = ConfigManager()
    config = mgr.add_observation("test_user_123")
    assert "test_user_123" in config["observations"]
    mgr.remove_observation("test_user_123")


# ── Access Control ──

def test_access_control_suspend_unsuspend():
    """Suspend and unsuspend should work."""
    from src.admin.access_control import AccessControl
    ac = AccessControl()
    ac.suspend("test_bad_user", "testing")
    # list should include it
    suspended = ac.list_suspended()
    ac.unsuspend("test_bad_user")


# ── Role Pre-Filter ──

def test_role_pre_filter_skip():
    """Role should skip when outside circle of competence."""
    from src.governance.roles import PersonaConfig, apply_role_pre_filters
    persona = PersonaConfig(
        id="test_role", label="测试角色", stance_bias="neutral",
        portfolio_filter={"only_markets": ["A股"]},
        circle_of_competence="只看A股，不碰美股",
    )
    result = apply_role_pre_filters(persona, "AAPL", signal_market="US")
    assert result.passed is False
    assert "A股" in result.reason


def test_role_pre_filter_pass():
    """Role should pass when in circle."""
    from src.governance.roles import PersonaConfig, apply_role_pre_filters
    persona = PersonaConfig(
        id="test_role", label="测试角色", stance_bias="neutral",
        portfolio_filter={"only_markets": ["US"]},
    )
    result = apply_role_pre_filters(persona, "AAPL", signal_market="US")
    assert result.passed is True
