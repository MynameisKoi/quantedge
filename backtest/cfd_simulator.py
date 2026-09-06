"""Exness-style variable spreads, slippage, and overnight swap model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FillResult:
    fill_price: float
    spread_cost: float
    slippage: float
    swap: float = 0.0


# Indicative Exness-like base spreads (price units)
BASE_SPREADS: dict[str, float] = {
    "XAUUSD": 0.25,
    "USOIL": 0.04,
    "BTCUSD": 35.0,
    "EURUSD": 0.00012,
}

# Overnight swap approx (fraction of notional per night)
SWAP_RATES: dict[str, dict[str, float]] = {
    "XAUUSD": {"long": -0.00012, "short": -0.00005},
    "USOIL": {"long": -0.00018, "short": 0.00002},
    "BTCUSD": {"long": -0.00045, "short": -0.0002},
    "EURUSD": {"long": -0.00004, "short": -0.00002},
}


class ExnessCFDSimulator:
    def __init__(self, news_multiplier: float = 1.0) -> None:
        self.news_multiplier = news_multiplier

    def spread(self, symbol: str) -> float:
        base = BASE_SPREADS.get(symbol, 0.01)
        return base * self.news_multiplier

    def simulate_fill(
        self,
        symbol: str,
        side: str,
        mid: float,
        slippage_bps: float = 0.5,
    ) -> FillResult:
        spr = self.spread(symbol)
        half = spr / 2.0
        slip = mid * (slippage_bps / 10_000.0) * self.news_multiplier
        if side == "long":
            fill = mid + half + slip
        else:
            fill = mid - half - slip
        return FillResult(fill_price=fill, spread_cost=spr, slippage=slip)

    def overnight_swap(self, symbol: str, side: str, notional: float, nights: int = 1) -> float:
        rates = SWAP_RATES.get(symbol, {"long": -0.0001, "short": -0.0001})
        rate = rates.get(side, -0.0001)
        return notional * rate * nights
