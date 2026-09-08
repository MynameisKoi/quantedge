"""Comprehensive test suite for Stop Loss/Take Profit structural upgrades,
MT4 History Parser, IntentGuard Deliberation Tracking, and 00:00 UTC Midnight Learner.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import pytest
import httpx

from api.main import app
from config.settings import settings
from core.portfolio import portfolio
from core.rl.quantedge_tracker import QuantEdgeTracker, quantedge_tracker
from core.rl.intentguard_tracker import IntentGuardTracker, intentguard_tracker
from core.rl.midnight_learner import MidnightExecutionAuditor, midnight_learner
from execution.bridge.mt4_history_parser import MT4HistoryParser, mt4_history_parser
from risk.position_sizer import MINIMUM_STOP_FLOORS, atr_position_size


def test_position_sizer_minimum_floors_and_breathing_room():
    """Verify that compressed ATR values do not suffocate trades due to minimum stop floors."""
    portfolio.balance = 2000.0
    portfolio.equity = 2000.0

    # 1. Gold with compressed ATR (e.g. $2.50) -> floor of $20.00 must override
    gold_sizing = atr_position_size(
        price=4420.0,
        atr=2.50,
        asset="XAUUSD",
        atr_stop_mult=2.5,
    )
    assert gold_sizing["stop_distance"] >= MINIMUM_STOP_FLOORS["XAUUSD"]
    assert gold_sizing["stop_distance"] >= 20.0
    assert gold_sizing["volume"] > 0
    # Dollar risk is strictly 1% ($20 on $2,000 equity)
    assert gold_sizing["risk_amount"] == 20.0

    # 2. Bitcoin with compressed ATR ($80) -> floor of $850 must override
    btc_sizing = atr_position_size(
        price=79200.0,
        atr=80.0,
        asset="BTCUSD",
        atr_stop_mult=2.8,
    )
    assert btc_sizing["stop_distance"] >= MINIMUM_STOP_FLOORS["BTCUSD"]
    assert btc_sizing["stop_distance"] >= 850.0

    # 3. EURUSD with compressed ATR (0.00025 / 2.5 pips) -> floor of 18 pips (0.0018) must override
    eur_sizing = atr_position_size(
        price=1.1625,
        atr=0.00025,
        asset="EURUSD",
        atr_stop_mult=2.2,
    )
    assert eur_sizing["stop_distance"] >= MINIMUM_STOP_FLOORS["EURUSD"]
    assert eur_sizing["stop_distance"] >= 0.0018


def test_position_sizer_structural_anchoring():
    """Verify that a structural swing low/high outside the ATR stop expands the stop distance."""
    portfolio.equity = 2500.0
    # Long setup at $4420, ATR is $4 (ATR stop = $10), but 5-bar swing low is at $4395 ($25 distance)
    sizing = atr_position_size(
        price=4420.0,
        atr=4.0,
        asset="XAUUSD",
        atr_stop_mult=2.5,
        structural_stop_price=4395.0,
    )
    assert sizing["stop_distance"] >= 25.0
    assert sizing["stop_loss_long"] <= 4395.0
    # Verify inverse volume scaling: larger stop distance = smaller lot size, protecting account equity
    assert sizing["volume"] <= 0.02


def test_mt4_history_parser_metrics_calculation(tmp_path: Path):
    """Verify performance metrics calculation (Win Rate, Net PnL, Profit Factor, Max Drawdown)."""
    parser = MT4HistoryParser(log_dir=str(tmp_path))

    sample_trades = [
        {"ticket": "101", "symbol": "XAUUSD", "side": "buy", "lots": 0.01, "open_price": 4420.0, "close_price": 4435.0, "close_reason": "take_profit", "pnl": 15.0},
        {"ticket": "102", "symbol": "EURUSD", "side": "buy", "lots": 0.05, "open_price": 1.1600, "close_price": 1.1585, "close_reason": "stop_loss", "pnl": -7.5},
        {"ticket": "103", "symbol": "USOIL", "side": "buy", "lots": 0.01, "open_price": 90.5, "close_price": 91.5, "close_reason": "take_profit", "pnl": 10.0},
        {"ticket": "104", "symbol": "BTCUSD", "side": "buy", "lots": 0.01, "open_price": 79000.0, "close_price": 78700.0, "close_reason": "stop_loss", "pnl": -3.0},
    ]

    metrics = parser.compute_performance_metrics(sample_trades)
    assert metrics["total_trades"] == 4
    assert metrics["wins"] == 2
    assert metrics["losses"] == 2
    assert metrics["win_rate_pct"] == 50.0
    assert metrics["gross_profit"] == 25.0
    assert metrics["gross_loss"] == 10.5
    assert metrics["net_pnl"] == 14.5
    assert metrics["profit_factor"] == round(25.0 / 10.5, 2)
    assert "XAUUSD" in metrics["asset_breakdown"]
    assert metrics["asset_breakdown"]["XAUUSD"]["wins"] == 1


def test_quantedge_tracker_and_deliberations(tmp_path: Path):
    """Verify recording orders, capturing 5-agent debate, and outcome correlation using QuantEdgeTracker."""
    storage = tmp_path / "test_quantedge.json"
    tracker = QuantEdgeTracker(storage_path=storage)

    # 1. Record an order
    order = tracker.record_order(
        ticket="888001",
        asset="BTCUSD",
        side="buy",
        volume=0.02,
        price=79500.0,
        stop_loss=78500.0,
        take_profit=82000.0,
        strategy_name="Adaptive_BTC_Expansion",
        strategy_archetype="Volatility Breakout",
        consensus={"score": 92.0, "agreed_count": 5, "total_agents": 5},
        rationale="Order Decision Agent approved BUY BTCUSD at 79500.00.",
    )
    assert order["ticket"] == "888001"
    assert "regime_pm" in order["deliberations"]
    assert "claude_haiku" in order["deliberations"]
    assert "risk_guard" in order["deliberations"]

    # 2. Sync with MT4 closed trade
    closed = [
        {
            "ticket": "888001",
            "symbol": "BTCUSD",
            "side": "buy",
            "lots": 0.02,
            "open_price": 79500.0,
            "close_price": 81500.0,
            "close_reason": "take_profit",
            "pnl": 40.0,
        }
    ]
    synced = tracker.sync_with_mt4_history(closed)
    matched = next((s for s in synced if s["ticket"] == "888001"), None)
    assert matched is not None
    assert matched["status"] == "CLOSED"
    assert matched["pnl"] == 40.0
    assert "WIN" in matched["post_mortem"]

    # Verify IntentGuardTracker backward compatibility alias
    assert IntentGuardTracker is QuantEdgeTracker


def test_midnight_execution_auditor(tmp_path: Path):
    """Verify the 00:00 UTC auditor evaluates past trades, scores agents, and writes daily post-mortem."""
    reports_dir = tmp_path / "reports"
    auditor = MidnightExecutionAuditor(reports_dir=reports_dir)

    report = auditor.run_daily_audit(force_date="2026-09-08")
    assert report["audit_date"] == "2026-09-08"
    assert "summary" in report
    assert "agent_accuracy" in report
    assert "regime_pm" in report["agent_accuracy"]
    assert "risk_guard" in report["agent_accuracy"]
    assert len(report["institutional_takeaways"]) >= 3
    assert (reports_dir / "daily_learning_2026-09-08.json").exists()


@pytest.mark.asyncio
async def test_quantedge_and_midnight_api_routes():
    """Verify live FastAPI endpoints for QuantEdge executions and Midnight Learner."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # QuantEdge primary executions endpoint
        res_qe = await client.get("/api/v1/analytics/quantedge/executions")
        assert res_qe.status_code == 200
        data_qe = res_qe.json()
        assert "total_executions" in data_qe
        assert "executions" in data_qe

        # Backward compatibility IntentGuard executions endpoint
        res_ig = await client.get("/api/v1/analytics/intentguard/executions")
        assert res_ig.status_code == 200
        data_ig = res_ig.json()
        assert data_ig["total_executions"] == data_qe["total_executions"]

        # Midnight learner latest
        res_mn = await client.get("/api/v1/analytics/midnight-learner/latest")
        assert res_mn.status_code == 200
        data_mn = res_mn.json()
        assert "audit_date" in data_mn
        assert "agent_accuracy" in data_mn

        # Midnight learner on-demand trigger
        res_run = await client.post("/api/v1/analytics/midnight-learner/run")
        assert res_run.status_code == 200
        data_run = res_run.json()
        assert "institutional_takeaways" in data_run
