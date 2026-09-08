"""Adaptive M15 Energy Volatility Breakout & NY Session Strategy for USOIL (Crude Oil)."""

from __future__ import annotations

import logging
from typing import Any
import numpy as np
import pandas as pd

from strategies.adaptive.xauusd_strategy import calculate_adx

logger = logging.getLogger(__name__)


class UsOilAdaptiveStrategy:
    """
    USOIL M15 NY Session Volatility Breakout Strategy:
    - Designed specifically for the high-volatility, wide-wick nature of Crude Oil.
    - Operates strictly in the high-volume energy window: 12:00 - 18:00 UTC (London/NY Overlap & NY Open).
    - Uses 20-period Donchian breakout confirmation + ADX >= 20 trend filter.
    - Expanded stop buffer (SL = 2.0 ATR) to prevent premature wick stop-outs.
    - Exits: BE at +1.2R, 50% bank at +2.0R, and dynamic 2.5 ATR trailing runner.
    """

    name = "usoil_vol_breakout"
    asset = "USOIL"

    def __init__(self) -> None:
        self.sl_atr_mult = 2.5
        self.be_r = 1.5
        self.partial_r = 2.5
        self.trail_atr_mult = 2.8

    def evaluate(
        self,
        df_m15: pd.DataFrame,
        df_h4: pd.DataFrame | None = None,
        timestamp: pd.Timestamp | None = None,
    ) -> dict[str, Any]:
        if len(df_m15) < 25:
            return {"side": "none", "score": 0.0, "atr": 0.50}

        # Session filter: High-volume NY & London overlap energy window (12:00 to 18:00 UTC, Weekdays)
        if timestamp is not None:
            if timestamp.weekday() >= 5:
                return {"side": "none", "score": 0.0, "atr": 0.50, "reason": "weekend"}
            hour = timestamp.hour
            if hour < 12 or hour >= 18:
                return {"side": "none", "score": 0.0, "atr": 0.50, "reason": "non_energy_session"}

        close = df_m15["close"]
        high = df_m15["high"]
        low = df_m15["low"]

        # 14-period ATR
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])
        atr = max(atr, 0.20)

        # ADX trend strength filter
        adx_val = calculate_adx(df_m15, period=14)

        # 20-period Donchian Channels (using prior bars to prevent lookahead)
        donchian_high = high.shift(1).rolling(20).max()
        donchian_low = low.shift(1).rolling(20).min()

        ema20 = close.ewm(span=20).mean()
        ema50 = close.ewm(span=50).mean()

        cur_price = float(close.iloc[-1])
        dh = float(donchian_high.iloc[-1])
        dl = float(donchian_low.iloc[-1])
        e20 = float(ema20.iloc[-1])
        e50 = float(ema50.iloc[-1])
        oil_trend = "bullish" if e20 > e50 else "bearish"

        indicators = {
            "price": round(cur_price, 2),
            "donchian_high": round(dh, 2),
            "donchian_low": round(dl, 2),
            "ema20": round(e20, 2),
            "ema50": round(e50, 2),
            "adx": round(adx_val, 1),
            "atr": round(atr, 2),
            "trend": oil_trend,
        }

        # ADX trend strength filter
        if adx_val < 18.0:
            return {
                "side": "none",
                "score": 40.0,
                "atr": atr,
                "reason": "oil_choppy_adx",
                "indicators": indicators,
                "analysis": f"WTI Crude ADX is {adx_val:.1f} (<18.0) indicating low-volatility chop. Waiting for energy session volume expansion.",
                "checklist": {"session": True, "adx_trend": False, "setup_trigger": False, "score_met": False},
                "sl_mult": self.sl_atr_mult, "be_r": self.be_r, "partial_r": self.partial_r, "trail_mult": self.trail_atr_mult,
            }

        last_close = float(close.iloc[-1])
        last_high = float(high.iloc[-1])
        last_low = float(low.iloc[-1])

        side = "none"
        score = 50.0
        reason = "waiting_for_breakout"
        analysis = f"WTI Crude is in a {oil_trend.upper()} trend. "

        # Bullish Breakout Setup: Price breaks above 20-bar high with EMA20 > EMA50
        if last_close > dh and ema20.iloc[-1] > ema50.iloc[-1]:
            side = "long"
            score = 85.0
            reason = "usoil_donchian_bull_breakout"
            analysis += f"Bullish breakout above 20-bar Donchian high ({dh:.2f}). High momentum Long."

        # Bearish Breakdown Setup: Price breaks below 20-bar low with EMA20 < EMA50
        elif last_close < dl and ema20.iloc[-1] < ema50.iloc[-1]:
            side = "short"
            score = 85.0
            reason = "usoil_donchian_bear_breakdown"
            analysis += f"Bearish breakdown below 20-bar Donchian low ({dl:.2f}). High momentum Short."

        # Pullback into EMA20 during strong trend
        elif ema20.iloc[-1] > ema50.iloc[-1] and last_low <= ema20.iloc[-1] and last_close > ema20.iloc[-1]:
            side = "long"
            score = 75.0
            reason = "usoil_ema20_pullback_long"
            analysis += f"Energy trend pullback tapped EMA 20 ({e20:.2f}) support. Long active."

        elif ema20.iloc[-1] < ema50.iloc[-1] and last_high >= ema20.iloc[-1] and last_close < ema20.iloc[-1]:
            side = "short"
            score = 75.0
            reason = "usoil_ema20_pullback_short"
            analysis += f"Energy trend pullback tapped EMA 20 ({e20:.2f}) resistance. Short active."

        else:
            score = 50.0
            reason = "inside_donchian_range"
            analysis += f"Price ({cur_price:.2f}) is inside Donchian range [{dl:.2f} - {dh:.2f}]. Waiting for breakout or EMA20 tap."

        checklist = {
            "session": True,
            "adx_trend": adx_val >= 18.0,
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
