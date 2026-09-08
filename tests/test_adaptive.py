"""Unit tests for Adaptive Multi-Asset M15 Strategies."""

import numpy as np
import pandas as pd
import pytest

from backtest.engine import run_backtest
from strategies.adaptive.eurusd_strategy import EurUsdAdaptiveStrategy
from strategies.adaptive.router import adaptive_router
from strategies.adaptive.usoil_strategy import UsOilAdaptiveStrategy
from strategies.adaptive.xauusd_strategy import XauUsdAdaptiveStrategy


def _create_sample_m15(n_bars: int = 50, base_price: float = 100.0) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    rets = rng.normal(0, 0.002, n_bars)
    close = base_price * np.cumprod(1 + rets)
    high = close * (1 + rng.uniform(0, 0.001, n_bars))
    low = close * (1 - rng.uniform(0, 0.001, n_bars))
    open_ = np.roll(close, 1)
    open_[0] = base_price
    idx = pd.date_range("2024-01-02 08:00", periods=n_bars, freq="15min")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=idx)


def test_xauusd_adaptive_strategy_structure():
    strat = XauUsdAdaptiveStrategy()
    df = _create_sample_m15(60, 2350.0)
    res = strat.evaluate(df, timestamp=pd.Timestamp("2024-01-02 10:00"))
    assert "side" in res
    assert "score" in res
    assert "atr" in res
    assert res["sl_mult"] == 2.5
    assert res["be_r"] == 1.5


def test_eurusd_adaptive_strategy_structure():
    strat = EurUsdAdaptiveStrategy()
    df = _create_sample_m15(60, 1.0850)
    res = strat.evaluate(df, timestamp=pd.Timestamp("2024-01-02 10:00"))
    assert "side" in res
    assert "score" in res
    assert "atr" in res
    assert res["sl_mult"] >= 2.2
    assert res["be_r"] >= 1.2
    assert res["partial_r"] >= 2.0


def test_usoil_adaptive_strategy_structure():
    strat = UsOilAdaptiveStrategy()
    df = _create_sample_m15(60, 78.50)
    res = strat.evaluate(df, timestamp=pd.Timestamp("2024-01-02 14:00"))
    assert "side" in res
    assert "score" in res
    assert "atr" in res
    assert res["sl_mult"] == 2.5
    assert res["be_r"] == 1.5


def test_adaptive_router_dispatch():
    df_gold = _create_sample_m15(60, 2350.0)
    df_eur = _create_sample_m15(60, 1.0850)
    df_oil = _create_sample_m15(60, 78.50)

    res_gold = adaptive_router.evaluate_asset("XAUUSD", df_gold, timestamp=pd.Timestamp("2024-01-02 10:00"))
    assert res_gold["sl_mult"] == 2.5

    res_eur = adaptive_router.evaluate_asset("EURUSD", df_eur, timestamp=pd.Timestamp("2024-01-02 10:00"))
    assert res_eur["sl_mult"] >= 2.2

    res_oil = adaptive_router.evaluate_asset("USOIL", df_oil, timestamp=pd.Timestamp("2024-01-02 14:00"))
    assert res_oil["sl_mult"] == 2.5


def test_adaptive_backtest_execution():
    res = run_backtest(
        strategy="adaptive_portfolio",
        asset="XAUUSD",
        timeframe="M15",
        enable_rl=False,
    )
    assert res.trades >= 0
    assert isinstance(res.net_pnl, float)
