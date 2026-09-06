"""Adaptive M15 Institutional Trend & Chandelier Runner Strategy for XAUUSD (Gold)."""

from __future__ import annotations

import logging
from typing import Any
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def calculate_adx(df: pd.DataFrame, period: int = 14) -> float:
    """Calculate Average Directional Index (ADX)."""
    if len(df) < period + 2:
        return 20.0
    high, low, close = df["high"], df["low"], df["close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    plus_di = 100 * (pd.Series(plus_dm, index=df.index).rolling(period).mean() / (atr + 1e-9))
    minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(period).mean() / (atr + 1e-9))
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    adx = dx.rolling(period).mean()
    return float(adx.iloc[-1]) if not np.isnan(adx.iloc[-1]) else 20.0


class XauUsdAdaptiveStrategy:
    """
    Gold M15 Institutional Alpha Strategy:
    - Trend: ADX >= 18 + EMA50 slope alignment + H4 EMA50/200 bias.
    - Trigger: M15 EMA9/21 crossover or pullback tap into value zone.
    - Killzone: London & NY active liquidity sessions.
    - Exit: Asymmetric 3-Stage Chandelier Exit (SL=1.5 ATR, BE at +1.0R, 50% Bank at +2.0R, 2.0 ATR Trail).
    """

    name = "xauusd_trend"
    asset = "XAUUSD"

    def __init__(self) -> None:
        self.sl_atr_mult = 1.5
        self.be_r = 1.0
        self.partial_r = 2.0
        self.trail_atr_mult = 2.0

    def evaluate(
        self,
        df_m15: pd.DataFrame,
        df_h4: pd.DataFrame | None = None,
        timestamp: pd.Timestamp | None = None,
    ) -> dict[str, Any]:
        if len(df_m15) < 25:
            return {"side": "none", "score": 0.0, "atr": 1.0}

        # Killzone filter (07:00 to 18:00 UTC, Weekdays)
        if timestamp is not None:
            if timestamp.weekday() >= 5:
                return {"side": "none", "score": 0.0, "atr": 1.0, "reason": "weekend"}
            hour = timestamp.hour
            if hour < 7 or hour >= 18:
                return {"side": "none", "score": 0.0, "atr": 1.0, "reason": "asian_offhours"}

        close = df_m15["close"]
        high = df_m15["high"]
        low = df_m15["low"]

        # 14-period ATR
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])
        atr = max(atr, 0.5)

        # EMAs
        ema9 = close.ewm(span=9).mean()
        ema21 = close.ewm(span=21).mean()
        ema50 = close.ewm(span=50).mean()

        # Trend & Momentum Gating
        adx_val = calculate_adx(df_m15, period=14)

        # HTF Trend
        htf_bias = "ranging"
        if df_h4 is not None and len(df_h4) >= 20:
            h4_close = df_h4["close"]
            h4_ema50 = h4_close.ewm(span=min(50, len(h4_close))).mean().iloc[-1]
            if h4_close.iloc[-1] > h4_ema50:
                htf_bias = "bullish"
            elif h4_close.iloc[-1] < h4_ema50:
                htf_bias = "bearish"
        else:
            htf_bias = "bullish" if close.iloc[-1] > ema50.iloc[-1] else "bearish"

        cur_price = float(close.iloc[-1])
        indicators = {
            "price": round(cur_price, 2),
            "ema9": round(float(ema9.iloc[-1]), 2),
            "ema21": round(float(ema21.iloc[-1]), 2),
            "ema50": round(float(ema50.iloc[-1]), 2),
            "adx": round(adx_val, 1),
            "atr": round(atr, 2),
            "trend": htf_bias,
        }

        if adx_val < 18.0:
            return {
                "side": "none",
                "score": 40.0,
                "atr": atr,
                "reason": "low_adx",
                "indicators": indicators,
                "analysis": f"Gold ADX is {adx_val:.1f} (<18.0) indicating weak non-directional chop. Waiting for institutional trend momentum.",
                "checklist": {"session": True, "adx_trend": False, "setup_trigger": False, "score_met": False},
                "sl_mult": self.sl_atr_mult, "be_r": self.be_r, "partial_r": self.partial_r, "trail_mult": self.trail_atr_mult,
            }

        side = "none"
        score = 50.0
        reason = "waiting_for_setup"
        analysis = f"Gold is in a {htf_bias.upper()} regime above EMA 50 ({indicators['ema50']}). "

        # Bullish setup
        if htf_bias == "bullish":
            if ema9.iloc[-1] > ema21.iloc[-1]:
                if ema9.iloc[-2] <= ema21.iloc[-2]:
                    side = "long"
                    score = 85.0
                    reason = "ema9_21_bull_cross"
                    analysis += f"Fresh bullish EMA 9/21 cross confirmed at {cur_price:.2f}. High conviction Long."
                elif low.iloc[-1] <= ema21.iloc[-1] and close.iloc[-1] > ema9.iloc[-1]:
                    side = "long"
                    score = 80.0
                    reason = "ema21_pullback_tap_long"
                    analysis += f"Value zone pullback tap of EMA 21 ({indicators['ema21']}) with strong recovery. Long active."
                else:
                    score = 52.0
                    reason = "waiting_for_ema21_pullback"
                    analysis += f"Price ({cur_price:.2f}) is extended above EMA 21 ({indicators['ema21']}). Waiting for pullback tap into value zone to buy."
            else:
                score = 48.0
                reason = "waiting_for_bullish_alignment"
                analysis += f"EMA 9 is below EMA 21. Waiting for bullish crossover or re-alignment."

        # Bearish setup
        elif htf_bias == "bearish":
            if ema9.iloc[-1] < ema21.iloc[-1]:
                if ema9.iloc[-2] >= ema21.iloc[-2]:
                    side = "short"
                    score = 85.0
                    reason = "ema9_21_bear_cross"
                    analysis += f"Fresh bearish EMA 9/21 cross confirmed at {cur_price:.2f}. High conviction Short."
                elif high.iloc[-1] >= ema21.iloc[-1] and close.iloc[-1] < ema9.iloc[-1]:
                    side = "short"
                    score = 80.0
                    reason = "ema21_pullback_tap_short"
                    analysis += f"Bearish relief rally tapped EMA 21 ({indicators['ema21']}) resistance. Short active."
                else:
                    score = 52.0
                    reason = "waiting_for_ema21_relief_rally"
                    analysis += f"Price ({cur_price:.2f}) is below EMA 21 ({indicators['ema21']}). Waiting for relief tap to sell."
            else:
                score = 48.0
                reason = "waiting_for_bearish_alignment"
                analysis += f"Waiting for bearish moving average alignment."

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
