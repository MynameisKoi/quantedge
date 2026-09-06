"""Multi-asset EMA crossover with ADX filter (stub scoring)."""

from __future__ import annotations

from typing import Any

from strategies.base import BaseStrategy


class EmaTrendUniversal(BaseStrategy):
    name = "ema_trend_universal"
    assets = ["XAUUSD", "USOIL", "BTCUSD", "EURUSD"]
    timeframes = ["H1", "H4"]
    enabled_regimes = ["risk-on", "risk-off", "stagflation", "deflation"]

    def __init__(self) -> None:
        self._ema_fast = 21
        self._ema_slow = 55
        self._adx_min = 18.0

    def on_regime_change(self, regime: str) -> None:
        if regime in ("risk-off", "deflation"):
            self._adx_min = 22.0
            self._ema_fast = 13
        else:
            self._adx_min = 18.0
            self._ema_fast = 21

    def compute_signals(self, data: dict[str, Any]) -> dict[str, Any]:
        regime = data.get("regime", "risk-on")
        # Mild scores so regime-specialist strategies dominate first.
        defaults = {
            "XAUUSD": (2350.0, 15.0),
            "USOIL": (78.5, 0.9),
            "BTCUSD": (65_000.0, 1100.0),
            "EURUSD": (1.085, 0.0045),
        }
        side = "short" if regime in ("risk-off", "deflation") else "long"
        out: dict[str, Any] = {}
        for asset in self.assets:
            price, atr = defaults[asset]
            out[asset] = {
                "score": 55.0,
                "side": side,
                "atr": atr,
                "price": price,
                "reason": f"EMA({self._ema_fast}/{self._ema_slow}) ADX>{self._adx_min} stub",
            }
        return out
