"""Unit tests for StrategyAllocator and reasoning-driven strategy selection."""

import pytest

from risk.manager import RiskManager
from strategies.strategy_allocator import StrategyAllocator


def test_strategy_allocator_gold_trend():
    allocator = StrategyAllocator()
    mt4_data = {
        "price": 4450.0,
        "ema9": 4440.0,
        "ema21": 4445.0,
        "ema50": 4430.0,
        "atr": 10.0,
        "adx": 22.0,
    }
    macro_info = {
        "stance": "BULLISH",
        "bias": 0.5,
        "summary": "Central bank gold diversification supports safe haven bids.",
    }
    res = allocator.evaluate_live_allocation(
        asset="XAUUSD",
        mt4_data=mt4_data,
        macro_info=macro_info,
        regime="stagflation",
    )
    assert res["strategy_name"] in ("Institutional Trend & Chandelier Runner", "Momentum Impulse Runner")
    assert res["sl_mult"] >= 1.5
    assert res["be_r"] >= 1.0
    assert res["partial_r"] >= 2.0
    assert "Central bank gold" in res["reasoning"]


def test_strategy_allocator_oil_breakout():
    allocator = StrategyAllocator()
    mt4_data = {
        "price": 89.50,
        "donchian_high": 89.20,
        "donchian_low": 87.00,
        "ema20": 88.80,
        "ema50": 88.20,
        "atr": 0.45,
        "adx": 25.0,
    }
    macro_info = {
        "stance": "BULLISH",
        "bias": 0.33,
        "summary": "OPEC+ supply cuts maintain energy floor.",
    }
    res = allocator.evaluate_live_allocation(
        asset="USOIL",
        mt4_data=mt4_data,
        macro_info=macro_info,
        regime="risk-on",
    )
    assert res["strategy_name"] == "NY Volatility Breakout"
    assert res["sl_mult"] >= 2.0
    assert res["be_r"] >= 1.0
    assert res["partial_r"] >= 2.0
    assert res["side"] == "long"
    assert res["score"] >= 60.0
    assert res["status"] == "SIGNAL_TRIGGERED"
    assert res["potential_order"] is not None
    assert res["potential_order"]["action"] == "BUY (LONG)"


def test_strategy_allocator_eurusd_mean_revert():
    allocator = StrategyAllocator()
    mt4_data = {
        "price": 1.0820,
        "bb_upper": 1.0900,
        "bb_middle": 1.0860,
        "bb_lower": 1.0825,
        "rsi": 32.0,
        "atr": 0.0008,
        "adx": 19.0,
    }
    macro_info = {
        "stance": "BULLISH",
        "bias": 0.6,
        "summary": "Fed-ECB yield differential steady.",
    }
    res = allocator.evaluate_live_allocation(
        asset="EURUSD",
        mt4_data=mt4_data,
        macro_info=macro_info,
        regime="deflation",
    )
    assert res["strategy_name"] == "Liquidity Sweep Mean Revert"
    assert res["sl_mult"] >= 1.2
    assert res["be_r"] >= 0.8
    assert res["partial_r"] >= 1.5
    assert res["side"] == "long"
    assert res["score"] >= 60.0
    assert res["status"] == "SIGNAL_TRIGGERED"


def test_risk_manager_fine_tunes_order_with_sl_and_tp():
    risk = RiskManager()
    decision = risk.evaluate(
        asset="XAUUSD",
        side="long",
        score=75.0,
        atr=10.0,
        price=4450.0,
        sl_mult=2.5,
        be_r=1.0,
        partial_r=2.0,
    )
    assert decision["approved"] is True
    assert decision["volume"] >= 0.01
    # SL distance = max(2.5 * 10 = 25, 20 floor) = 25 -> SL = 4450 - 25 = 4425
    assert decision["stop_loss"] == 4425.0
    # TP distance = 2.0 * 25 = 50 -> TP = 4450 + 50 = 4500
    assert decision["take_profit"] == 4500.0
    # BE trigger = 4450 + 25 = 4475
    assert decision["breakeven_trigger"] == 4475.0


def test_multi_agent_consensus_order_execution():
    """Verify that when all agents discuss and agree, signal threshold gauge is met and order is ready."""
    allocator = StrategyAllocator(min_score_threshold=65.0)
    mt4_data = {
        "price": 88.50,
        "donchian_high": 88.00,
        "donchian_low": 86.00,
        "ema20": 87.80,
        "ema50": 87.00,
        "atr": 0.40,
        "adx": 24.0,
    }
    macro_info = {
        "stance": "BULLISH",
        "bias": 0.45,
        "summary": "OPEC+ quota compliance and tight global inventories bolster crude.",
        "multi_agent_perspectives": {
            "monetary_policy": "Central bank easing supports industrial activity.",
            "growth_liquidity": "Global commodity demand expansion.",
        },
    }
    res = allocator.evaluate_live_allocation(
        asset="USOIL",
        mt4_data=mt4_data,
        macro_info=macro_info,
        regime="risk-on",
    )

    # All 5 agents must have agreed
    consensus = res["agent_consensus"]
    assert consensus["all_agreed"] is True
    assert consensus["agreed_count"] == 5
    assert res["checklist"]["agent_consensus"] is True
    assert res["checklist"]["score_met"] is True
    assert res["score"] >= 65.0
    assert res["progress_pct"] == 100.0
    assert res["status"] == "SIGNAL_TRIGGERED"
    assert res["potential_order"] is not None
    assert res["potential_order"]["triggered"] is True
    assert res["potential_order"]["type"] == "EXECUTION_READY"
    assert "BUY (LONG)" in res["potential_order"]["action"]


def test_multi_agent_dissent_prevents_execution():
    """Verify that when an agent dissents (macro opposes technicals), score stays below threshold and no order triggers."""
    allocator = StrategyAllocator(min_score_threshold=65.0)
    mt4_data = {
        "price": 88.50,
        "donchian_high": 88.00,
        "donchian_low": 86.00,
        "ema20": 87.80,
        "ema50": 87.00,
        "atr": 0.40,
        "adx": 24.0,
    }
    # Macro specialist stance opposes the breakout!
    macro_info = {
        "stance": "BEARISH",
        "bias": -0.65,
        "summary": "Severe demand destruction and massive inventory build announced.",
    }
    res = allocator.evaluate_live_allocation(
        asset="USOIL",
        mt4_data=mt4_data,
        macro_info=macro_info,
        regime="risk-on",
    )

    consensus = res["agent_consensus"]
    assert consensus["all_agreed"] is False
    assert res["checklist"]["agent_consensus"] is False
    assert res["checklist"]["score_met"] is False
    # Threshold gauge not met
    assert res["score"] < 65.0
    assert res["status"] != "SIGNAL_TRIGGERED"
    if res["potential_order"]:
        assert res["potential_order"]["triggered"] is False


def test_strategy_allocator_btcusd_dynamic_allocation():
    """Verify that BTCUSD is dynamically allocated and evaluated."""
    allocator = StrategyAllocator()
    res = allocator.evaluate_live_allocation(
        asset="BTCUSD",
        mt4_data={
            "price": 79400.0,
            "ema9": 79500.0,
            "ema21": 79650.0,
            "atr": 260.0,
            "rsi": 42.0,
            "adx": 28.0,
        },
        macro_info={
            "stance": "BULLISH",
            "bias": 0.25,
            "summary": "Institutional crypto momentum and spot ETF inflows.",
        },
        regime="risk-on",
    )
    assert res["asset"] == "BTCUSD"
    assert "strategy_name" in res
    assert "rl_intel" in res
    assert "math_rules" in res
    assert "educational_guide" in res
    assert res["rl_intel"]["selected_archetype"] in ("momentum_impulse", "value_pullback", "volatility_breakout", "mean_revert")


def test_strategy_details_transparency_structure():
    """Verify that strategy allocation exposes educational guides and math formulas for user transparency."""
    allocator = StrategyAllocator()
    res = allocator.evaluate_live_allocation("XAUUSD")
    assert "math_rules" in res
    assert "educational_guide" in res
    assert "entry_rule" in res["math_rules"]
    assert "concept" in res["educational_guide"]
    assert "why_chosen_now" in res["educational_guide"]
    assert len(res["rl_intel"]["candidates"]) == 4


