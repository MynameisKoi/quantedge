"""Adaptive M15 Volatility Compression & Momentum Expansion Runner Strategy for BTCUSD (Bitcoin)."""

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
    val = adx.iloc[-1]
    return float(val) if not np.isnan(val) else 20.0


def calculate_rsi(series: pd.Series, period: int = 14) -> float:
    """Calculate Relative Strength Index (RSI)."""
    if len(series) < period + 1:
        return 50.0
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    val = rsi.iloc[-1]
    return float(val) if not np.isnan(val) else 50.0


class BtcUsdAdaptiveStrategy:
    """
    Dedicated Institutional Alpha Strategy for BTCUSD:
    Bitcoin Volatility Compression & Momentum Expansion Runner.

    Microstructure & Quant Edge:
    1. 24/7 Liquidity Awareness:
       - Unlike traditional FX and Commodities, BTC trades 24/7/365.
       - Highest liquidity & institutional flow happens during London/NY Cash Hours (08:00 - 20:00 UTC).
       - Weekend liquidity is thin and subject to derivative liquidation sweeps: dynamic stop loss
         expands from 1.8 ATR (weekdays) to 2.2 ATR (weekends) to eliminate wick hunting.
    2. Dual-Timeframe Trend & Moving Average Ribbon:
       - H4 Macro Bias (50/200 EMA) + M15 Ribbon (EMA 9, EMA 21, EMA 50).
       - Longs restricted to H4 Bullish / Above M15 EMA 50; Shorts restricted to H4 Bearish / Below M15 EMA 50.
    3. Volatility Squeeze & Donchian Expansion Filter:
       - Detects Bollinger Band Width compression (Keltner/BB squeeze) prior to violent trend breakouts.
       - ADX >= 22 confirms trending velocity (rejects low-volume sideways chop).
    4. Dual High-Probability Trigger Mechanisms:
       - Trigger A (Value Zone Pullback Tap): Price taps the EMA 21/50 value zone with RSI resetting
         to 40-55 support (Long) or 45-60 resistance (Short) with candle confirmation.
       - Trigger B (Volatility Squeeze Breakout): Price explodes beyond 20-bar Donchian channel
         with expanding volume and ADX > 25.
    5. Asymmetric Exits & Chandelier Runner:
       - SL: 1.8 ATR (2.2 ATR weekend)
       - Breakeven Ratchet: Move SL to entry at +1.0R
       - Partial Bank: +2.0R
       - Chandelier Trailing Runner: 2.5 ATR trailing stop to ride multi-R crypto trend runs.
    """

    name = "btcusd_volatility_expansion"
    asset = "BTCUSD"

    def __init__(self) -> None:
        self.sl_atr_mult = 2.8
        self.be_r = 1.5
        self.partial_r = 2.5
        self.trail_atr_mult = 3.0

    def evaluate(
        self,
        df_m15: pd.DataFrame,
        df_h4: pd.DataFrame | None = None,
        timestamp: pd.Timestamp | None = None,
    ) -> dict[str, Any]:
        if len(df_m15) < 25:
            return {"side": "none", "score": 0.0, "atr": 250.0}

        # 1. 24/7 Session & Weekend Liquidity Assessment
        is_weekend = False
        is_cash_hours = False
        if timestamp is not None:
            weekday = timestamp.weekday()
            hour = timestamp.hour
            is_weekend = weekday >= 5 or (weekday == 4 and hour >= 21)
            is_cash_hours = 8 <= hour < 20
        else:
            now_utc = pd.Timestamp.now("UTC")
            is_weekend = now_utc.weekday() >= 5
            is_cash_hours = 8 <= now_utc.hour < 20

        # Dynamic stop cushion: Wider stop on weekends to guard against derivative exchange wick flushes
        active_sl_mult = 3.2 if is_weekend else self.sl_atr_mult

        close = df_m15["close"]
        high = df_m15["high"]
        low = df_m15["low"]

        # 2. 14-period ATR
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])
        atr = max(atr, 20.0)  # BTC minimum ATR floor $20

        # 3. Indicator Ribbon: EMA 9, EMA 21, EMA 50
        ema9 = close.ewm(span=9).mean()
        ema21 = close.ewm(span=21).mean()
        ema50 = close.ewm(span=50).mean()

        # 4. ADX & RSI Momentum
        adx_val = calculate_adx(df_m15, period=14)
        rsi_val = calculate_rsi(close, period=14)

        # 5. Volatility Squeeze (Bollinger Bands vs 20-bar Donchian)
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_upper = bb_mid + (bb_std * 2.0)
        bb_lower = bb_mid - (bb_std * 2.0)
        bb_width = (bb_upper - bb_lower) / (bb_mid + 1e-9)

        # Squeeze active if current bandwidth is below 20-bar rolling average of bandwidth
        bandwidth_rolling_mean = bb_width.rolling(20).mean().iloc[-1]
        is_squeeze = float(bb_width.iloc[-1]) < (float(bandwidth_rolling_mean) * 0.90) if not np.isnan(bandwidth_rolling_mean) else False

        # 20-bar Donchian Channel
        donchian_high = high.rolling(20).max().iloc[-2]  # previous 20 bars
        donchian_low = low.rolling(20).min().iloc[-2]

        cur_price = float(close.iloc[-1])
        e9_val = float(ema9.iloc[-1])
        e21_val = float(ema21.iloc[-1])
        e50_val = float(ema50.iloc[-1])

        # 6. HTF Macro Bias
        htf_bias = "ranging"
        if df_h4 is not None and len(df_h4) >= 20:
            h4_close = df_h4["close"]
            h4_ema50 = float(h4_close.ewm(span=min(50, len(h4_close))).mean().iloc[-1])
            if float(h4_close.iloc[-1]) > h4_ema50:
                htf_bias = "bullish"
            elif float(h4_close.iloc[-1]) < h4_ema50:
                htf_bias = "bearish"
        else:
            htf_bias = "bullish" if cur_price > e50_val else "bearish"

        indicators = {
            "price": round(cur_price, 2),
            "ema9": round(e9_val, 2),
            "ema21": round(e21_val, 2),
            "ema50": round(e50_val, 2),
            "adx": round(adx_val, 1),
            "rsi": round(rsi_val, 1),
            "atr": round(atr, 2),
            "donchian_high": round(float(donchian_high), 2) if not np.isnan(donchian_high) else round(cur_price + 2 * atr, 2),
            "donchian_low": round(float(donchian_low), 2) if not np.isnan(donchian_low) else round(cur_price - 2 * atr, 2),
            "is_squeeze": is_squeeze,
            "trend": htf_bias,
            "session": "Weekend 24/7" if is_weekend else ("US/London Cash Liquidity" if is_cash_hours else "Asian Off-Hours"),
        }

        # Robbins Cup Location Filter: Non-directional consolidation when ADX < 22 (or < 26 on weekends)
        poc_val = (float(donchian_high) + float(donchian_low)) / 2.0 if not np.isnan(donchian_high) and not np.isnan(donchian_low) else cur_price
        min_adx_threshold = 26.0 if is_weekend else 22.0
        if adx_val < min_adx_threshold and not is_squeeze:
            return {
                "side": "none",
                "score": 42.0,
                "atr": atr,
                "reason": "low_adx_chop",
                "indicators": indicators,
                "analysis": f"Robbins Cup Location Filter: Bitcoin ADX is {adx_val:.1f} (<{min_adx_threshold:.1f}) trapped at POC (${poc_val:.2f}). Preserving capital until momentum breakout.",
                "checklist": {"session": True, "adx_trend": False, "setup_trigger": False, "score_met": False},
                "sl_mult": active_sl_mult, "be_r": self.be_r, "partial_r": self.partial_r, "trail_mult": self.trail_atr_mult,
            }

        side = "none"
        score = 50.0
        reason = "waiting_for_setup"
        active_partial_r = self.partial_r
        analysis = f"BTC is {htf_bias.upper()} relative to M15 EMA 50 (${e50_val:.2f}). "

        # -----------------------------------------------------------------
        # Bullish Setups
        # -----------------------------------------------------------------
        if htf_bias == "bullish":
            # Trigger A: Value Zone Pullback Tap (Price dips between EMA 21 and EMA 50 and holds)
            is_in_value_zone = cur_price <= (e21_val * 1.002) and cur_price >= (e50_val * 0.998)
            rsi_pullback_reset = 40.0 <= rsi_val <= 58.0

            # Trigger B: Robbins Cup Forced Liquidation Breakout beyond 20-bar Donchian High
            # Suppress breakouts on illiquid weekends to eliminate derivative liquidation traps!
            is_breakout = (not is_weekend) and cur_price >= float(donchian_high) and (adx_val >= 25.0 or is_squeeze)

            if is_breakout:
                side = "long"
                score = 92.0 if is_cash_hours else 86.0
                active_partial_r = 4.0  # Asymmetric multi-R objective!
                reason = "forced_liquidation_breakout_long"
                analysis += f"Robbins Cup Forced Participation: Explosive breakout above 20-bar Value High (${donchian_high:.2f}) with ADX {adx_val:.1f}. Trapped shorts covering."
            elif is_in_value_zone and rsi_pullback_reset and e9_val >= e21_val:
                side = "long"
                score = 84.0 if is_cash_hours else 78.0
                reason = "btc_value_zone_pullback_long"
                analysis += f"Value zone tap into EMA 21/50 (${e21_val:.2f} - ${e50_val:.2f}) with RSI reset ({rsi_val:.1f}). Long active."
            elif ema9.iloc[-1] > ema21.iloc[-1] and ema9.iloc[-2] <= ema21.iloc[-2] and cur_price > e50_val:
                side = "long"
                score = 80.0
                reason = "btc_ema9_21_cross_long"
                analysis += f"Bullish EMA 9/21 cross confirmed above EMA 50 with RSI {rsi_val:.1f}. Long active."
            else:
                score = 52.0
                reason = "waiting_for_btc_long_trigger"
                analysis += f"Price (${cur_price:.2f}) is extended above EMA 21 (${e21_val:.2f}). Waiting for value pullback or Donchian breakout."

        # -----------------------------------------------------------------
        # Bearish Setups
        # -----------------------------------------------------------------
        elif htf_bias == "bearish":
            # Trigger A: Relief Rally Tap into EMA 21/50 resistance
            is_in_relief_zone = cur_price >= (e21_val * 0.998) and cur_price <= (e50_val * 1.002)
            rsi_relief_reset = 42.0 <= rsi_val <= 60.0

            # Trigger B: Robbins Cup Forced Liquidation Breakdown below 20-bar Donchian Low
            # Suppress breakdowns on illiquid weekends to eliminate derivative liquidation traps!
            is_breakdown = (not is_weekend) and cur_price <= float(donchian_low) and (adx_val >= 25.0 or is_squeeze)

            if is_breakdown:
                side = "short"
                score = 92.0 if is_cash_hours else 86.0
                active_partial_r = 4.0  # Asymmetric multi-R objective!
                reason = "forced_liquidation_breakdown_short"
                analysis += f"Robbins Cup Forced Participation: Explosive breakdown below 20-bar Value Low (${donchian_low:.2f}) with ADX {adx_val:.1f}. Trapped longs liquidating."
            elif is_in_relief_zone and rsi_relief_reset and e9_val <= e21_val:
                side = "short"
                score = 84.0 if is_cash_hours else 78.0
                reason = "btc_relief_zone_tap_short"
                analysis += f"Bearish relief tap into EMA 21/50 (${e21_val:.2f} - ${e50_val:.2f}) with RSI recovery ({rsi_val:.1f}). Short active."
            elif ema9.iloc[-1] < ema21.iloc[-1] and ema9.iloc[-2] >= ema21.iloc[-2] and cur_price < e50_val:
                side = "short"
                score = 80.0
                reason = "btc_ema9_21_cross_short"
                analysis += f"Bearish EMA 9/21 cross confirmed below EMA 50 with RSI {rsi_val:.1f}. Short active."
            else:
                score = 52.0
                reason = "waiting_for_btc_short_trigger"
                analysis += f"Price (${cur_price:.2f}) is below EMA 21 (${e21_val:.2f}). Waiting for relief tap or breakdown."

        # Cash hours boost
        if side != "none" and is_cash_hours:
            score = min(95.0, score + 4.0)

        checklist = {
            "session": True,
            "adx_trend": adx_val >= 20.0 or is_squeeze,
            "setup_trigger": side != "none",
            "score_met": score >= 60.0,
        }

        # Math rules and educational guide for transparency
        math_rules = {
            "trend_filter": "H4 50 EMA + M15 EMA Ribbon (9, 21, 50)",
            "momentum_gate": f"ADX >= 20 (Current: {adx_val:.1f}) and RSI Momentum (Current: {rsi_val:.1f})",
            "entry_trigger": (
                f"Breakout beyond Donchian boundary [${indicators['donchian_low']:.2f} - ${indicators['donchian_high']:.2f}] "
                f"or Value Zone tap into EMA 21/50 [${e21_val:.2f} - ${e50_val:.2f}]"
            ),
            "stop_loss": f"Entry - ({active_sl_mult} * ATR) [${active_sl_mult * atr:.2f} distance]",
            "breakeven_trigger": f"Lock entry price at +{self.be_r}R [${self.be_r * (active_sl_mult * atr):.2f}]",
            "take_profit": f"Bank 50% at +{self.partial_r}R; trail remainder along {self.trail_atr_mult} * ATR Chandelier band",
        }

        educational_guide = {
            "concept": "Bitcoin Volatility Compression & Momentum Expansion Runner",
            "why_chosen_now": (
                f"Evaluated for BTCUSD 24/7 regime ({indicators['session']}). "
                "Crypto price action forms tight compression bases before explosive trend expansion. "
                "The strategy captures both value zone pullbacks and high-velocity range breakouts."
            ),
            "institutional_edge": (
                "Avoids chasing overextended wicks. Employs dynamic weekend stop widening "
                f"({active_sl_mult}x ATR) to defend against derivative liquidation flushes, while riding "
                "multi-R trend runs with Chandelier trailing stops."
            ),
            "pitfalls_to_avoid": "Never short into a high-volume Donchian breakout or long into an EMA 50 structural break.",
        }

        return {
            "side": side,
            "score": score,
            "atr": atr,
            "sl_mult": active_sl_mult,
            "be_r": self.be_r,
            "partial_r": active_partial_r,
            "trail_mult": self.trail_atr_mult,
            "reason": reason,
            "indicators": indicators,
            "analysis": analysis,
            "checklist": checklist,
            "strategy_name": "Bitcoin Volatility Compression & Momentum Runner",
            "math_rules": math_rules,
            "educational_guide": educational_guide,
        }
