"""Adaptive M15 Forex Liquidity Sweep & Mean-Reversion Strategy for EURUSD."""

from __future__ import annotations

import logging
from typing import Any
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def calculate_rsi(close: pd.Series, period: int = 14) -> float:
    """Calculate Relative Strength Index (RSI)."""
    if len(close) < period + 1:
        return 50.0
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    val = float(rsi.iloc[-1])
    return val if not np.isnan(val) else 50.0


class EurUsdAdaptiveStrategy:
    """
    EURUSD M15 Liquidity Sweep & Mean Reversion Strategy:
    - Designed specifically for the mean-reverting microstructure of EURUSD Forex.
    - Uses 20-period Bollinger Bands (2.0 std dev) and 14-period RSI extremes.
    - Fades false breakouts and liquidity sweeps outside the bands during London/NY sessions.
    - Target: High win-rate quick rotation back to EMA20 / opposite band (SL=1.2 ATR, BE=+0.8R, TP=+1.5R).
    """

    name = "eurusd_mean_revert"
    asset = "EURUSD"

    def __init__(self) -> None:
        self.sl_atr_mult = 1.2
        self.be_r = 0.8
        self.partial_r = 1.5
        self.trail_atr_mult = 1.5

    def evaluate(
        self,
        df_m15: pd.DataFrame,
        df_h4: pd.DataFrame | None = None,
        timestamp: pd.Timestamp | None = None,
    ) -> dict[str, Any]:
        if len(df_m15) < 25:
            return {"side": "none", "score": 0.0, "atr": 0.0015}

        # Session filter: London & NY active liquidity (07:00 to 17:00 UTC, Weekdays)
        if timestamp is not None:
            if timestamp.weekday() >= 5:
                return {"side": "none", "score": 0.0, "atr": 0.0015, "reason": "weekend"}
            hour = timestamp.hour
            if hour < 7 or hour >= 17:
                return {"side": "none", "score": 0.0, "atr": 0.0015, "reason": "off_hours"}

        close = df_m15["close"]
        high = df_m15["high"]
        low = df_m15["low"]

        # 14-period ATR
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])
        atr = max(atr, 0.0005)

        # 20-period Bollinger Bands
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper_bb = sma20 + (2.0 * std20)
        lower_bb = sma20 - (2.0 * std20)

        rsi_val = calculate_rsi(close, period=14)

        last_open = float(df_m15["open"].iloc[-1])
        last_close = float(close.iloc[-1])
        last_high = float(high.iloc[-1])
        last_low = float(low.iloc[-1])
        last_lower = float(lower_bb.iloc[-1])
        last_upper = float(upper_bb.iloc[-1])
        mid_bb = float(sma20.iloc[-1])

        bar_range = max(last_high - last_low, 1e-6)
        lower_wick = min(last_close, last_open) - last_low
        upper_wick = last_high - max(last_close, last_open)

        indicators = {
            "price": round(last_close, 5),
            "bb_upper": round(last_upper, 5),
            "bb_middle": round(mid_bb, 5),
            "bb_lower": round(last_lower, 5),
            "rsi": round(rsi_val, 1),
            "atr": round(atr, 5),
            "trend": "neutral_mean_reverting",
        }

        side = "none"
        score = 50.0
        reason = "inside_bands_neutral"
        analysis = f"EURUSD RSI is {rsi_val:.1f} (Neutral 42-58). Price ({last_close:.5f}) is inside Bollinger Bands [{last_lower:.5f} - {last_upper:.5f}]. "

        # Long Setup: Liquidity sweep below lower band with bullish rejection wick
        if last_low <= last_lower and (lower_wick / bar_range) >= 0.40 and rsi_val <= 42.0:
            if last_close > last_low + (0.30 * bar_range):
                side = "long"
                score = 80.0
                reason = "eurusd_oversold_sweep_long"
                analysis += f"Bullish liquidity sweep below lower band ({last_lower:.5f}) with {(lower_wick/bar_range)*100:.0f}% rejection wick. Long active."

        # Short Setup: Liquidity sweep above upper band with bearish rejection wick
        elif last_high >= last_upper and (upper_wick / bar_range) >= 0.40 and rsi_val >= 58.0:
            if last_close < last_high - (0.30 * bar_range):
                side = "short"
                score = 80.0
                reason = "eurusd_overbought_sweep_short"
                analysis += f"Bearish liquidity sweep above upper band ({last_upper:.5f}) with {(upper_wick/bar_range)*100:.0f}% rejection wick. Short active."

        else:
            if last_close > mid_bb:
                analysis += "Trending above middle band. Waiting for upper band sweep & rejection wick to fade."
            else:
                analysis += "Trending below middle band. Waiting for lower band sweep & rejection wick to buy."

        checklist = {
            "session": True,
            "rsi_divergence": rsi_val <= 42.0 or rsi_val >= 58.0,
            "setup_trigger": side != "none",
            "score_met": score >= 60.0,
        }

        return {
            "side": side,
            "score": score,
            "atr": atr,
            "sl_mult": self.sl_atr_mult,
            "be_r": self.be_r,
            "partial_r": self.partial_r,
            "trail_mult": self.trail_atr_mult,
            "reason": reason,
            "indicators": indicators,
            "analysis": analysis,
            "checklist": checklist,
        }
