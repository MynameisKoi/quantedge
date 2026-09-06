"""Hierarchical Multi-Timeframe (MTF) analysis engine.

Timeframe Roles:
- HTF (D1, H4): Macro trend & institutional direction filter.
- Intermediate (H1, M30, M15): Intraday setup & momentum pullback / breakout zones.
- Lower (M5, M1): Precision execution trigger, micro structure break & spread filter.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def calculate_adx(df: pd.DataFrame, period: int = 14) -> float:
    """Compute Average Directional Index (ADX) to gauge trend strength."""
    if len(df) < period * 2:
        return 25.0
    high = df["high"]
    low = df["low"]
    close = df["close"]
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
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9))
    adx_series = dx.rolling(period).mean().dropna()
    return float(adx_series.iloc[-1]) if not adx_series.empty else 25.0


@dataclass
class MultiTimeframeState:
    asset: str
    htf_trend: str  # "bullish", "bearish", "ranging"
    mtf_setup: str  # "pullback_ema", "breakout_squeeze", "oversold_bounce", "overbought_fade", "neutral"
    micro_trigger: str  # "m5_bull_shift", "m5_bear_shift", "m5_pullback_tap_long", "m5_pullback_tap_short", "none"
    alignment_score: float  # 0.0 to 100.0
    suggested_side: str  # "long", "short", "none"
    atr_m5: float
    current_price: float
    session: str = "london_ny"  # "london", "new_york", "overlap", "asian_offhours"
    in_killzone: bool = True
    spread_pips: float = 0.0


class MultiTimeframeTracker:
    """Computes technical alignment across D1/H4, H1/M30/M15, and M5/M1 bars."""

    @staticmethod
    def evaluate_session_killzone(timestamp: pd.Timestamp | None = None) -> tuple[str, bool]:
        """Determine institutional trading session and high-liquidity killzone."""
        if timestamp is None:
            return "london_ny", True

        hour = timestamp.hour
        weekday = timestamp.weekday()  # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday

        # Weekend filter (Forex/Metals/Oil closed)
        if weekday >= 5:
            return "weekend", False

        # London: 07:00 - 12:00 UTC, Overlap: 12:00 - 16:00 UTC, NY: 16:00 - 18:00 UTC
        if 7 <= hour < 12:
            return "london", True
        if 12 <= hour < 16:
            return "overlap", True
        if 16 <= hour < 18:
            return "new_york", True

        # Asian / Late Night off-hours (00:00 - 07:00, 18:00 - 23:59 UTC)
        return "asian_offhours", False

    @staticmethod
    def evaluate_htf_trend(df_h4: pd.DataFrame | None, df_d1: pd.DataFrame | None = None) -> str:
        """Evaluate major trend from H4 (or M15 anchor) close vs EMA 50 & EMA 200 with ADX strength."""
        if df_h4 is None or len(df_h4) < 20:
            return "ranging"

        close = df_h4["close"]
        ema50 = close.ewm(span=min(50, len(close))).mean()
        ema200 = close.ewm(span=min(200, len(close))).mean()
        last_px = float(close.iloc[-1])

        # Slope of EMA 50 over last 3 bars
        lookback = min(3, len(ema50) - 1)
        ema50_slope = (ema50.iloc[-1] - ema50.iloc[-lookback]) / (ema50.iloc[-1] + 1e-9) * 100

        adx_val = calculate_adx(df_h4)
        if adx_val < 18.0:
            return "ranging"

        if last_px > ema50.iloc[-1] and (ema50.iloc[-1] > ema200.iloc[-1] or ema50_slope > 0.01):
            return "bullish"
        if last_px < ema50.iloc[-1] and (ema50.iloc[-1] < ema200.iloc[-1] or ema50_slope < -0.01):
            return "bearish"
        return "ranging"

    @staticmethod
    def evaluate_mtf_setup(df_m15: pd.DataFrame | None, df_h1: pd.DataFrame | None = None) -> str:
        """Identify intraday setup from M15 pullbacks into EMA value zones."""
        if df_m15 is None or len(df_m15) < 20:
            return "neutral"

        close = df_m15["close"]
        ema20 = close.ewm(span=20).mean()
        ema50 = close.ewm(span=50).mean()
        last_px = float(close.iloc[-1])

        # 14-period RSI
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean().iloc[-1]
        loss = (-delta.clip(upper=0)).rolling(14).mean().iloc[-1]
        rs = (gain / (loss + 1e-9)) if loss > 0 else 1.0
        rsi = 100 - (100 / (1 + rs))

        # Pullback into value zone (near EMA 20 or between EMA 20 & 50)
        dist_ema20 = abs(last_px - ema20.iloc[-1]) / (ema20.iloc[-1] + 1e-9) * 100
        in_value_zone = dist_ema20 < 0.40 or (min(ema20.iloc[-1], ema50.iloc[-1]) <= last_px <= max(ema20.iloc[-1], ema50.iloc[-1]))

        if in_value_zone and 38 <= rsi <= 62:
            return "pullback_ema"
        if rsi < 32:
            return "oversold_bounce"
        if rsi > 68:
            return "overbought_fade"
        return "neutral"

    @staticmethod
    def evaluate_micro_trigger(df_m5: pd.DataFrame | None, df_m1: pd.DataFrame | None = None) -> tuple[str, float]:
        """Pinpoint exact entry trigger and local ATR from M15 or M5 bars."""
        if df_m5 is None or len(df_m5) < 20:
            return "none", 1.0

        high = df_m5["high"]
        low = df_m5["low"]
        close = df_m5["close"]

        # 14-period ATR
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])

        ema9 = close.ewm(span=9).mean()
        ema21 = close.ewm(span=21).mean()

        # Trigger 1: Clean crossover shift
        if ema9.iloc[-1] > ema21.iloc[-1] and ema9.iloc[-2] <= ema21.iloc[-2]:
            return "m5_bull_shift", max(atr, 0.0001)
        if ema9.iloc[-1] < ema21.iloc[-1] and ema9.iloc[-2] >= ema21.iloc[-2]:
            return "m5_bear_shift", max(atr, 0.0001)

        # Trigger 2: Pullback tap and bounce off EMA21 in trend
        if ema9.iloc[-1] > ema21.iloc[-1] and low.iloc[-1] <= ema21.iloc[-1] and close.iloc[-1] > ema9.iloc[-1]:
            return "m5_pullback_tap_long", max(atr, 0.0001)
        if ema9.iloc[-1] < ema21.iloc[-1] and high.iloc[-1] >= ema21.iloc[-1] and close.iloc[-1] < ema9.iloc[-1]:
            return "m5_pullback_tap_short", max(atr, 0.0001)

        return "none", max(atr, 0.0001)

    @classmethod
    def synthesize_state(
        cls,
        asset: str,
        current_price: float,
        df_h4: pd.DataFrame | None = None,
        df_m15: pd.DataFrame | None = None,
        df_m5: pd.DataFrame | None = None,
        timestamp: pd.Timestamp | None = None,
        spread_pips: float = 0.0,
    ) -> MultiTimeframeState:
        """Combine all layers into a complete MultiTimeframeState."""
        htf = cls.evaluate_htf_trend(df_h4 if df_h4 is not None else df_m15)
        mtf = cls.evaluate_mtf_setup(df_m15)
        trigger_df = df_m5 if df_m5 is not None else df_m15
        trigger, atr = cls.evaluate_micro_trigger(trigger_df)
        session, in_killzone = cls.evaluate_session_killzone(timestamp)

        score = 50.0
        side = "none"

        # If outside liquid London/NY killzone, avoid initiating fresh day trades
        if not in_killzone and asset != "BTCUSD":
            return MultiTimeframeState(
                asset=asset,
                htf_trend=htf,
                mtf_setup=mtf,
                micro_trigger=trigger,
                alignment_score=40.0,
                suggested_side="none",
                atr_m5=atr,
                current_price=current_price,
                session=session,
                in_killzone=in_killzone,
                spread_pips=spread_pips,
            )

        # Bullish alignment
        if htf == "bullish":
            if mtf in ("pullback_ema", "oversold_bounce"):
                score += 25.0
            if trigger in ("m5_bull_shift", "m5_pullback_tap_long", "m15_bull_shift", "m15_pullback_tap_long"):
                score += 25.0
                side = "long"

        # Bearish alignment
        elif htf == "bearish":
            if mtf in ("pullback_ema", "overbought_fade"):
                score += 25.0
            if trigger in ("m5_bear_shift", "m5_pullback_tap_short", "m15_bear_shift", "m15_pullback_tap_short"):
                score += 25.0
                side = "short"

        # Range scalping (only in active sessions)
        else:
            if mtf == "oversold_bounce" and trigger in ("m5_bull_shift", "m5_pullback_tap_long", "m15_bull_shift", "m15_pullback_tap_long"):
                score = 70.0
                side = "long"
            elif mtf == "overbought_fade" and trigger in ("m5_bear_shift", "m5_pullback_tap_short", "m15_bear_shift", "m15_pullback_tap_short"):
                score = 70.0
                side = "short"

        return MultiTimeframeState(
            asset=asset,
            htf_trend=htf,
            mtf_setup=mtf,
            micro_trigger=trigger,
            alignment_score=min(100.0, score),
            suggested_side=side,
            atr_m5=atr,
            current_price=current_price,
            session=session,
            in_killzone=in_killzone,
            spread_pips=spread_pips,
        )

