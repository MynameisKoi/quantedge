"""Exness MT4 symbol aliases (standard → broker Market Watch name)."""

from __future__ import annotations

# Exness MT4 demo commonly uses the "m" suffix.
EXNESS_MT4_MAP: dict[str, str] = {
    "EURUSD": "EURUSDm",
    "XAUUSD": "XAUUSDm",
    "BTCUSD": "BTCUSDm",
    "USOIL": "USOILm",
    "GBPUSD": "GBPUSDm",
    "USDJPY": "USDJPYm",
}


def to_broker_symbol(symbol: str) -> str:
    s = (symbol or "").strip()
    if not s:
        return s
    if s in EXNESS_MT4_MAP.values():
        return s
    return EXNESS_MT4_MAP.get(s, EXNESS_MT4_MAP.get(s.upper(), s))


def to_canonical_symbol(symbol: str) -> str:
    s = (symbol or "").strip()
    for canon, broker in EXNESS_MT4_MAP.items():
        if s == broker or s.upper() == broker.upper():
            return canon
    if s.endswith("m") and len(s) > 1:
        base = s[:-1]
        if base in EXNESS_MT4_MAP:
            return base
    return s
