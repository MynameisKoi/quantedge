"""Unit tests for Dedicated BTCUSD Adaptive Strategy."""

from __future__ import annotations

from datetime import UTC, datetime
import pandas as pd
import pytest

from strategies.adaptive.btcusd_strategy import BtcUsdAdaptiveStrategy
from strategies.adaptive.router import adaptive_router
from strategies.strategy_allocator import strategy_allocator


def _generate_synthetic_m15_btc(trend: str = "bullish", n_bars: int = 60) -> pd.DataFrame:
    """Generate synthetic BTCUSD M15 OHLCV bars for unit testing."""
    times = pd.date_range("2026-09-01 00:00:00", periods=n_bars, freq="15min", tz="UTC")
    base_price = 79000.0
    records = []

    for i in range(n_bars):
        if trend == "bullish":
            price = base_price + (i * 30.0)
        elif trend == "bearish":
            price = base_price - (i * 30.0)
        else:  # sideways chop
            price = base_price + (10.0 if i % 2 == 0 else -10.0)

        high = price + 40.0
        low = price - 40.0
        open_px = price - 10.0
        close_px = price + 10.0
        volume = 150.0 + (i * 2.0)
        records.append({
            "open": open_px,
            "high": high,
            "low": low,
            "close": close_px,
            "volume": volume,
        })

    df = pd.DataFrame(records, index=times)
    return df


def test_btcusd_strategy_structure_and_params():
    """Verify BtcUsdAdaptiveStrategy initializes with institutional parameters."""
    strat = BtcUsdAdaptiveStrategy()
    assert strat.name == "btcusd_volatility_expansion"
    assert strat.asset == "BTCUSD"
    assert strat.sl_atr_mult == 2.8
    assert strat.be_r == 1.5
    assert strat.partial_r == 2.5
    assert strat.trail_atr_mult == 3.0


def test_btcusd_strategy_bullish_evaluation():
    """Verify BtcUsdAdaptiveStrategy generates a valid evaluation for trending crypto."""
    strat = BtcUsdAdaptiveStrategy()
    df = _generate_synthetic_m15_btc("bullish", n_bars=60)
    # Weekday 14:00 UTC (US cash hours)
    eval_time = pd.Timestamp("2026-09-02 14:00:00", tz="UTC")

    res = strat.evaluate(df_m15=df, timestamp=eval_time)
    assert "side" in res
    assert "score" in res
    assert "atr" in res
    assert res["atr"] > 0
    assert res["sl_mult"] == 2.8  # Weekday stop
    assert "indicators" in res
    assert "math_rules" in res
    assert "educational_guide" in res
    assert res["strategy_name"] == "Bitcoin Volatility Compression & Momentum Runner"


def test_btcusd_strategy_weekend_stop_cushion():
    """Verify BtcUsdAdaptiveStrategy dynamically expands stop cushion to 3.2 ATR on weekends."""
    strat = BtcUsdAdaptiveStrategy()
    df = _generate_synthetic_m15_btc("bullish", n_bars=60)
    # Saturday 12:00 UTC (Weekend)
    weekend_time = pd.Timestamp("2026-09-05 12:00:00", tz="UTC")

    res = strat.evaluate(df_m15=df, timestamp=weekend_time)
    assert res["sl_mult"] == 3.2  # Expanded weekend stop loss cushion to prevent wick hunting
    assert "Weekend" in res["indicators"]["session"]


def test_adaptive_router_dispatches_btcusd():
    """Verify adaptive_router routes BTCUSD to BtcUsdAdaptiveStrategy."""
    df = _generate_synthetic_m15_btc("bullish", n_bars=60)
    res = adaptive_router.evaluate_asset("BTCUSD", df_m15=df)
    assert res["strategy_name"] == "Bitcoin Volatility Compression & Momentum Runner"


def test_strategy_allocator_btcusd_transparency():
    """Verify StrategyAllocator provides dedicated Bitcoin educational guide and rules."""
    alloc = strategy_allocator.evaluate_live_allocation(
        asset="BTCUSD",
        mt4_data={"price": 79800.0, "ema9": 79850.0, "ema21": 79750.0, "ema50": 79600.0, "atr": 220.0, "adx": 26.0, "rsi": 54.0},
    )
    assert alloc["asset"] == "BTCUSD"
    assert "Bitcoin" in alloc["strategy_name"]
    assert "math_rules" in alloc
    assert "educational_guide" in alloc
    assert "Bitcoin Volatility Compression" in alloc["educational_guide"]["concept"]
    assert alloc["threshold"] > 0
