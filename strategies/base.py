from abc import ABC, abstractmethod
from typing import Any


class BaseStrategy(ABC):
    name: str
    assets: list[str]
    timeframes: list[str]
    enabled_regimes: list[str] = ["risk-on", "risk-off", "stagflation", "deflation"]

    @abstractmethod
    def compute_signals(self, data: dict[str, Any]) -> dict[str, Any]:
        """Calculates quantitative composite signal score per asset."""

    @abstractmethod
    def on_regime_change(self, regime: str) -> None:
        """Dynamically adjusts parameters when macro regime shifts."""

    def is_regime_allowed(self, regime: str) -> bool:
        return regime in self.enabled_regimes
