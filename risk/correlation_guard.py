"""Cross-asset exposure limiters."""

from __future__ import annotations

# Simplified buckets — correlated names share a heat budget.
CORRELATION_GROUPS: dict[str, str] = {
    "XAUUSD": "safe_haven",
    "XAUUSDm": "safe_haven",
    "USOIL": "energy",
    "USOILm": "energy",
    "BTCUSD": "risk_crypto",
    "BTCUSDm": "risk_crypto",
    "EURUSD": "fx_major",
    "EURUSDm": "fx_major",
}


def group_for(symbol: str) -> str:
    return CORRELATION_GROUPS.get(symbol, symbol)


def allows_new_exposure(symbol: str, open_symbols: list[str], max_per_group: int = 1) -> bool:
    group = group_for(symbol)
    same = sum(1 for s in open_symbols if group_for(s) == group)
    return same < max_per_group
