"""Live Multi-Asset M15 Adaptive Strategy for QuantEdge Core Engine."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
import pandas as pd

from config.settings import settings
from data.feeds.live_price_feed import live_price_feed
from macro.asset_macro_manager import asset_macro_manager
from strategies.adaptive.router import adaptive_router
from strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


class AdaptiveM15LiveStrategy(BaseStrategy):
    """
    Live production strategy wrapper for M15 execution on Exness MT4:
    - Automatically routes XAUUSD, USOIL, and EURUSD to their specialized M15 models.
    - Manages risk multipliers and custom take-profit / breakeven triggers per asset.
    """

    name = "adaptive_m15_portfolio"
    assets = ["XAUUSD", "USOIL", "EURUSD", "BTCUSD"]
    timeframes = ["M15", "H4"]
    enabled_regimes = ["risk-on", "risk-off", "stagflation", "deflation"]

    def __init__(self) -> None:
        self.min_score_threshold = settings.signal_threshold
        self._cached_dfs: dict[str, pd.DataFrame] = {}
        self._price_ref = {
            "XAUUSD": {"price": 4420.0, "atr": 10.5},
            "USOIL": {"price": 89.0, "atr": 0.40},
            "EURUSD": {"price": 1.1610, "atr": 0.00045},
            "BTCUSD": {"price": 79400.0, "atr": 250.0},
        }

    def _get_or_load_m15(self, asset: str, live_price: float | None = None) -> pd.DataFrame | None:
        """Provide rolling M15 bars calibrated to latest live market price."""
        if asset not in self._cached_dfs:
            csv_path = Path(f"data/historical/{asset}_5M.csv")
            if csv_path.exists():
                try:
                    df = pd.read_csv(csv_path)
                    df["Datetime"] = pd.to_datetime(df["Datetime"], utc=True)
                    df = df.set_index("Datetime")
                    df_m15 = df.resample("15min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
                    self._cached_dfs[asset] = df_m15.tail(150).copy()
                except Exception as e:
                    logger.debug("Failed loading fallback M15 for %s: %s", asset, e)

        df = self._cached_dfs.get(asset)
        if df is not None and not df.empty and live_price is not None and live_price > 0:
            df_live = df.copy()
            mean_px = float(df_live["close"].tail(20).mean())
            # If price level differs by > 2%, rescale OHLC geometry so indicators are perfectly calibrated
            if mean_px > 0 and abs(mean_px - live_price) / live_price > 0.02:
                scale = live_price / float(df_live["close"].iloc[-1])
                for col in ("open", "high", "low", "close"):
                    df_live[col] = (df_live[col] * scale).round(5 if asset == "EURUSD" else 2)
            last_idx = df_live.index[-1]
            df_live.loc[last_idx, "close"] = live_price
            if live_price > float(df_live.loc[last_idx, "high"]):
                df_live.loc[last_idx, "high"] = live_price
            if live_price < float(df_live.loc[last_idx, "low"]):
                df_live.loc[last_idx, "low"] = live_price
            return df_live
        return df

    def on_regime_change(self, regime: str) -> None:
        logger.info("%s notified of macro regime shift: %s", self.name, regime)

    def compute_signals(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Evaluate adaptive models for all active CFD assets.
        - In Live Mode (default): uses StrategyAllocator to ingest live MT4 technicals,
          macro regime, and news catalysts with multi-factor reasoning.
        - In Backtest Mode (market_data provided): uses historical DataFrames to benchmark
          and optimize alpha strategies against walk-forward data.
        """
        regime = data.get("regime", "risk-on")
        ts = data.get("timestamp")
        cur_ts = pd.Timestamp(ts) if ts is not None else None
        market_data = data.get("market_data", {})
        signals: dict[str, Any] = {}

        # 1. Backtest Mode: Historical DataFrames supplied
        if market_data:
            live_prices = live_price_feed.get_live_prices_sync()
            for asset in self.assets:
                ref = self._price_ref.get(asset, {"price": 100.0, "atr": 1.0})
                live_px = live_prices.get(asset)
                asset_data = market_data.get(asset, {})
                df_m15: pd.DataFrame | None = asset_data.get("M15") if asset_data.get("M15") is not None else self._get_or_load_m15(asset, live_price=live_px)
                df_h4: pd.DataFrame | None = asset_data.get("H4")

                if df_m15 is not None and len(df_m15) >= 25:
                    cur_price = float(df_m15["close"].iloc[-1])
                    strat_res = adaptive_router.evaluate_asset(
                        asset=asset,
                        df_m15=df_m15,
                        df_h4=df_h4,
                        timestamp=cur_ts,
                    )
                    side = strat_res.get("side", "none")
                    score = strat_res.get("score", 0.0)
                    atr = strat_res.get("atr", ref["atr"])
                    reason = strat_res.get("reason", "")
                    sl_mult = strat_res.get("sl_mult", 1.5)
                    be_r = strat_res.get("be_r", 1.0)
                    partial_r = strat_res.get("partial_r", 2.0)
                else:
                    side = "none"
                    score = 0.0
                    atr = ref["atr"]
                    cur_price = live_px if live_px else ref["price"]
                    reason = "waiting_for_m15_feed"
                    sl_mult = 1.5
                    be_r = 1.0
                    partial_r = 2.0

                if side == "none" or score < self.min_score_threshold:
                    continue

                signals[asset] = {
                    "score": score,
                    "side": side,
                    "price": cur_price,
                    "atr": atr,
                    "sl_mult": sl_mult,
                    "be_r": be_r,
                    "partial_r": partial_r,
                    "reason": f"AdaptiveM15({reason})",
                    "state_key": f"{asset}|{regime}|{reason}",
                    "rl_action": "execute_full",
                }
            return signals

        # 2. Live Trading Mode: Ingest Live MT4 Ground Truth + News/Macro Intelligence
        from strategies.strategy_allocator import strategy_allocator

        allocations = strategy_allocator.allocate_all()
        for asset, alloc in allocations.items():
            if alloc.get("status") == "MARKET_CLOSED":
                continue

            side = alloc.get("side", "none")
            score = float(alloc.get("score", 0.0))
            consensus = alloc.get("agent_consensus", {})
            all_agreed = consensus.get("all_agreed", False)

            # Execution Gate: All agents must discuss and agree, and score threshold gauge must be met
            if side == "none" or score < self.min_score_threshold or not all_agreed:
                continue

            signals[asset] = {
                "score": score,
                "side": side,
                "price": float(alloc.get("live_price", 0.0)),
                "atr": float(alloc.get("atr", 1.0)),
                "sl_mult": float(alloc.get("sl_mult", 1.5)),
                "be_r": float(alloc.get("be_r", 1.0)),
                "partial_r": float(alloc.get("partial_r", 2.0)),
                "strategy_name": alloc.get("strategy_name", "AdaptiveM15"),
                "reason": alloc.get("reasoning", ""),
                "state_key": f"{asset}|{regime}|{alloc.get('strategy_name')}|{alloc.get('reason')}",
                "rl_action": "execute_full",
                "consensus": consensus,
            }

        return signals

    def get_live_analysis(self) -> dict[str, Any]:
        """Return rich live score, indicators, and analysis commentary directly from StrategyAllocator."""
        from strategies.strategy_allocator import strategy_allocator

        return strategy_allocator.allocate_all()


# Global singleton instance for live inspection
adaptive_live_strategy = AdaptiveM15LiveStrategy()
