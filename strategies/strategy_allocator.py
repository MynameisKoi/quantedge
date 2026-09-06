"""Strategy Allocator & Macro-Technical Reasoning Engine.

Implements the Dynamic RL & Regime-Gated Strategy Allocation layer:
1. Ingests Macro Regime (risk-on, risk-off, stagflation, deflation) + News Catalysts.
2. Ingests Live MT4 Technical Indicators (prices, EMAs, ATR, ADX, Bollinger Bands, Donchian channels).
3. Uses Reinforcement Learning (Contextual Bandit Q-values) to select the optimal strategy archetype:
   - Momentum Impulse Runner (high ADX trend continuation riding EMA 9)
   - Value Pullback & Chandelier (classic EMA 21/50 value zone tap)
   - NY Volatility Breakout (channel / Donchian range breakout)
   - Liquidity Sweep Mean Revert (Bollinger Band sweep & RSI exhaustion)
4. Convenes Multi-Agent Order Discussion & Consensus Committee (Supermajority 4/5 with RiskGuard veto).
5. Provides full transparency into math rules, candidate rankings, and educational guides for user learning.
"""

from __future__ import annotations

import logging
from typing import Any

from config.settings import settings
from core.rl.trade_learner import rl_policy
from data.feeds.live_price_feed import live_price_feed
from macro.asset_macro_manager import asset_macro_manager
from macro.order_consensus import OrderConsensusResult, order_consensus_committee
from macro.regime_classifier import regime_classifier
from macro.scheduler import macro_scheduler

logger = logging.getLogger(__name__)


class StrategyAllocator:
    """
    Reasoning-driven Strategy Allocator that dynamically selects the best strategy
    for the current ongoing time using Reinforcement Learning and Multi-Agent Consensus.
    """

    SUPPORTED_ASSETS = ["XAUUSD", "USOIL", "EURUSD", "BTCUSD"]

    def __init__(self, min_score_threshold: float | None = None) -> None:
        self.min_score_threshold = (
            min_score_threshold if min_score_threshold is not None else settings.signal_threshold
        )

    def evaluate_live_allocation(
        self,
        asset: str,
        mt4_data: dict[str, Any] | None = None,
        macro_info: dict[str, Any] | None = None,
        regime: str | None = None,
        side_override: str | None = None,
        check_market_hours: bool = False,
    ) -> dict[str, Any]:
        """
        Synthesize Macro Regime, News Sentiment, and Live MT4 Technicals
        to dynamically select and evaluate the fit alpha strategy for the asset.
        """
        regime_name = regime or regime_classifier.current.name
        if macro_info is None:
            macro_info = asset_macro_manager.get_summary().get("assets", {}).get(asset, {})
        if mt4_data is None:
            mt4_data = live_price_feed.get_mt4_stats().get(asset, {})

        live_px = float(mt4_data.get("price", mt4_data.get("bid", 0.0)))
        if live_px <= 0:
            prices = live_price_feed.get_live_prices_sync()
            live_px = float(prices.get(asset, 0.0))

        macro_bias = float(macro_info.get("bias", 0.0))
        macro_stance = str(macro_info.get("stance", "NEUTRAL")).upper()
        macro_summary = str(macro_info.get("summary", "Monitoring institutional order flow."))

        # 0. Market Hours Gate: Suppress execution and LLM deliberation during down-market hours
        is_market_open = True
        mkt_status = "Market Open"
        if check_market_hours and side_override is None:
            is_market_open, mkt_status = macro_scheduler.is_asset_market_open(asset)

        # ---------------------------------------------------------------------
        # 1. Indicator Pre-processing & Baseline Metrics
        # ---------------------------------------------------------------------
        if asset == "XAUUSD":
            ema9 = float(mt4_data.get("ema9", live_px))
            ema21 = float(mt4_data.get("ema21", live_px))
            ema50 = float(mt4_data.get("ema50", live_px))
            atr = float(mt4_data.get("atr", 10.5))
            adx = float(mt4_data.get("adx", 20.0))
            crange = float(mt4_data.get("candle_range", 0.0))
            cbody = float(mt4_data.get("candle_body", 0.0))
            trend = "bullish" if ema9 > ema21 else "bearish"
            indicators = {
                "price": live_px, "ema9": ema9, "ema21": ema21, "ema50": ema50,
                "atr": atr, "adx": adx, "trend": trend,
                "candle_range": crange, "candle_body": cbody,
            }
            atr_pct = atr / max(live_px, 1.0)
        elif asset == "USOIL":
            ema20 = float(mt4_data.get("ema20", live_px))
            ema50 = float(mt4_data.get("ema50", live_px))
            dh = float(mt4_data.get("donchian_high", live_px + 0.5))
            dl = float(mt4_data.get("donchian_low", live_px - 0.5))
            atr = float(mt4_data.get("atr", 0.40))
            adx = float(mt4_data.get("adx", 25.0))
            crange = float(mt4_data.get("candle_range", 0.0))
            cbody = float(mt4_data.get("candle_body", 0.0))
            trend = "bullish" if ema20 >= ema50 else "bearish"
            indicators = {
                "price": live_px, "ema20": ema20, "ema50": ema50,
                "donchian_high": dh, "donchian_low": dl,
                "atr": atr, "adx": adx, "trend": trend,
                "candle_range": crange, "candle_body": cbody,
            }
            atr_pct = atr / max(live_px, 1.0)
        elif asset == "EURUSD":
            up = float(mt4_data.get("bb_upper", live_px + 0.001))
            mid = float(mt4_data.get("bb_middle", live_px))
            low = float(mt4_data.get("bb_lower", live_px - 0.001))
            rsi = float(mt4_data.get("rsi", 50.0))
            atr = float(mt4_data.get("atr", 0.00045))
            adx = float(mt4_data.get("adx", 20.0))
            crange = float(mt4_data.get("candle_range", 0.0))
            cbody = float(mt4_data.get("candle_body", 0.0))
            trend = "bullish" if live_px > mid else ("bearish" if live_px < mid else "neutral")
            indicators = {
                "price": live_px, "bb_upper": up, "bb_middle": mid, "bb_lower": low,
                "rsi": rsi, "atr": atr, "adx": adx, "trend": trend,
                "candle_range": crange, "candle_body": cbody,
            }
            atr_pct = atr / max(live_px, 1.0)
        else:  # BTCUSD
            ema9 = float(mt4_data.get("ema9", live_px))
            ema21 = float(mt4_data.get("ema21", live_px))
            ema50 = float(mt4_data.get("ema50", live_px))
            atr = float(mt4_data.get("atr", 250.0))
            rsi = float(mt4_data.get("rsi", 50.0))
            adx = float(mt4_data.get("adx", 26.0))
            dh = float(mt4_data.get("donchian_high", ema50 + 2.0 * atr))
            dl = float(mt4_data.get("donchian_low", ema50 - 2.0 * atr))
            crange = float(mt4_data.get("candle_range", 0.0))
            cbody = float(mt4_data.get("candle_body", 0.0))
            trend = "bullish" if ema9 > ema21 else "bearish"
            indicators = {
                "price": live_px, "ema9": ema9, "ema21": ema21, "ema50": ema50,
                "atr": atr, "rsi": rsi, "adx": adx, "trend": trend,
                "donchian_high": dh, "donchian_low": dl,
                "candle_range": crange, "candle_body": cbody,
            }
            atr_pct = atr / max(live_px, 1.0)

        # ---------------------------------------------------------------------
        # 2. Reinforcement Learning: Dynamic Strategy Archetype Selection
        # ---------------------------------------------------------------------
        rl_choice = rl_policy.select_strategy(
            asset=asset,
            regime=regime_name,
            adx=adx,
            atr_pct=atr_pct,
            explore=False,
        )
        archetype = rl_choice["selected_strategy"]
        candidates = rl_choice["candidates"]

        # Setup-aware archetype resolution: Prioritize High-Velocity Forced Breakouts/Breakdowns
        # (Robbins Cup: Pounce on forced liquidation cascades like 4 Sep 09:45-12:45)
        has_donchian = ("donchian_high" in indicators) and ("donchian_low" in indicators)
        is_breakout_extreme = has_donchian and (
            live_px >= indicators.get("donchian_high", float("inf"))
            or live_px <= indicators.get("donchian_low", float("-inf"))
        )

        if asset in ("USOIL", "BTCUSD") and is_breakout_extreme:
            archetype = "volatility_breakout"
        elif asset == "EURUSD" and ("bb_lower" in indicators) and (live_px <= indicators.get("bb_lower", float("-inf")) or live_px >= indicators.get("bb_upper", float("inf"))) and (indicators.get("rsi", 50.0) <= 38.0 or indicators.get("rsi", 50.0) >= 62.0):
            archetype = "mean_revert"
        elif asset in ("XAUUSD", "BTCUSD") and ("ema21" in indicators) and ("ema50" in indicators):
            e21 = indicators["ema21"]
            e50 = indicators["ema50"]
            is_pullback = (live_px <= e21 and live_px >= e50) if trend == "bullish" else (live_px >= e21 and live_px <= e50)
            if is_pullback:
                archetype = "value_pullback"
        elif adx >= 22.0 and ("ema9" in indicators):
            e9 = indicators["ema9"]
            is_momentum = (live_px >= e9) if trend == "bullish" else (live_px <= e9)
            if is_momentum:
                archetype = "momentum_impulse"

        # Strategy Archetype Customization & Educational Content
        archetype_titles = {
            "momentum_impulse": "Momentum Impulse Runner",
            "value_pullback": "Institutional Trend & Chandelier Runner",
            "volatility_breakout": "NY Volatility Breakout",
            "mean_revert": "Liquidity Sweep Mean Revert",
        }
        if asset == "BTCUSD":
            strategy_name = "Bitcoin Volatility Compression & Momentum Runner"
        else:
            strategy_name = archetype_titles.get(archetype, "Adaptive M15 Strategy")

        # ---------------------------------------------------------------------
        # 3. Strategy Execution Logic & Math Formulas
        # ---------------------------------------------------------------------
        side = "none"
        score = 50.0
        reason = "waiting_for_setup"
        tech_analysis = ""
        math_rules: dict[str, str] = {}
        educational_guide: dict[str, str] = {}

        sl_mult = 1.5
        be_r = 1.0
        partial_r = 2.0

        # Robbins Cup Location & Environment Filter (Chop Gate):
        # Assess whether price is trapped at the Point of Control (POC equilibrium)
        # during low volatility. Entering in dead chop produces 0 edge, whipsaws, and commission drag.
        ref_dh = indicators.get("donchian_high", live_px + atr)
        ref_dl = indicators.get("donchian_low", live_px - atr)
        poc_price = (ref_dh + ref_dl) / 2.0
        dist_from_poc_pct = abs(live_px - poc_price) / max(live_px, 1.0)
        crange = indicators.get("candle_range", 0.0)

        is_low_movement_chop = (
            side_override is None
            and not is_breakout_extreme
            and (
                # Condition A: Stagnant ADX (< 18.0) inside Donchian boundaries
                (adx < 18.0 and live_px > ref_dl and live_px < ref_dh)
                # Condition B: Tiny candle range (< 0.50x ATR) hovering near POC (< 0.35%)
                or (adx < 22.0 and crange > 0 and crange < (0.50 * atr) and dist_from_poc_pct < 0.0035)
            )
        )

        checklist = {
            "session": True,
            "adx_trend": adx >= 18.0 and not is_low_movement_chop,
            "setup_trigger": False,
            "agent_consensus": False,
            "score_met": False,
        }

        # Archetype 1: Momentum Impulse Runner (High ADX Impulse Ride)
        if archetype == "momentum_impulse":
            sl_mult = 1.5
            be_r = 1.0
            partial_r = 2.2
            math_rules = {
                "entry_rule": "Bullish: live_price >= EMA9 & EMA9 > EMA21; Bearish: live_price <= EMA9 & EMA9 < EMA21",
                "trend_filter": f"ADX >= 20.0 (Current ADX: {adx:.1f})",
                "stop_loss": f"Entry - ({sl_mult} * ATR)",
                "breakeven_trigger": f"Trailing stop to Entry at +{be_r}R gain",
                "take_profit": f"Partial exit (+{partial_r}R); trail remainder on M15 EMA 9",
            }
            educational_guide = {
                "concept": "High-Velocity Impulse Following",
                "why_chosen_now": (
                    f"Selected by RL policy (Q={rl_choice['top_q']}) because ADX ({adx:.1f}) demonstrates directional strength. "
                    "In strong impulse waves, waiting for deep pullbacks into EMA 21 causes traders to miss 100% of the move."
                ),
                "institutional_edge": "Captures the strongest phase of the trend by riding short-term exponential momentum with an adaptive stop.",
                "pitfalls_to_avoid": "Do not trade during low ADX (< 18) consolidation or right before Tier-1 economic news.",
            }

            if asset in ("XAUUSD", "BTCUSD"):
                if trend == "bullish" and live_px >= ema9:
                    side = "long"
                    score = 58.0
                    reason = "momentum_impulse_long"
                    tech_analysis = f"{asset} in strong BULLISH impulse (ADX {adx:.1f}). Riding EMA 9 ({ema9:.2f}) momentum. Long active."
                    checklist["setup_trigger"] = True
                elif trend == "bearish" and live_px <= ema9:
                    side = "short"
                    score = 58.0
                    reason = "momentum_impulse_short"
                    tech_analysis = f"{asset} in strong BEARISH impulse (ADX {adx:.1f}). Riding below EMA 9 ({ema9:.2f}) momentum. Short active."
                    checklist["setup_trigger"] = True
                else:
                    score = 52.0
                    reason = "momentum_consolidation"
                    tech_analysis = f"{asset} trend is {trend.upper()}, but price is consolidating around EMA 9. Waiting for continuation candle."
            elif asset == "USOIL":
                if trend == "bullish" and live_px >= ema20:
                    side = "long"
                    score = 58.0
                    reason = "oil_momentum_long"
                    tech_analysis = f"WTI Crude strong trend continuation above EMA 20 ({ema20:.2f}) with ADX {adx:.1f}. Long active."
                    checklist["setup_trigger"] = True
                elif trend == "bearish" and live_px <= ema20:
                    side = "short"
                    score = 58.0
                    reason = "oil_momentum_short"
                    tech_analysis = f"WTI Crude downward momentum continuation below EMA 20 ({ema20:.2f}) with ADX {adx:.1f}. Short active."
                    checklist["setup_trigger"] = True
                else:
                    score = 52.0
                    reason = "oil_range"
                    tech_analysis = f"WTI Crude trend is {trend.upper()}. Waiting for directional momentum continuation."
            else:  # EURUSD
                if trend == "bullish" and live_px > mid:
                    side = "long"
                    score = 58.0
                    reason = "eur_momentum_long"
                    tech_analysis = f"EURUSD trending long above middle band ({mid:.5f}) with ADX {adx:.1f}. Long active."
                    checklist["setup_trigger"] = True
                elif trend == "bearish" and live_px < mid:
                    side = "short"
                    score = 58.0
                    reason = "eur_momentum_short"
                    tech_analysis = f"EURUSD trending short below middle band ({mid:.5f}) with ADX {adx:.1f}. Short active."
                    checklist["setup_trigger"] = True

        # Archetype 2: Value Pullback & Chandelier Runner (Classic Pullback)
        elif archetype == "value_pullback":
            sl_mult = 1.8
            be_r = 1.0
            partial_r = 2.0
            math_rules = {
                "entry_rule": "Pullback tap into value zone: Long: EMA 21 to EMA 50; Short: EMA 21 to EMA 50",
                "trend_filter": "EMA 9 > EMA 21 (Bullish) or EMA 9 < EMA 21 (Bearish)",
                "stop_loss": f"Entry - ({sl_mult} * ATR)",
                "breakeven_trigger": f"Move SL to Entry at +{be_r}R",
                "take_profit": f"Target +{partial_r}R; trail stop along Chandelier volatility band",
            }
            educational_guide = {
                "concept": "Institutional Value Pullback Tap",
                "why_chosen_now": (
                    f"Selected by RL policy (Q={rl_choice['top_q']}) for steady trend conditions. "
                    "Institutional order flow accumulates assets at the mean (EMA 21/50) rather than chasing extended breakouts."
                ),
                "institutional_edge": "Optimal asymmetric Risk-to-Reward: entry near value zone minimizes SL distance and maximizes R-multiples.",
                "pitfalls_to_avoid": "Do not buy pullbacks that break with heavy volume below the EMA 50 support line.",
            }

            if asset in ("XAUUSD", "BTCUSD"):
                e21 = indicators.get("ema21", live_px)
                e50 = indicators.get("ema50", e21 - 1.5 * atr if trend == "bullish" else e21 + 1.5 * atr)
                if trend == "bullish":
                    if live_px <= e21 and live_px >= e50:
                        side = "long"
                        score = 58.0
                        reason = "value_pullback_tap_long"
                        tech_analysis = f"{asset} pullback tap into EMA 21 value zone with bullish structure. Long active."
                        checklist["setup_trigger"] = True
                    else:
                        score = 50.0
                        reason = "waiting_for_pullback"
                        tech_analysis = f"{asset} is BULLISH. Price ({live_px:.2f}) waiting for pullback into EMA 21 ({e21:.2f})."
                else:
                    if live_px >= e21 and live_px <= e50:
                        side = "short"
                        score = 58.0
                        reason = "value_relief_tap_short"
                        tech_analysis = f"{asset} relief tap into EMA 21 value zone with bearish structure. Short active."
                        checklist["setup_trigger"] = True
                    else:
                        score = 50.0
                        reason = "waiting_for_relief"
                        tech_analysis = f"{asset} is BEARISH. Price ({live_px:.2f}) waiting for relief tap into EMA 21 ({e21:.2f})."
            elif asset == "USOIL":
                if trend == "bullish" and live_px <= ema20 and live_px >= ema50:
                    side = "long"
                    score = 58.0
                    reason = "oil_pullback_long"
                    tech_analysis = f"WTI Crude pullback tap into EMA 20/50 zone ({ema20:.2f} - {ema50:.2f}). Long active."
                    checklist["setup_trigger"] = True
                elif trend == "bearish" and live_px >= ema20 and live_px <= ema50:
                    side = "short"
                    score = 58.0
                    reason = "oil_pullback_short"
                    tech_analysis = f"WTI Crude relief tap into EMA 20/50 zone. Short active."
                    checklist["setup_trigger"] = True
                else:
                    score = 50.0
                    reason = "waiting_for_pullback"
                    tech_analysis = f"WTI Crude waiting for pullback into EMA 20/50 value zone."
            else:  # EURUSD
                if trend == "bullish" and live_px <= mid and live_px >= low:
                    side = "long"
                    score = 58.0
                    reason = "eur_pullback_long"
                    tech_analysis = f"EURUSD pullback tap into middle Bollinger band. Long active."
                    checklist["setup_trigger"] = True
                elif trend == "bearish" and live_px >= mid and live_px <= up:
                    side = "short"
                    score = 58.0
                    reason = "eur_pullback_short"
                    tech_analysis = f"EURUSD relief tap into middle Bollinger band. Short active."
                    checklist["setup_trigger"] = True
                else:
                    score = 50.0
                    reason = "waiting_for_pullback"
                    tech_analysis = f"EURUSD waiting for pullback into middle band."

        # Archetype 3: NY Volatility Breakout (Channel Breakout)
        elif archetype == "volatility_breakout":
            sl_mult = 2.0
            be_r = 1.0
            partial_r = 2.0
            math_rules = {
                "entry_rule": "Long: live_price >= Donchian High / Upper Band; Short: live_price <= Donchian Low / Lower Band",
                "volatility_filter": "ATR expansion above 20-bar baseline",
                "stop_loss": f"Entry - ({sl_mult} * ATR)",
                "breakeven_trigger": f"Move to BE at +{be_r}R",
                "take_profit": f"+{partial_r}R breakout target",
            }
            educational_guide = {
                "concept": "Volatility Expansion Breakout",
                "why_chosen_now": f"Selected by RL policy (Q={rl_choice['top_q']}) for consolidation expansion setup.",
                "institutional_edge": "Catches explosive moves when volatility compresses and market participants are trapped on breakout.",
                "pitfalls_to_avoid": "Beware false breakouts during low liquidity Asian session hours.",
            }

            if asset == "USOIL":
                if live_px >= dh and ema20 >= ema50:
                    side = "long"
                    score = 58.0
                    reason = "donchian_breakout_long"
                    tech_analysis = f"WTI Crude 20-bar Donchian breakout above {dh:.2f}. Long active."
                    checklist["setup_trigger"] = True
                elif live_px <= dl and ema20 <= ema50:
                    side = "short"
                    score = 58.0
                    reason = "donchian_breakdown_short"
                    tech_analysis = f"WTI Crude 20-bar Donchian breakdown below {dl:.2f}. Short active."
                    checklist["setup_trigger"] = True
                else:
                    score = 50.0
                    reason = "inside_donchian_range"
                    tech_analysis = f"WTI Crude inside Donchian range [{dl:.2f} - {dh:.2f}]. Waiting for breakout."
            elif asset == "BTCUSD":
                e50 = indicators.get("ema50", live_px)
                btc_dh = indicators.get("donchian_high", e50 + 1.5 * atr)
                btc_dl = indicators.get("donchian_low", e50 - 1.5 * atr)
                sl_mult = 1.8
                be_r = 1.2
                partial_r = 4.0  # Asymmetric multi-thousand dollar runner (+4.0R objective)!

                if live_px <= btc_dl and trend == "bearish":
                    side = "short"
                    score = 62.0
                    reason = "forced_liquidation_breakdown_short"
                    tech_analysis = (
                        f"Robbins Cup Forced Participation: Bitcoin explosive breakdown below 20-bar Value Low (${btc_dl:.2f}). "
                        f"Trapped longs liquidating with ADX {adx:.1f}. High conviction Short."
                    )
                    checklist["setup_trigger"] = True
                elif live_px >= btc_dh and trend == "bullish":
                    side = "long"
                    score = 62.0
                    reason = "forced_liquidation_breakout_long"
                    tech_analysis = (
                        f"Robbins Cup Forced Participation: Bitcoin explosive breakout above 20-bar Value High (${btc_dh:.2f}). "
                        f"Trapped shorts covering with ADX {adx:.1f}. High conviction Long."
                    )
                    checklist["setup_trigger"] = True
                else:
                    score = 50.0
                    reason = "inside_donchian_range"
                    tech_analysis = f"Bitcoin consolidating inside Donchian range [${btc_dl:.2f} - ${btc_dh:.2f}]. Waiting for breakout."
            else:
                score = 50.0
                reason = "waiting_for_channel_breakout"
                tech_analysis = f"{asset} waiting for volatility breakout beyond outer channel boundary."

        # Archetype 4: Liquidity Sweep Mean Revert (Bollinger & RSI Sweep)
        else:  # mean_revert
            sl_mult = 1.2
            be_r = 0.8
            partial_r = 1.5
            math_rules = {
                "entry_rule": "Long: Price <= Lower BB & RSI <= 35; Short: Price >= Upper BB & RSI >= 65",
                "oscillator_filter": "RSI extreme exhaustion (<= 35 oversold / >= 65 overbought)",
                "stop_loss": f"Entry - ({sl_mult} * ATR)",
                "breakeven_trigger": f"Move to BE at +{be_r}R",
                "take_profit": f"Target +{partial_r}R at middle Bollinger Band",
            }
            educational_guide = {
                "concept": "Liquidity Sweep & Statistical Mean Reversion",
                "why_chosen_now": (
                    f"Selected by RL policy (Q={rl_choice['top_q']}) during low-ADX range bound conditions. "
                    "When ADX < 20, price tends to oscillate between statistical extremes (Bollinger Bands)."
                ),
                "institutional_edge": "Sweeps trapped liquidity beyond support/resistance and reverts back to equilibrium.",
                "pitfalls_to_avoid": "Never use mean reversion when ADX >= 25; trending momentum will cause stop outs.",
            }

            if asset == "EURUSD":
                if live_px <= low and rsi <= 38.0:
                    side = "long"
                    score = 58.0
                    reason = "eur_oversold_sweep_long"
                    tech_analysis = f"EURUSD swept below lower band ({low:.5f}) with RSI {rsi:.1f}. Mean reversion Long active."
                    checklist["setup_trigger"] = True
                elif live_px >= up and rsi >= 62.0:
                    side = "short"
                    score = 58.0
                    reason = "eur_overbought_sweep_short"
                    tech_analysis = f"EURUSD swept above upper band ({up:.5f}) with RSI {rsi:.1f}. Mean reversion Short active."
                    checklist["setup_trigger"] = True
                else:
                    score = 50.0
                    reason = "inside_bands_neutral"
                    tech_analysis = f"EURUSD inside Bollinger Bands [{low:.5f} - {up:.5f}] with RSI {rsi:.1f}. Waiting for sweep."
            elif asset == "BTCUSD":
                if rsi >= 65.0:
                    side = "short"
                    score = 58.0
                    reason = "btc_overbought_exhaustion_short"
                    tech_analysis = f"Bitcoin RSI {rsi:.1f} extreme overbought exhaustion. Tactical mean reversion Short active."
                    checklist["setup_trigger"] = True
                elif rsi <= 35.0:
                    side = "long"
                    score = 58.0
                    reason = "btc_oversold_sweep_long"
                    tech_analysis = f"Bitcoin RSI {rsi:.1f} extreme oversold sweep. Tactical mean reversion Long active."
                    checklist["setup_trigger"] = True
                else:
                    score = 50.0
                    reason = "waiting_for_reversion_sweep"
                    tech_analysis = f"Bitcoin RSI {rsi:.1f} in neutral zone. Waiting for extreme deviation."
            else:
                score = 50.0
                reason = "waiting_for_reversion_sweep"
                tech_analysis = f"{asset} waiting for extreme statistical deviation sweep."

        # ---------------------------------------------------------------------
        # Apply Robbins Cup Low-Movement Chop Filter
        # ---------------------------------------------------------------------
        if is_low_movement_chop:
            side = "none"
            score = 42.0
            reason = "low_movement_chop_suppressed"
            checklist["adx_trend"] = False
            checklist["setup_trigger"] = False
            tech_analysis = (
                f"Robbins Cup Location Filter: {asset} trapped at equilibrium POC (${poc_price:.2f}) "
                f"with compressed volatility (ADX {adx:.1f} < 18.0). Conserving capital until volatility expands."
            )

        # Directional override or candidate bias
        if side_override in ("long", "short", "buy", "sell"):
            side = "long" if side_override in ("long", "buy") else "short"
            eval_side = side
            checklist["setup_trigger"] = True
            reason = f"manual_{side}_order"
            tech_analysis = f"Direct {side.upper()} order execution requested. Evaluating consensus & risk parameters."
        else:
            # If side is still 'none' but trend is clearly defined, provide directional candidate bias
            eval_side = side if side != "none" else ("long" if trend == "bullish" else "short")

        # ---------------------------------------------------------------------
        # 4. Multi-Agent Order Discussion & Consensus Committee Deliberation
        # ---------------------------------------------------------------------
        if not is_market_open:
            side = "none"
            score = 0.0
            reason = "market_closed"
            tech_analysis = (
                f"{asset} market is closed ({mkt_status}). "
                f"Consensus deliberation and order dispatch suspended until market reopening."
            )
            checklist["session"] = False
            checklist["setup_trigger"] = False
            checklist["adx_trend"] = False
            checklist["agent_consensus"] = False
            checklist["score_met"] = False
            all_agents_agreed = False
            consensus_res = OrderConsensusResult(
                asset=asset,
                side="none",
                all_agreed=False,
                total_agents=5,
                agreed_count=0,
                agreement_ratio=0.0,
                consensus_bonus=0.0,
                discussion_summary=f"Market closed for {asset}: {mkt_status}. Deliberation suspended.",
                agent_votes=[],
            )
            status = "MARKET_CLOSED"
            potential_order = {"triggered": False, "type": "MARKET_CLOSED", "action": "STAND_DOWN", "reason": "market_closed"}
        else:
            consensus_res = order_consensus_committee.discuss_order(
                asset=asset,
                side=eval_side if checklist["setup_trigger"] else side,
                price=live_px,
                indicators=indicators,
                regime_name=regime_name,
                macro_info=macro_info,
                setup_triggered=checklist.get("setup_trigger", False),
                sl_mult=sl_mult,
                be_r=be_r,
                partial_r=partial_r,
            )

            all_agents_agreed = consensus_res.all_agreed
            checklist["agent_consensus"] = all_agents_agreed

            # When consensus is reached, apply the consensus boost (+15.0 pts)
            if all_agents_agreed and checklist["setup_trigger"]:
                score += consensus_res.consensus_bonus
            elif not all_agents_agreed:
                score = min(score, self.min_score_threshold - 5.0)

            # Apply Macro News Catalyst bias adjustment
            macro_adj, macro_reason = asset_macro_manager.get_quant_adjustment(asset, side, macro_info=macro_info)
            if side in ("long", "short"):
                score = min(100.0, max(0.0, score + macro_adj))

            # Check if Signal Threshold Gauge is met
            threshold_met = (score >= self.min_score_threshold) and all_agents_agreed and checklist["setup_trigger"]
            checklist["score_met"] = threshold_met

            is_ready = threshold_met and side in ("long", "short")
            is_imminent = score >= 55.0 and side != "none" and not is_ready

            potential_order = None
            if is_ready:
                potential_order = {
                    "triggered": True,
                    "type": "EXECUTION_READY",
                    "action": f"BUY (LONG)" if side == "long" else f"SELL (SHORT)",
                    "symbol": asset,
                    "price": live_px,
                    "score": round(score, 1),
                    "threshold": self.min_score_threshold,
                    "reason": reason,
                    "sl_mult": sl_mult,
                    "be_r": be_r,
                    "partial_r": partial_r,
                    "agent_consensus": consensus_res.as_dict(),
                    "alert_text": (
                        f"[ALL AGENTS AGREED] Signal threshold gauge met ({score:.1f}/{self.min_score_threshold:.0f}). "
                        f"Order ready for MT4 execution: {side.upper()} {asset} at {live_px}"
                    ),
                }
            elif is_imminent:
                potential_order = {
                    "triggered": False,
                    "type": "AGENTS_DEBATING",
                    "action": f"WATCH {side.upper()}",
                    "symbol": asset,
                    "price": live_px,
                    "score": round(score, 1),
                    "threshold": self.min_score_threshold,
                    "reason": reason,
                    "sl_mult": sl_mult,
                    "be_r": be_r,
                    "partial_r": partial_r,
                    "agent_consensus": consensus_res.as_dict(),
                    "alert_text": (
                        f"[AGENTS DEBATING] {strategy_name} approaching threshold ({score:.1f}/{self.min_score_threshold:.0f}) — "
                        f"{consensus_res.agreed_count}/{consensus_res.total_agents} agents agreed."
                    ),
                }

            status = "SIGNAL_TRIGGERED" if is_ready else ("AGENTS_DEBATING" if is_imminent else "WAITING_SETUP")
            if is_low_movement_chop:
                status = "CHOP_EQUILIBRIUM_SUPPRESSED"

        if macro_info.get("stance"):
            full_reasoning = f"{tech_analysis} [Macro Catalyst: {macro_stance} ({macro_bias:+0.2f})] - {macro_summary}"
        else:
            full_reasoning = tech_analysis

        return {
            "asset": asset,
            "strategy_name": strategy_name,
            "strategy_archetype": archetype,
            "score": round(score, 1),
            "side": side,
            "live_price": live_px,
            "reason": reason,
            "reasoning": full_reasoning,
            "analysis": full_reasoning,
            "indicators": indicators,
            "atr": atr,
            "checklist": checklist,
            "threshold": self.min_score_threshold,
            "progress_pct": min(100.0, round((score / self.min_score_threshold) * 100.0, 1)),
            "status": status,
            "sl_mult": sl_mult,
            "be_r": be_r,
            "partial_r": partial_r,
            "potential_order": potential_order,
            "agent_consensus": consensus_res.as_dict(),
            "consensus_summary": consensus_res.discussion_summary,
            "agent_votes": consensus_res.agent_votes,
            "asset_macro": macro_info,
            "rl_intel": {
                "state_key": rl_choice["state_key"],
                "selected_archetype": archetype,
                "top_q_value": rl_choice["top_q"],
                "exploration": rl_choice["exploration"],
                "q_values": rl_choice["q_values"],
                "candidates": candidates,
            },
            "math_rules": (
                {
                    "trend_filter": "H4 50/200 EMA + M15 EMA Ribbon (EMA 9, EMA 21, EMA 50)",
                    "momentum_gate": f"ADX >= 20 (Current: {adx:.1f}) & RSI Momentum (Current: {rsi:.1f})",
                    "entry_trigger": "Donchian 20-bar volatility breakout or EMA 21/50 Value Zone pullback tap",
                    "stop_loss": f"Entry - ({sl_mult} * ATR) [${sl_mult * atr:.2f} distance]",
                    "breakeven_trigger": f"Lock entry price at +{be_r}R [${be_r * (sl_mult * atr):.2f}]",
                    "take_profit": f"Bank 50% at +{partial_r}R; trail remainder along 2.5 * ATR Chandelier band",
                }
                if asset == "BTCUSD"
                else math_rules
            ),
            "educational_guide": (
                {
                    "concept": "Bitcoin Volatility Compression & Momentum Expansion",
                    "why_chosen_now": (
                        f"Selected by RL policy (Q={rl_choice['top_q']}) for 24/7 crypto regime. "
                        "Bitcoin price action compresses inside tight ranges before explosive directional trend expansion."
                    ),
                    "institutional_edge": (
                        "Combines H4 Macro Trend + M15 EMA Ribbon with dynamic weekend stop widening (2.2x ATR) "
                        "to eliminate derivative wick flushes, riding sustained moves with Chandelier trailing stops."
                    ),
                    "pitfalls_to_avoid": "Do not trade into low ADX (<20) weekend chop or fight strong EMA 50 trend breaks.",
                }
                if asset == "BTCUSD"
                else educational_guide
            ),
        }

    def allocate_all(self) -> dict[str, Any]:
        """Evaluate strategy allocation and macro reasoning across all supported CFD assets."""
        mt4_all = live_price_feed.get_mt4_stats()
        macro_summary = asset_macro_manager.get_summary().get("assets", {})
        regime = regime_classifier.current.name

        results = {}
        for asset in self.SUPPORTED_ASSETS:
            results[asset] = self.evaluate_live_allocation(
                asset=asset,
                mt4_data=mt4_all.get(asset),
                macro_info=macro_summary.get(asset),
                regime=regime,
                check_market_hours=True,
            )
        return results


# Global singleton allocator
strategy_allocator = StrategyAllocator()
