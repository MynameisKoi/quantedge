"""ATR-based institutional position sizing with contract size normalization."""

from __future__ import annotations

from config.settings import settings
from core.portfolio import portfolio

# Standard Exness CFD Contract Sizes
CONTRACT_SIZES: dict[str, float] = {
    "XAUUSD": 100.0,      # 1 lot = 100 troy oz
    "USOIL": 1000.0,      # 1 lot = 1,000 barrels
    "EURUSD": 100000.0,   # 1 lot = 100,000 EUR
    "BTCUSD": 1.0,        # 1 lot = 1 BTC
}

# Institutional Hard Minimum Stop Loss Floors (Noise Filters to eliminate premature stopouts)
MINIMUM_STOP_FLOORS: dict[str, float] = {
    "BTCUSD": 850.0,      # $850 floor (~1.1% on BTC)
    "XAUUSD": 20.0,       # $20.00 floor (~0.45% on Gold to absorb news/session wicks)
    "USOIL": 1.10,        # $1.10 floor (~1.2% on Crude Oil)
    "EURUSD": 0.0018,     # 18 pips floor on EURUSD
}


def atr_position_size(
    price: float,
    atr: float,
    asset: str = "XAUUSD",
    atr_stop_mult: float = 2.5,
    risk_pct: float | None = None,
    tp_r_mult: float = 2.0,
    be_r_mult: float = 1.5,
    structural_stop_price: float | None = None,
    structural_stop_distance: float | None = None,
) -> dict[str, float]:
    """
    Size volume so that dollar loss at stop loss equals exactly risk_pct of current equity:
    Loss = Volume * StopDistance * ContractSize = RiskAmount
    Volume = RiskAmount / (StopDistance * ContractSize)
    
    Protects against Volatility Compression Suffocation by enforcing:
    1. Institutional minimum stop floors per asset class.
    2. Structural swing high/low anchoring outside liquidity hunt pools.
    3. Inverse volume scaling: widening stop distance proportionally reduces lot size,
       keeping account dollar risk capped at exactly 1%.
    """
    equity = max(portfolio.equity, 100.0)
    risk_pct = risk_pct if risk_pct is not None else settings.risk_per_trade_pct
    risk_amount = equity * (risk_pct / 100.0)

    canon_asset = asset.upper().rstrip("M")
    contract_size = CONTRACT_SIZES.get(canon_asset, 1.0)

    # 1. Base ATR Stop Distance
    atr_dist = atr * atr_stop_mult

    # 2. Institutional Minimum Noise Floor
    min_floor = MINIMUM_STOP_FLOORS.get(canon_asset, price * 0.005)

    # 3. Structural Anchor Distance
    struct_dist = 0.0
    if structural_stop_distance is not None and structural_stop_distance > 0:
        struct_dist = structural_stop_distance
    elif structural_stop_price is not None and structural_stop_price > 0:
        struct_dist = abs(price - structural_stop_price)

    # Stop distance is the maximum of all three: guarantees trade breathing room
    stop_distance = max(atr_dist, min_floor, struct_dist)

    raw_volume = risk_amount / (stop_distance * contract_size)
    # Exness minimum lot is 0.01, step 0.01
    volume = max(0.01, round(raw_volume, 2))

    digits = 4 if "EUR" in canon_asset else 2
    return {
        "volume": volume,
        "stop_distance": round(stop_distance, digits),
        "risk_amount": round(risk_amount, 2),
        "stop_loss_long": round(price - stop_distance, digits),
        "stop_loss_short": round(price + stop_distance, digits),
        "take_profit_long": round(price + (tp_r_mult * stop_distance), digits),
        "take_profit_short": round(price - (tp_r_mult * stop_distance), digits),
        "breakeven_long": round(price + (be_r_mult * stop_distance), digits),
        "breakeven_short": round(price - (be_r_mult * stop_distance), digits),
        "atr_distance": round(atr_dist, digits),
        "min_floor": round(min_floor, digits),
        "structural_distance": round(struct_dist, digits),
    }
