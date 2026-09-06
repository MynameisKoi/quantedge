"""Unit tests for Robbins Cup Low-Movement Chop Suppression and Big Movement Forced Participation."""

from __future__ import annotations

import pandas as pd
import pytest

from strategies.adaptive.btcusd_strategy import BtcUsdAdaptiveStrategy
from strategies.strategy_allocator import StrategyAllocator


def test_low_movement_chop_suppression():
    """Verify that when market is in dead equilibrium chop (like 5 Sep), trade entry is strictly suppressed."""
    allocator = StrategyAllocator(min_score_threshold=65.0)

    # Simulated 5 Sep dead chop: ADX 14.5, tight candle range, price hovering right at equilibrium POC
    mt4_data = {
        "price": 79708.0,
        "ema9": 79715.0,
        "ema21": 79710.0,
        "ema50": 79720.0,
        "atr": 120.0,
        "adx": 14.5,  # Low ADX < 18
        "donchian_high": 79900.0,
        "donchian_low": 79516.0,
        "candle_range": 40.0,  # Compressed candle (< 0.50x ATR)
        "candle_body": 15.0,
        "rsi": 49.0,
    }

    res = allocator.evaluate_live_allocation(
        asset="BTCUSD",
        mt4_data=mt4_data,
        regime="risk-on",
    )

    # Must be suppressed
    assert res["status"] == "CHOP_EQUILIBRIUM_SUPPRESSED"
    assert res["side"] == "none"
    assert res["score"] <= 45.0
    assert res["checklist"]["adx_trend"] is False
    assert res["checklist"]["setup_trigger"] is False
    assert res["checklist"]["score_met"] is False
    assert "Robbins Cup Location Filter" in res["reasoning"]


def test_4_sep_big_movement_forced_liquidation_breakdown():
    """Verify that explosive breakdown (like 4 Sep 09:45-12:45) triggers high-conviction SHORT with +4.0R target."""
    allocator = StrategyAllocator(min_score_threshold=65.0)

    # Simulated 4 Sep 09:45: Price collapses from 81,400 to 79,800, breaking 20-bar Donchian Low (80,800)
    mt4_data = {
        "price": 79750.0,
        "ema9": 80200.0,
        "ema21": 80600.0,
        "ema50": 80900.0,
        "atr": 450.0,
        "adx": 28.5,  # High trending ADX
        "donchian_high": 81450.0,
        "donchian_low": 80800.0,  # Price broke far below Donchian Low
        "candle_range": 1200.0,  # Massive expansion candle (> 2.5x ATR)
        "candle_body": 950.0,
        "rsi": 31.0,
    }

    # Macro aligned or neutral
    macro_info = {
        "stance": "BEARISH",
        "bias": -0.45,
        "summary": "Institutional risk-off de-risking and liquidation cascade observed.",
    }

    res = allocator.evaluate_live_allocation(
        asset="BTCUSD",
        mt4_data=mt4_data,
        macro_info=macro_info,
        regime="risk-off",
    )

    assert res["status"] == "SIGNAL_TRIGGERED"
    assert res["side"] == "short"
    assert res["score"] >= 65.0
    assert res["reason"] == "forced_liquidation_breakdown_short"
    assert res["partial_r"] >= 3.5  # Asymmetric multi-R runner target!
    assert res["potential_order"] is not None
    assert res["potential_order"]["triggered"] is True
    assert "SELL (SHORT)" in res["potential_order"]["action"]
    assert "Robbins Cup Forced Participation" in res["reasoning"]


def test_forced_liquidation_breakout_long():
    """Verify that explosive breakout above Donchian High triggers high-conviction LONG with +4.0R target."""
    allocator = StrategyAllocator(min_score_threshold=65.0)

    # Explosive bullish breakout
    mt4_data = {
        "price": 82100.0,
        "ema9": 81600.0,
        "ema21": 81200.0,
        "ema50": 80900.0,
        "atr": 400.0,
        "adx": 27.0,
        "donchian_high": 81800.0,  # Price broke above Donchian High
        "donchian_low": 80200.0,
        "candle_range": 750.0,  # Expanding candle
        "candle_body": 550.0,
        "rsi": 68.0,
    }

    macro_info = {
        "stance": "BULLISH",
        "bias": 0.55,
        "summary": "Massive institutional spot ETF inflows announced.",
    }

    res = allocator.evaluate_live_allocation(
        asset="BTCUSD",
        mt4_data=mt4_data,
        macro_info=macro_info,
        regime="risk-on",
    )

    assert res["status"] == "SIGNAL_TRIGGERED"
    assert res["side"] == "long"
    assert res["score"] >= 65.0
    assert res["reason"] == "forced_liquidation_breakout_long"
    assert res["partial_r"] >= 3.5
    assert res["potential_order"] is not None
    assert res["potential_order"]["triggered"] is True
    assert "BUY (LONG)" in res["potential_order"]["action"]


def test_btcusd_strategy_4_sep_simulation():
    """Verify BtcUsdAdaptiveStrategy standalone model catches 4 Sep breakdown with 4.0R target."""
    strategy = BtcUsdAdaptiveStrategy()

    # Create synthetic M15 bars depicting 4 Sep crash
    dates = pd.date_range("2026-09-04 06:00", periods=30, freq="15min", tz="UTC")
    df = pd.DataFrame(index=dates)
    # Steady at 81,400 then sudden dump to 79,800
    prices = [81400.0 - (i * 10.0) for i in range(25)]
    prices += [81000.0, 80400.0, 79800.0, 79400.0, 78800.0]
    df["close"] = prices
    df["open"] = [p + 50.0 for p in prices]
    df["high"] = [p + 120.0 for p in prices]
    df["low"] = [p - 150.0 for p in prices]

    res = strategy.evaluate(df, timestamp=dates[-1])

    assert res["side"] == "short"
    assert res["score"] >= 80.0
    assert res["partial_r"] == 4.0
    assert res["reason"] == "forced_liquidation_breakdown_short"
