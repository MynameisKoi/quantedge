"""Unit tests for MacroEventScheduler and AdaptiveM15LiveStrategy."""

from datetime import UTC, datetime, time
import pytest

from macro.scheduler import MacroEventScheduler, MarketEventWindow, macro_scheduler
from strategies.adaptive.live_strategy import AdaptiveM15LiveStrategy


def test_scheduler_event_trigger():
    # Tuesday 12:28 UTC (inside US Tier-1 macro window 12:25 - 12:45)
    test_dt = datetime(2026, 9, 8, 12, 28, tzinfo=UTC)  # Tuesday
    scheduler = MacroEventScheduler()
    should_run, event_name = scheduler.should_refresh_macro(test_dt)
    assert should_run is True
    assert event_name == "us_tier1_macro"

    # Should not trigger twice on the same day
    should_run_again, _ = scheduler.should_refresh_macro(test_dt)
    assert should_run_again is False


def test_scheduler_off_hours_no_trigger():
    # Tuesday 03:15 UTC (dead Asian off-hours)
    test_dt = datetime(2026, 9, 8, 3, 15, tzinfo=UTC)
    scheduler = MacroEventScheduler()
    should_run, event_name = scheduler.should_refresh_macro(test_dt)
    assert should_run is False
    assert event_name == "none"


def test_scheduler_eia_crude_wednesday_only():
    # Wednesday 14:26 UTC -> should trigger
    wed_dt = datetime(2026, 9, 9, 14, 26, tzinfo=UTC)  # Wednesday
    scheduler = MacroEventScheduler()
    should_run, event_name = scheduler.should_refresh_macro(wed_dt)
    assert should_run is True
    assert event_name == "eia_crude_inventories"

    # Tuesday 14:26 UTC -> should NOT trigger EIA (only on Wednesday)
    tue_dt = datetime(2026, 9, 8, 14, 26, tzinfo=UTC)
    scheduler2 = MacroEventScheduler()
    should_run, event_name = scheduler2.should_refresh_macro(tue_dt)
    assert should_run is False


def test_pre_news_blackout_guard():
    scheduler = MacroEventScheduler()
    # 3 minutes before 12:25 US macro window -> inside blackout
    dt_blackout = datetime(2026, 9, 8, 12, 22, tzinfo=UTC)
    is_blackout, reason = scheduler.is_pre_news_blackout(dt_blackout)
    assert is_blackout is True
    assert "us_tier1_macro" in reason

    # 30 minutes before 12:25 (11:55 UTC) -> outside blackout
    dt_normal = datetime(2026, 9, 8, 11, 55, tzinfo=UTC)
    is_blackout, reason = scheduler.is_pre_news_blackout(dt_normal)
    assert is_blackout is False
    assert reason == "normal"


def test_adaptive_live_strategy_interface():
    strat = AdaptiveM15LiveStrategy()
    assert strat.name == "adaptive_m15_portfolio"
    assert "XAUUSD" in strat.assets
    assert "USOIL" in strat.assets
    strat.on_regime_change("risk-on")
    sigs = strat.compute_signals({"regime": "risk-on"})
    assert isinstance(sigs, dict)
