"""Tests for Institutional Live MT4 Chart & Analysis Browser API."""

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from core.portfolio import Position, portfolio


@pytest.fixture
def test_app():
    return app


@pytest.mark.asyncio
async def test_chart_endpoint_all_assets_and_timeframes(test_app):
    """Verify all 4 CFD assets and all 7 supported timeframes return valid OHLCV and indicators."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for asset in ["BTCUSD", "XAUUSD", "EURUSD", "USOIL"]:
            for tf in ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]:
                resp = await client.get(f"/api/v1/analytics/chart/{asset}?timeframe={tf}&limit=50")
                assert resp.status_code == 200, f"Failed for {asset} {tf}: {resp.text}"
                data = resp.json()

                # Schema verification
                assert data["asset"] == asset
                assert data["timeframe"] == tf
                assert "live_price" in data and data["live_price"] > 0
                assert "bid" in data and "ask" in data
                assert "spread" in data

                # Candles verification
                candles = data["candles"]
                assert len(candles) > 0, f"No candles returned for {asset} {tf}"
                assert len(candles) <= 50

                # Strictly ascending timestamps
                for i in range(1, len(candles)):
                    assert candles[i]["time"] >= candles[i - 1]["time"]

                # Candle price bounds
                last_c = candles[-1]
                assert last_c["high"] >= last_c["low"]
                assert last_c["high"] >= min(last_c["open"], last_c["close"])
                assert last_c["low"] <= max(last_c["open"], last_c["close"])

                # Technical Indicator verification
                indicators = data["indicators"]
                assert "ema9" in indicators and len(indicators["ema9"]) > 0
                assert "ema21" in indicators and len(indicators["ema21"]) > 0
                assert "ema50" in indicators and len(indicators["ema50"]) > 0
                assert "donchian_high" in indicators and len(indicators["donchian_high"]) > 0
                assert "donchian_low" in indicators and len(indicators["donchian_low"]) > 0
                assert "donchian_poc" in indicators and len(indicators["donchian_poc"]) > 0

                # Summary verification
                summary = data["indicators_summary"]
                assert "ema9" in summary
                assert "ema21" in summary
                assert "ema50" in summary
                assert "atr" in summary
                assert "rsi" in summary


@pytest.mark.asyncio
async def test_chart_endpoint_active_position_overlay(test_app):
    """Verify that when a live MT4 position is active, its coordinates are provided in active_position."""
    transport = ASGITransport(app=test_app)

    # Open mock BTCUSD position
    portfolio.positions.clear()
    portfolio.open_position(
        Position(
            symbol="BTCUSD",
            side="long",
            volume=0.02,
            entry_price=79779.89,
            stop_loss=79495.85,
            take_profit=80292.80,
            unrealized_pnl=14.50,
            ticket="201205151",
        )
    )

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Check BTCUSD has active position
        resp = await client.get("/api/v1/analytics/chart/BTCUSD?timeframe=M15&limit=30")
        assert resp.status_code == 200
        data = resp.json()
        pos = data["active_position"]
        assert pos is not None
        assert pos["has_position"] is True
        assert pos["ticket"] == "201205151"
        assert pos["side"] == "LONG"
        assert pos["volume"] == 0.02
        assert pos["entry_price"] == 79779.89
        assert pos["stop_loss"] == 79495.85
        assert pos["take_profit"] == 80292.80

        # 2. Check XAUUSD has NO active position
        resp_xau = await client.get("/api/v1/analytics/chart/XAUUSD?timeframe=M15&limit=30")
        assert resp_xau.status_code == 200
        data_xau = resp_xau.json()
        assert data_xau["active_position"] is None

    # Clean up
    portfolio.positions.clear()
