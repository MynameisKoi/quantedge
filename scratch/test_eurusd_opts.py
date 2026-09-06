"""Fast vectorized parameter testing for EURUSD on M15."""

import numpy as np
import pandas as pd
from backtest.engine import _load_or_generate_ohlc
from backtest.cfd_simulator import ExnessCFDSimulator

data = _load_or_generate_ohlc("EURUSD")
df = data["M15"].copy()

# Precompute indicators vectorially
close = df["close"]
high = df["high"]
low = df["low"]
open_ = df["open"]

tr1 = high - low
tr2 = (high - close.shift()).abs()
tr3 = (low - close.shift()).abs()
tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
atr_series = tr.rolling(14).mean().fillna(0.0010)

ema20 = close.ewm(span=20).mean()
ema50 = close.ewm(span=50).mean()
sma20 = close.rolling(20).mean()
std20 = close.rolling(20).std()
lower_bb = sma20 - (2.0 * std20)
upper_bb = sma20 + (2.0 * std20)

delta = close.diff()
gain = delta.clip(lower=0).rolling(14).mean()
loss = (-delta.clip(upper=0)).rolling(14).mean()
rs = gain / (loss + 1e-9)
rsi = 100 - (100 / (1 + rs))

# Precompute recent high/low
roll_h = high.shift(1).rolling(8).max()
roll_l = low.shift(1).rolling(8).min()

hours = df.index.hour
weekdays = df.index.weekday

def run_simulation(name, sig_series, sl_mult=1.2, be_r=1.0, tp_r=1.5, trail_mult=1.5):
    sim = ExnessCFDSimulator()
    equity = 10_000.0
    peak = equity
    max_dd = 0.0
    position = 0
    trades = 0
    wins = 0

    trade_units = 0.0
    entry_price = 0.0
    stop_dist = 0.0
    stop_price = 0.0
    best_fav = 0.0
    be_active = False
    part_taken = False

    for i in range(50, len(df)):
        cur_px = float(close.iloc[i])
        b_high = float(high.iloc[i])
        b_low = float(low.iloc[i])
        atr = float(atr_series.iloc[i])
        sig = sig_series[i]

        if position == 0 and sig in (1, -1):
            risk_budget = equity * 0.01
            stop_dist = max(sl_mult * atr, 0.0006)
            trade_units = risk_budget / stop_dist
            sig_side = "long" if sig == 1 else "short"
            fill = sim.simulate_fill("EURUSD", sig_side, cur_px)
            position = sig
            entry_price = fill.fill_price
            best_fav = entry_price
            stop_price = entry_price - stop_dist if position == 1 else entry_price + stop_dist
            be_active = False
            part_taken = False
            trades += 1

        elif position != 0:
            hit_exit = False
            if position == 1:
                best_fav = max(best_fav, b_high)
                fav_r = (b_high - entry_price) / max(stop_dist, 1e-6)
                if fav_r >= be_r and not be_active:
                    stop_price = entry_price + (0.1 * atr)
                    be_active = True
                if fav_r >= tp_r and not part_taken:
                    part_u = trade_units * 0.5
                    fill_p = sim.simulate_fill("EURUSD", "short", entry_price + (tp_r * stop_dist))
                    realized = (fill_p.fill_price - entry_price) * part_u - (fill_p.spread_cost * part_u)
                    equity += realized
                    trade_units -= part_u
                    part_taken = True
                    wins += 1
                if fav_r >= tp_r:
                    ch_stop = best_fav - (trail_mult * atr)
                    stop_price = max(stop_price, ch_stop)
                hit_exit = b_low <= stop_price
            else:
                best_fav = min(best_fav, b_low)
                fav_r = (entry_price - b_low) / max(stop_dist, 1e-6)
                if fav_r >= be_r and not be_active:
                    stop_price = entry_price - (0.1 * atr)
                    be_active = True
                if fav_r >= tp_r and not part_taken:
                    part_u = trade_units * 0.5
                    fill_p = sim.simulate_fill("EURUSD", "long", entry_price - (tp_r * stop_dist))
                    realized = (entry_price - fill_p.fill_price) * part_u - (fill_p.spread_cost * part_u)
                    equity += realized
                    trade_units -= part_u
                    part_taken = True
                    wins += 1
                if fav_r >= tp_r:
                    ch_stop = best_fav + (trail_mult * atr)
                    stop_price = min(stop_price, ch_stop)
                hit_exit = b_high >= stop_price

            if hit_exit:
                ex_side = "short" if position == 1 else "long"
                fill = sim.simulate_fill("EURUSD", ex_side, stop_price)
                pnl = (fill.fill_price - entry_price) * position * trade_units - (fill.spread_cost * trade_units)
                equity += pnl
                if pnl > 0 and not part_taken:
                    wins += 1
                position = 0
                peak = max(peak, equity)
                dd = (peak - equity) / peak * 100
                max_dd = max(max_dd, dd)

    net_pnl = equity - 10_000.0
    win_rate = (wins / max(trades, 1)) * 100.0
    print(f"{name:38s} | Trades={trades:3d} | WinRate={win_rate:5.1f}% | NetPnL=${net_pnl:8.2f} | MaxDD={max_dd:5.2f}%")


print("=" * 80)
print("FAST EURUSD M15 STRATEGY OPTIMIZATION TESTS")
print("=" * 80)

# Model A: London Open Breakout (08:00 - 12:00 UTC)
sig_a = np.zeros(len(df))
cond_long_a = (weekdays < 5) & (hours >= 8) & (hours < 12) & (close > roll_h) & (ema20 > ema50)
cond_short_a = (weekdays < 5) & (hours >= 8) & (hours < 12) & (close < roll_l) & (ema20 < ema50)
sig_a[cond_long_a] = 1
sig_a[cond_short_a] = -1
run_simulation("A. London Open Breakout (Trend)", sig_a, sl_mult=1.5, be_r=1.0, tp_r=2.0)

# Model B: London Reversal Pin-Bar (08:00 - 15:00 UTC)
bar_rng = (high - low).clip(lower=1e-6)
lower_wick = np.minimum(close, open_) - low
upper_wick = high - np.maximum(close, open_)
sig_b = np.zeros(len(df))
cond_long_b = (weekdays < 5) & (hours >= 8) & (hours < 15) & (low <= lower_bb) & (lower_wick / bar_rng > 0.55) & (rsi < 40)
cond_short_b = (weekdays < 5) & (hours >= 8) & (hours < 15) & (high >= upper_bb) & (upper_wick / bar_rng > 0.55) & (rsi > 60)
sig_b[cond_long_b] = 1
sig_b[cond_short_b] = -1
run_simulation("B. Pinbar Reversal Sweep (Reversion)", sig_b, sl_mult=1.0, be_r=0.8, tp_r=1.5)

# Model C: NY Session Reversal Fade (13:00 - 17:00 UTC)
sig_c = np.zeros(len(df))
cond_long_c = (weekdays < 5) & (hours >= 13) & (hours < 17) & (low <= lower_bb) & (close > lower_bb) & (rsi < 35)
cond_short_c = (weekdays < 5) & (hours >= 13) & (hours < 17) & (high >= upper_bb) & (close < upper_bb) & (rsi > 65)
sig_c[cond_long_c] = 1
sig_c[cond_short_c] = -1
run_simulation("C. NY Session Extreme Reversal", sig_c, sl_mult=1.0, be_r=0.7, tp_r=1.2)

# Model D: RSI Exhaustion + EMA Touch (London/NY 08:00 - 16:00)
sig_d = np.zeros(len(df))
cond_long_d = (weekdays < 5) & (hours >= 8) & (hours < 16) & (rsi < 28) & (close > open_)
cond_short_d = (weekdays < 5) & (hours >= 8) & (hours < 16) & (rsi > 72) & (close < open_)
sig_d[cond_long_d] = 1
sig_d[cond_short_d] = -1
run_simulation("D. RSI Deep Exhaustion (<28 / >72)", sig_d, sl_mult=1.0, be_r=0.6, tp_r=1.2)
