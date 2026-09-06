"""Adaptive Strategies Package for QuantEdge."""

from strategies.adaptive.btcusd_strategy import BtcUsdAdaptiveStrategy
from strategies.adaptive.eurusd_strategy import EurUsdAdaptiveStrategy
from strategies.adaptive.router import AdaptiveStrategyRouter, adaptive_router
from strategies.adaptive.usoil_strategy import UsOilAdaptiveStrategy
from strategies.adaptive.xauusd_strategy import XauUsdAdaptiveStrategy

__all__ = [
    "BtcUsdAdaptiveStrategy",
    "XauUsdAdaptiveStrategy",
    "EurUsdAdaptiveStrategy",
    "UsOilAdaptiveStrategy",
    "AdaptiveStrategyRouter",
    "adaptive_router",
]
