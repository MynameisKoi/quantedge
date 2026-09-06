"""BTC longs aligned with risk-on / liquidity expansion."""

from __future__ import annotations

from typing import Any

from strategies.base import BaseStrategy


class BtcLiquidityCycle(BaseStrategy):
    name = "btc_liquidity_cycle"
    assets = ["BTCUSD"]
    timeframes = ["H1", "H4", "D1"]
    enabled_regimes = ["risk-on"]

    def __init__(self) -> None:
        self._vol_scale = 1.0

    def on_regime_change(self, regime: str) -> None:
        self._vol_scale = 1.0 if regime == "risk-on" else 1.4

    def compute_signals(self, data: dict[str, Any]) -> dict[str, Any]:
        regime = data.get("regime", "risk-on")
        if not self.is_regime_allowed(regime):
            return {}

        return {
            "BTCUSD": {
                "score": 68.0,
                "side": "long",
                "atr": 1200.0 * self._vol_scale,
                "price": 65_000.0,
                "reason": "Liquidity-cycle / risk-on stub",
            }
        }
