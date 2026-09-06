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


def atr_position_size(
    price: float,
    atr: float,
    asset: str = "XAUUSD",
    atr_stop_mult: float = 1.5,
    risk_pct: float | None = None,
    tp_r_mult: float = 2.0,
    be_r_mult: float = 1.0,
) -> dict[str, float]:
    """
    Size volume so that dollar loss at stop loss equals exactly risk_pct of current equity:
    Loss = Volume * StopDistance * ContractSize = RiskAmount
    Volume = RiskAmount / (StopDistance * ContractSize)
    Also computes dynamic Take Profit and Breakeven trigger prices.
    """
    equity = max(portfolio.equity, 100.0)
    risk_pct = risk_pct if risk_pct is not None else settings.risk_per_trade_pct
    risk_amount = equity * (risk_pct / 100.0)

    canon_asset = asset.upper().rstrip("M")
    stop_distance = max(atr * atr_stop_mult, price * 0.0005)
    contract_size = CONTRACT_SIZES.get(canon_asset, 1.0)

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
    }
