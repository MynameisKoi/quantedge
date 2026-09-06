"""Unit tests for OrderDecisionAgent and order dispatch endpoints."""

from unittest.mock import AsyncMock, patch
import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from core.order_agent import order_decision_agent
from core.portfolio import portfolio


@pytest.fixture(autouse=True)
def reset_portfolio():
    yield
    portfolio.positions.clear()
    portfolio.balance = 10000.0
    portfolio.equity = 10000.0
    portfolio.peak_equity = 10000.0


def test_order_decision_agent_sizing_and_parameters():
    """Verify that OrderDecisionAgent computes all parameters: size, symbol, price, SL, TP."""
    portfolio.sync_mt4(501.94, 501.94)
    decision = order_decision_agent.decide_order(asset="USOIL", force=True)

    assert decision["approved"] is True
    assert decision["asset"] == "USOIL"
    assert decision["symbol"] == "USOILm"  # mapped to broker symbol
    assert decision["side"] in ("long", "short")
    assert decision["volume"] >= 0.01
    assert decision["price"] > 0
    assert decision["stop_loss"] > 0
    assert decision["take_profit"] > 0
    assert decision["breakeven_trigger"] > 0
    assert "Order Decision Agent approved" in decision["rationale"]
    assert "USOILm" in decision["rationale"]


@pytest.mark.asyncio
async def test_order_decision_agent_fire_order():
    """Verify firing a long order routes and records properly without hitting real broker."""
    portfolio.sync_mt4(501.94, 501.94)
    mock_res = {
        "status": "submitted",
        "bridge": {"ok": True, "ticket": 999101, "payload": {"ticket": 999101, "price": 79800.0}},
    }
    with patch.object(order_decision_agent.order_manager, "submit", new_callable=AsyncMock, return_value=mock_res), \
         patch.object(order_decision_agent, "_record_order_lock"):
        res = await order_decision_agent.fire_order(asset="BTCUSD", side="long", force=True)

        assert res["ok"] is True
        assert res["status"] in ("executed", "submitted")
        assert res["ticket"] == "999101"
        assert res["decision"]["side"] == "long"
        assert res["decision"]["order_cmd"] == "buy"
        assert res["decision"]["stop_loss"] < res["decision"]["price"]
        assert res["decision"]["take_profit"] > res["decision"]["price"]


@pytest.mark.asyncio
async def test_order_decision_agent_fire_sell_order():
    """Verify firing a SELL/SHORT order routes with correct sell command and inverse SL/TP."""
    portfolio.sync_mt4(501.94, 501.94)
    mock_res = {
        "status": "submitted",
        "bridge": {"ok": True, "ticket": 999102, "payload": {"ticket": 999102, "price": 79800.0}},
    }
    with patch.object(order_decision_agent.order_manager, "submit", new_callable=AsyncMock, return_value=mock_res), \
         patch.object(order_decision_agent, "_record_order_lock"):
        res = await order_decision_agent.fire_order(asset="BTCUSD", side="short", force=True)

        assert res["ok"] is True
        assert res["status"] in ("executed", "submitted")
        assert res["ticket"] == "999102"
        assert res["decision"]["side"] == "short"
        assert res["decision"]["order_cmd"] == "sell"
        # In a short order, SL must be above entry and TP below entry
        assert res["decision"]["stop_loss"] > res["decision"]["price"]
        assert res["decision"]["take_profit"] < res["decision"]["price"]


@pytest.mark.asyncio
async def test_api_order_decision_and_fire_routes():
    """Verify FastAPI routes for /orders/decision and /orders/fire using mock bridge."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Preview Decision
        r_dec = await ac.get("/api/v1/orders/decision/USOIL?force=true")
        assert r_dec.status_code == 200
        dec_data = r_dec.json()
        assert dec_data["asset"] == "USOIL"
        assert dec_data["symbol"] == "USOILm"
        assert dec_data["volume"] >= 0.01

        # 2. Fire Order Endpoint for 24/7 asset BTCUSD (mocked)
        mock_res = {
            "status": "submitted",
            "bridge": {"ok": True, "ticket": 999103, "payload": {"ticket": 999103, "price": 79800.0}},
        }
        with patch.object(order_decision_agent.order_manager, "submit", new_callable=AsyncMock, return_value=mock_res), \
             patch.object(order_decision_agent, "_record_order_lock"):
            r_fire = await ac.post("/api/v1/orders/fire", json={"asset": "BTCUSD", "side": "short", "force": True})
            assert r_fire.status_code == 200
            fire_data = r_fire.json()
            assert fire_data["ok"] is True
            assert fire_data["ticket"] == "999103"
            assert fire_data["decision"]["side"] == "short"
            assert fire_data["decision"]["order_cmd"] == "sell"


def test_order_decision_agent_sell_order():
    """Verify that OrderDecisionAgent handles SELL (SHORT) orders with correct parameters."""
    portfolio.sync_mt4(501.94, 501.94)
    decision = order_decision_agent.decide_order(asset="BTCUSD", side="short", force=True)

    assert decision["approved"] is True
    assert decision["asset"] == "BTCUSD"
    assert decision["side"] == "short"
    assert decision["order_cmd"] == "sell"
    assert decision["volume"] >= 0.01
    assert decision["price"] > 0
    # For a SELL/SHORT order, Stop Loss must be ABOVE entry price and Take Profit must be BELOW entry price
    assert decision["stop_loss"] > decision["price"]
    assert decision["take_profit"] < decision["price"]
    assert "SHORT" in decision["rationale"] or "short" in decision["rationale"]


