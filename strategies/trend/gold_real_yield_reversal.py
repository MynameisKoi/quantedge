"""XAUUSD vs real-yield divergence — favors stagflation."""

from __future__ import annotations

from typing import Any

from strategies.base import BaseStrategy


class GoldRealYieldReversal(BaseStrategy):
    name = "gold_real_yield_reversal"
    assets = ["XAUUSD"]
    timeframes = ["H1", "H4", "D1"]
    enabled_regimes = ["stagflation", "risk-off", "deflation"]

    def __init__(self) -> None:
        self._atr_mult = 1.8
        self._score_boost = 0.0

    def on_regime_change(self, regime: str) -> None:
        self._score_boost = 10.0 if regime == "stagflation" else 0.0
        self._atr_mult = 2.2 if regime == "risk-off" else 1.8

    def compute_signals(self, data: dict[str, Any]) -> dict[str, Any]:
        regime = data.get("regime", "risk-on")
        if not self.is_regime_allowed(regime):
            return {}

        # Placeholder composite until live OHLC feed is wired.
        base = 62.0 + self._score_boost
        if regime == "stagflation":
            base += 12.0
        return {
            "XAUUSD": {
                "score": min(100.0, base),
                "side": "long",
                "atr": 18.5 * self._atr_mult / 1.8,
                "price": 2350.0,
                "reason": "Real-yield divergence stub; regime-gated gold bias",
            }
        }
