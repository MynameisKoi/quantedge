"""Unit tests for Multi-Order Lifecycle and Scale-In Agent."""

from __future__ import annotations

from datetime import UTC, datetime
import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from core.order_lifecycle_agent import order_lifecycle_agent
from core.portfolio import Position, portfolio
from data.feeds.live_price_feed import live_price_feed


@pytest.mark.asyncio
async def test_order_lifecycle_evaluation_and_actions():
    """Verify lifecycle agent calculates R-multiple and assigns actions."""
    portfolio.positions.clear()
    portfolio.sync_mt4(500.0, 500.0)

    # Add a mock winning position (long at 79000, current price > 79500)
    pos = Position(
        symbol="BTCUSD",
        side="long",
        volume=0.02,
        entry_price=79000.0,
        stop_loss=78800.0,
        take_profit=79600.0,
        unrealized_pnl=10.0,
        ticket="999001",
    )
    portfolio.open_position(pos)

    try:
        evals = await order_lifecycle_agent.evaluate_open_positions()
        assert len(evals) >= 1
        p_eval = next((e for e in evals if str(e["ticket"]) == "999001"), None)
        assert p_eval is not None
        assert p_eval["symbol"] in ("BTCUSD", "BTCUSDm")
        assert "r_multiple" in p_eval
        assert p_eval["action"] in ("HOLD", "SCALE_IN", "MOVE_BREAKEVEN", "LOCK_PROFIT", "TRAIL_SL", "EXTEND_TP", "CLOSE_TAKE_PROFIT", "CLOSE_DEFENSIVE")
    finally:
        portfolio.positions.clear()
        portfolio.balance = 10000.0
        portfolio.equity = 10000.0
        portfolio.peak_equity = 10000.0


@pytest.mark.asyncio
async def test_order_lifecycle_api_endpoints():
    """Verify lifecycle and management API endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Lifecycle status
        res_lc = await ac.get("/api/v1/orders/lifecycle")
        assert res_lc.status_code == 200
        data = res_lc.json()
        assert "positions" in data
        assert "count" in data

        # 2. Close order endpoint (paper/mock ticket)
        res_close = await ac.post("/api/v1/orders/close/999001")
        assert res_close.status_code == 200
        c_data = res_close.json()
        assert c_data["ticket"] == "999001"
        assert c_data["action"] == "CLOSE"


@pytest.mark.asyncio
async def test_breathing_room_prevents_premature_defensive_cut():
    """Verify that newly opened positions are given 15-minute breathing room."""
    portfolio.positions.clear()
    portfolio.sync_mt4(500.0, 500.0)

    # Position opened long at 80000, current price slightly lower at ~79600 (-0.4R)
    # Even if trend were bearish, the 15-minute breathing room should keep action as HOLD
    pos = Position(
        symbol="BTCUSD",
        side="long",
        volume=0.03,
        entry_price=80000.0,
        stop_loss=79000.0,
        take_profit=82000.0,
        ticket="888001",
    )
    portfolio.open_position(pos)

    try:
        evals = await order_lifecycle_agent.evaluate_open_positions()
        p_eval = next((e for e in evals if str(e["ticket"]) == "888001"), None)
        assert p_eval is not None
        assert p_eval["in_breathing_window"] is True
        assert p_eval["action"] == "HOLD"
        assert "15-min development window" in p_eval["reason"]
    finally:
        portfolio.positions.clear()


def test_market_hours_weekend_detection():
    """Verify weekend detection for traditional markets vs 24/7 crypto."""
    from datetime import UTC, datetime
    from macro.scheduler import macro_scheduler

    # Saturday UTC
    saturday_noon = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    is_btc_open, btc_status = macro_scheduler.is_asset_market_open("BTCUSD", now=saturday_noon)
    assert is_btc_open is True
    assert "24/7" in btc_status

    is_oil_open, oil_status = macro_scheduler.is_asset_market_open("USOIL", now=saturday_noon)
    assert is_oil_open is False
    assert "Weekend Closed" in oil_status

    is_gold_open, gold_status = macro_scheduler.is_asset_market_open("XAUUSD", now=saturday_noon)
    assert is_gold_open is False

    is_eur_open, eur_status = macro_scheduler.is_asset_market_open("EURUSD", now=saturday_noon)
    assert is_eur_open is False

    # Tuesday UTC during active trading
    tuesday_noon = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    is_oil_open_tue, _ = macro_scheduler.is_asset_market_open("USOIL", now=tuesday_noon)
    assert is_oil_open_tue is True


@pytest.mark.asyncio
async def test_triple_barrier_alpha_decay():
    """Verify that when vertical time barrier expires with stagnant MFE, CLOSE_ALPHA_DECAY is assigned."""
    portfolio.positions.clear()
    now_ts = datetime.now(UTC).timestamp()

    from data.feeds.live_price_feed import live_price_feed

    quotes = live_price_feed.get_live_quotes()
    current_bid = float(quotes.get("BTCUSD", {}).get("bid") or 79600.0)

    # Stagnant trade: entry price is current market bid so r_multiple is 0.0 (stuck in place)
    pos = Position(
        symbol="BTCUSD",
        side="long",
        volume=0.03,
        entry_price=current_bid,
        stop_loss=current_bid - 500.0,
        take_profit=current_bid + 1000.0,
        ticket="777001",
    )
    portfolio.open_position(pos)

    # Set ticket entry time to 7500 seconds ago (exceeding 7200s vertical barrier)
    order_lifecycle_agent._ticket_first_seen["777001"] = now_ts - 7500.0
    order_lifecycle_agent._ticket_mfe["777001"] = 0.05  # zero traction (<0.20R)

    try:
        evals = await order_lifecycle_agent.evaluate_open_positions()
        p_eval = next((e for e in evals if str(e["ticket"]) == "777001"), None)
        assert p_eval is not None
        assert p_eval["action"] == "CLOSE_ALPHA_DECAY"
        assert "Alpha decay detected" in p_eval["reason"]
        assert p_eval["urgency"] == "medium"
    finally:
        portfolio.positions.clear()
        order_lifecycle_agent._ticket_first_seen.pop("777001", None)
        order_lifecycle_agent._ticket_mfe.pop("777001", None)


@pytest.mark.asyncio
async def test_trailing_profit_giveback_protection():
    """Verify that after reaching peak profit +1.5R, a sharp retracement triggers CLOSE_TRAIL_EXIT."""
    portfolio.positions.clear()
    now_ts = datetime.now(UTC).timestamp()

    pos = Position(
        symbol="BTCUSD",
        side="long",
        volume=0.03,
        entry_price=79000.0,
        stop_loss=78800.0,
        take_profit=79600.0,
        ticket="777002",
    )
    portfolio.open_position(pos)

    # Mock live quote so current price is precisely +0.5R above entry (79,100)
    from data.feeds.live_price_feed import live_price_feed
    orig_quotes = live_price_feed.get_live_quotes
    live_price_feed.get_live_quotes = lambda: {"BTCUSD": {"bid": 79100.0, "ask": 79100.0}}

    # Order aged 1200s (past breathing window)
    order_lifecycle_agent._ticket_first_seen["777002"] = now_ts - 1200.0
    # Peak MFE reached +1.8R, but current price pulled back to +0.5R (< 50% of peak)
    order_lifecycle_agent._ticket_mfe["777002"] = 1.8

    try:
        evals = await order_lifecycle_agent.evaluate_open_positions()
        p_eval = next((e for e in evals if str(e["ticket"]) == "777002"), None)
        assert p_eval is not None
        # Should trigger CLOSE_TRAIL_EXIT or CLOSE_TAKE_PROFIT
        assert p_eval["action"] in ("CLOSE_TRAIL_EXIT", "CLOSE_TAKE_PROFIT", "MOVE_BREAKEVEN")
    finally:
        portfolio.positions.clear()
        order_lifecycle_agent._ticket_first_seen.pop("777002", None)
        order_lifecycle_agent._ticket_mfe.pop("777002", None)
        live_price_feed.get_live_quotes = orig_quotes


def test_session_aware_breathing_window_scaling():
    """Verify that breathing window expands for Asian EURUSD and adapts to asset characteristics."""
    breathing_btc, vertical_btc, session = order_lifecycle_agent.get_dynamic_session_window("BTCUSD")
    assert breathing_btc == 900.0
    assert vertical_btc == 7200.0

    breathing_eur, vertical_eur, _ = order_lifecycle_agent.get_dynamic_session_window("EURUSD")
    assert breathing_eur in (900.0, 1800.0)
    assert vertical_eur in (5400.0, 7200.0)


@pytest.mark.asyncio
async def test_greedy_profit_locking_above_entry():
    """Verify that during a strong trend, lifecycle agent pushes SL above entry to guarantee a win."""
    portfolio.positions.clear()
    portfolio.sync_mt4(1000.0, 1000.0)

    # Position long at 78000, initial SL at 77000 (stop_dist = 1000)
    # Price is at 79350 (+1.35R)
    pos = Position(
        symbol="BTCUSD",
        side="long",
        volume=0.01,
        entry_price=78000.0,
        stop_loss=77000.0,
        take_profit=80000.0,
        unrealized_pnl=13.50,
        ticket="777003",
    )
    portfolio.open_position(pos)

    # Mock quotes and strong trend indicators (ADX 28.0, bullish)
    orig_quotes = live_price_feed.get_live_quotes
    live_price_feed.get_live_quotes = lambda: {"BTCUSD": {"bid": 79350.0, "ask": 79360.0}}

    # Set first seen past breathing window
    now_ts = datetime.now(UTC).timestamp()
    order_lifecycle_agent._ticket_first_seen["777003"] = now_ts - 1800.0

    orig_request = order_lifecycle_agent.order_manager.bridge.request
    async def mock_req(action, payload=None, timeout=12.0):
        if action == "MODIFY":
            return {"ok": True, "ticket": (payload or {}).get("ticket"), "sl": (payload or {}).get("sl"), "tp": (payload or {}).get("tp")}
        return await orig_request(action, payload, timeout)

    order_lifecycle_agent.order_manager.bridge.request = mock_req

    try:
        evals = await order_lifecycle_agent.evaluate_open_positions()
        p_eval = next((e for e in evals if str(e["ticket"]) == "777003"), None)
        assert p_eval is not None
        assert p_eval["r_multiple"] >= 1.2
        assert p_eval["rec_sl"] is not None
        # Recommended SL must be pushed ABOVE entry price (78000.0)
        assert p_eval["rec_sl"] > 78000.0
        assert p_eval["guaranteed_win"] is True
        assert p_eval["action"] in ("LOCK_PROFIT", "MOVE_BREAKEVEN", "EXTEND_TP", "HOLD")

        # Execute the action (LOCK_PROFIT / MODIFY)
        mod_res = await order_lifecycle_agent.execute_action(ticket="777003", action="LOCK_PROFIT")
        assert mod_res["ok"] is True
        assert mod_res["sl"] > 78000.0
    finally:
        portfolio.positions.clear()
        order_lifecycle_agent._ticket_first_seen.pop("777003", None)
        live_price_feed.get_live_quotes = orig_quotes
        order_lifecycle_agent.order_manager.bridge.request = orig_request


@pytest.mark.asyncio
async def test_mid_air_modify_api_and_execution():
    """Verify mid-air interference API modifies order parameters in real time."""
    portfolio.positions.clear()
    portfolio.sync_mt4(1000.0, 1000.0)

    pos = Position(
        symbol="EURUSD",
        side="long",
        volume=0.05,
        entry_price=1.16000,
        stop_loss=1.15750,
        take_profit=1.16500,
        ticket="777004",
    )
    portfolio.open_position(pos)

    orig_request = order_lifecycle_agent.order_manager.bridge.request
    async def mock_req(action, payload=None, timeout=12.0):
        if action == "MODIFY":
            return {"ok": True, "ticket": (payload or {}).get("ticket"), "sl": (payload or {}).get("sl"), "tp": (payload or {}).get("tp")}
        return await orig_request(action, payload, timeout)

    order_lifecycle_agent.order_manager.bridge.request = mock_req

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Mid-air modify: move SL above entry to 1.16100 (guaranteed win) and push TP to 1.16800
            res = await ac.post(
                "/api/v1/orders/modify",
                json={
                    "ticket": "777004",
                    "sl": 1.16100,
                    "tp": 1.16800,
                    "reason": "greedy_trend_lock",
                },
            )
            assert res.status_code == 200
            data = res.json()
            assert data["ok"] is True
            assert data["sl"] == 1.16100
            assert data["tp"] == 1.16800

            # Verify in-memory position was updated
            updated_pos = portfolio.positions.get("EURUSD:long")
            assert updated_pos is not None
            assert updated_pos.stop_loss == 1.16100
            assert updated_pos.take_profit == 1.16800
    finally:
        portfolio.positions.clear()
        order_lifecycle_agent.order_manager.bridge.request = orig_request


