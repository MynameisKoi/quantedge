import pandas as pd
from backtest.engine import run_backtest

timeframes = ["M5", "M15", "M30", "H1", "H4"]
assets = ["XAUUSD", "EURUSD", "USOIL"]

print("=" * 80)
print("TIMEFRAME SHOWDOWN: M5 vs M15 vs M30 vs H1 vs H4")
print("=" * 80)

results = []

for tf in timeframes:
    print(f"\n>>> TESTING TIMEFRAME: {tf} <<<")
    tf_trades = 0
    tf_wins = 0
    tf_pnl = 0.0
    for asset in assets:
        res = run_backtest("intraday_mtf_scalper", asset, timeframe=tf, enable_rl=True, explore=True)
        results.append({
            "Timeframe": tf,
            "Asset": asset,
            "Trades": res.trades,
            "WinRate": res.win_rate_pct,
            "NetPnL": res.net_pnl,
            "MaxDD": res.max_dd_pct,
            "Sharpe": res.sharpe,
        })
        tf_trades += res.trades
        tf_wins += int(round(res.trades * (res.win_rate_pct / 100.0)))
        tf_pnl += res.net_pnl

    agg_wr = (tf_wins / max(tf_trades, 1)) * 100
    print(f"[{tf} SUMMARY] Trades={tf_trades} WinRate={agg_wr:.1f}% Portfolio Net PnL=${tf_pnl:.2f}")

df_res = pd.DataFrame(results)
print("\n" + "=" * 80)
print("COMPLETE COMPARISON TABLE")
print("=" * 80)
print(df_res.to_string(index=False))
