"""USOIL OPEC / inventory momentum — London/US sessions preferred."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from strategies.base import BaseStrategy


class OilOpecMomentum(BaseStrategy):
    name = "oil_opec_momentum"
    assets = ["USOIL"]
    timeframes = ["M5", "H1", "H4"]
    enabled_regimes = ["risk-on", "stagflation"]

    def __init__(self) -> None:
        self._breakout_buffer = 0.35

    def on_regime_change(self, regime: str) -> None:
        self._breakout_buffer = 0.5 if regime == "stagflation" else 0.35

    def compute_signals(self, data: dict[str, Any]) -> dict[str, Any]:
        regime = data.get("regime", "risk-on")
        if not self.is_regime_allowed(regime):
            return {}

        hour = datetime.now(UTC).hour
        # Restrict to London/US (approx 07:00–21:00 UTC)
        if hour < 7 or hour > 21:
            return {}

        score = 70.0 if regime == "stagflation" else 58.0
        return {
            "USOIL": {
                "score": score,
                "side": "long",
                "atr": 0.85 + self._breakout_buffer,
                "price": 78.5,
                "reason": "OPEC/inventory momentum stub (session filtered)",
            }
        }
