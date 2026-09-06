"""Unit tests for Down Market Hours API Optimization."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
import pytest

from macro.asset_macro_manager import asset_macro_manager
from macro.scheduler import macro_scheduler


def test_market_down_hours_detection():
    """Verify is_market_down_hours correctly identifies weekends and active hours."""
    # Saturday 12:00 UTC
    sat_dt = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    is_down, reason = macro_scheduler.is_market_down_hours(sat_dt)
    assert is_down is True
    assert "Weekend Closure" in reason

    # Wednesday 14:30 UTC (Active market hours)
    wed_dt = datetime(2026, 9, 2, 14, 30, tzinfo=UTC)
    is_down, reason = macro_scheduler.is_market_down_hours(wed_dt)
    assert is_down is False
    assert reason == "Market Active"

    # Daily rollover break Wednesday 21:30 UTC
    rollover_dt = datetime(2026, 9, 2, 21, 30, tzinfo=UTC)
    is_down, reason = macro_scheduler.is_market_down_hours(rollover_dt)
    assert is_down is True
    assert "Daily Rollover" in reason


def test_asset_market_open_differentiates_crypto_and_fx():
    """Verify BTCUSD is open 24/7 while traditional markets close on weekends."""
    sat_dt = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)

    # Traditional assets closed on Saturday
    eur_open, eur_msg = macro_scheduler.is_asset_market_open("EURUSD", now=sat_dt)
    assert eur_open is False
    assert "Weekend Closed" in eur_msg

    gold_open, gold_msg = macro_scheduler.is_asset_market_open("XAUUSD", now=sat_dt)
    assert gold_open is False
    assert "Weekend Closed" in gold_msg

    oil_open, oil_msg = macro_scheduler.is_asset_market_open("USOIL", now=sat_dt)
    assert oil_open is False
    assert "Weekend Closed" in oil_msg

    # BTC is open 24/7
    btc_open, btc_msg = macro_scheduler.is_asset_market_open("BTCUSD", now=sat_dt)
    assert btc_open is True
    assert "24/7" in btc_msg


@pytest.mark.asyncio
async def test_fetch_and_analyze_asset_suspends_llm_when_market_closed():
    """Verify that during down/closed market hours, LLM analysis is suspended without API calls."""
    # Mock Saturday datetime
    sat_dt = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)

    with patch("macro.scheduler.datetime") as mock_dt:
        mock_dt.now.return_value = sat_dt
        mock_dt.combine = datetime.combine
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

        # Spy on agent analyze_asset
        agent = asset_macro_manager.agents["EURUSD"]
        with patch.object(agent, "analyze_asset", new_callable=AsyncMock) as mock_analyze:
            result = await asset_macro_manager.fetch_and_analyze_asset("EURUSD")

            # Must NEVER call the LLM agent during closed market hours!
            mock_analyze.assert_not_called()

            assert result["asset"] == "EURUSD"
            assert "Market closed" in result["summary"]
