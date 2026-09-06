"""Adaptive Strategy Router: Routes each asset to its dedicated M15 strategy."""

from __future__ import annotations

import logging
from typing import Any
import pandas as pd

from strategies.adaptive.btcusd_strategy import BtcUsdAdaptiveStrategy
from strategies.adaptive.eurusd_strategy import EurUsdAdaptiveStrategy
from strategies.adaptive.usoil_strategy import UsOilAdaptiveStrategy
from strategies.adaptive.xauusd_strategy import XauUsdAdaptiveStrategy

logger = logging.getLogger(__name__)


class AdaptiveStrategyRouter:
    """
    Routes each asset to its mathematically tailored M15 alpha strategy:
    - BTCUSD -> BtcUsdAdaptiveStrategy (Bitcoin Volatility Compression & Momentum Runner)
    - XAUUSD -> XauUsdAdaptiveStrategy (Gold Institutional Trend & Chandelier Runner)
    - EURUSD -> EurUsdAdaptiveStrategy (Forex Liquidity Sweep & Bollinger Mean Reversion)
    - USOIL  -> UsOilAdaptiveStrategy  (Crude Oil NY Session Volatility Breakout)
    """

    def __init__(self) -> None:
        self.strategies = {
            "BTCUSD": BtcUsdAdaptiveStrategy(),
            "XAUUSD": XauUsdAdaptiveStrategy(),
            "EURUSD": EurUsdAdaptiveStrategy(),
            "USOIL": UsOilAdaptiveStrategy(),
        }

    def evaluate_asset(
        self,
        asset: str,
        df_m15: pd.DataFrame,
        df_h4: pd.DataFrame | None = None,
        timestamp: pd.Timestamp | None = None,
    ) -> dict[str, Any]:
        strat = self.strategies.get(asset.upper())
        if strat is None:
            # Fallback to Gold trend model if unknown asset
            strat = self.strategies["XAUUSD"]
        return strat.evaluate(df_m15=df_m15, df_h4=df_h4, timestamp=timestamp)


# Global singleton instance
adaptive_router = AdaptiveStrategyRouter()
