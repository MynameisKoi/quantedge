"""High-Intensity Multi-Timeframe Intraday Scalper with RL Policy Feedback."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from core.rl.trade_learner import rl_policy
from strategies.base import BaseStrategy
from strategies.mtf.hierarchical_engine import MultiTimeframeTracker

logger = logging.getLogger(__name__)


class IntradayScalperStrategy(BaseStrategy):
    name = "intraday_mtf_scalper"
    assets = ["XAUUSD", "EURUSD", "USOIL", "BTCUSD"]
    timeframes = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]
    enabled_regimes = ["risk-on", "risk-off", "stagflation", "deflation"]

    def __init__(self) -> None:
        self.min_score_threshold = 60.0
        # Default price & volatility reference points
        self._price_ref = {
            "XAUUSD": {"price": 2350.0, "atr": 4.5},
            "EURUSD": {"price": 1.0850, "atr": 0.0015},
            "USOIL": {"price": 78.50, "atr": 0.35},
            "BTCUSD": {"price": 65000.0, "atr": 450.0},
        }

    def on_regime_change(self, regime: str) -> None:
        logger.info("%s notified of regime shift: %s", self.name, regime)

    def compute_signals(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Evaluate Multi-Timeframe data and RL policy for all assets.
        Generates day-trading signals with precision M1/M5 entries.
        """
        regime = data.get("regime", "risk-on")
        market_data: dict[str, Any] = data.get("market_data", {})
        signals: dict[str, Any] = {}

        for asset in self.assets:
            asset_data = market_data.get(asset, {})
            df_h4: pd.DataFrame | None = asset_data.get("H4")
            df_m15: pd.DataFrame | None = asset_data.get("M15")
            df_m5: pd.DataFrame | None = asset_data.get("M5")

            ref = self._price_ref.get(asset, {"price": 100.0, "atr": 1.0})
            price = float(asset_data.get("price", ref["price"]))

            # Step 1: MTF Hierarchical Analysis (D1/H4 trend -> M15 setup -> M5 trigger)
            mtf_state = MultiTimeframeTracker.synthesize_state(
                asset=asset,
                current_price=price,
                df_h4=df_h4,
                df_m15=df_m15,
                df_m5=df_m5,
            )

            side = mtf_state.suggested_side
            if side == "none":
                # Fallback to momentum directional test if in active regime
                side = "long" if regime in ("risk-on", "stagflation") else "short"

            # Step 2: Reinforcement Learning Policy Evaluation
            rl_decision = rl_policy.evaluate_setup(
                asset=asset,
                regime=regime,
                htf_trend=mtf_state.htf_trend,
                mtf_setup=mtf_state.mtf_setup,
                micro_trigger=mtf_state.micro_trigger,
                raw_score=mtf_state.alignment_score,
                explore=True,
            )

            # Skip if RL policy has learned that this state has negative EV
            if not rl_decision["approved"]:
                logger.debug("RL Policy pruned trade for %s (%s)", asset, rl_decision["reasoning"])
                continue

            final_score = rl_decision["adjusted_score"]
            if final_score < self.min_score_threshold:
                continue

            atr = mtf_state.atr_m5 if mtf_state.atr_m5 > 0 else ref["atr"]

            signals[asset] = {
                "score": final_score,
                "side": side,
                "price": price,
                "atr": atr,
                "size_multiplier": rl_decision["size_multiplier"],
                "q_value": rl_decision["q_value"],
                "state_key": rl_decision["state_key"],
                "rl_action": rl_decision["action"],
                "reason": (
                    f"MTF({mtf_state.htf_trend}→{mtf_state.mtf_setup}→{mtf_state.micro_trigger}) | "
                    f"RL({rl_decision['action']}, Q={rl_decision['q_value']:.2f})"
                ),
            }

        return signals
