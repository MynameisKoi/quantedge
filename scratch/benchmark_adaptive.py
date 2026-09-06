"""Benchmark and compare separate adaptive strategies for XAUUSD, EURUSD, and USOIL on M15."""

import pandas as pd
from backtest.engine import run_backtest, run_portfolio_backtest

assets = ["XAUUSD", "EURUSD", "USOIL"]

print("=" * 80)
print("BENCHMARKING ADAPTIVE SEPARATE STRATEGIES ON M15")
print("=" * 80)

# 1. Run each asset with the Adaptive Router
results = []
for asset in assets:
    print(f"\n>> TESTING ADAPTIVE STRATEGY FOR {asset} (M15)...")
    res = run_backtest(
        strategy="adaptive_portfolio",
        asset=asset,
        timeframe="M15",
        enable_rl=True,
        explore=False,  # Exploitation mode to test pure edge
    )
    results.append({
        "Asset": asset,
        "Strategy": "Adaptive M15",
        "Trades": res.trades,
        "WinRate %": res.win_rate_pct,
        "Net PnL $": res.net_pnl,
        "Max DD %": res.max_dd_pct,
        "Sharpe": res.sharpe,
    })

# Also run the full portfolio
print("\n" + "=" * 80)
print("RUNNING COMBINED ADAPTIVE PORTFOLIO (M15)")
print("=" * 80)
port_results = run_portfolio_backtest(
    strategy="adaptive_portfolio",
    timeframe="M15",
    enable_rl=True,
    explore=False,
)

df = pd.DataFrame(results)
print("\n" + "=" * 80)
print("ADAPTIVE STRATEGY RESULTS TABLE")
print("=" * 80)
print(df.to_string(index=False))
