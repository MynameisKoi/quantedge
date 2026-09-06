"""Vectorized / event-driven multi-timeframe backtester with RL trade learning."""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backtest.cfd_simulator import ExnessCFDSimulator
from core.rl.trade_learner import TradeRLPolicy
from core.rl.trade_memory import TradeExperience
from strategies.adaptive.router import adaptive_router
from strategies.mtf.hierarchical_engine import MultiTimeframeTracker

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("quantedge.backtest")


@dataclass
class BacktestResult:
    trades: int
    net_pnl: float
    win_rate_pct: float
    sharpe: float
    max_dd_pct: float
    rl_policy_summary: dict[str, Any] | None = None


def _load_or_generate_ohlc(asset: str, n_bars: int = 1000, start_price: float = 2350.0) -> dict[str, pd.DataFrame]:
    """Load MTF CSV files if available in data/historical/, else generate realistic multi-timeframe series."""
    hist_dir = Path("data/historical")
    candidates = [
        hist_dir / f"{asset}_M5.csv",
        hist_dir / f"{asset}_5M.csv",
        hist_dir / f"{asset}m_M5.csv",
        hist_dir / f"{asset}_M1.csv",
        hist_dir / f"{asset}_1M.csv",
        hist_dir / f"{asset}m_M1.csv",
        hist_dir / f"{asset}_H1.csv",
        hist_dir / f"{asset}_1H.csv",
        hist_dir / f"{asset}.csv",
    ]

    for csv_file in candidates:
        if csv_file.exists():
            try:
                # Read sample lines to determine header vs non-header MT4 format
                sample = csv_file.read_text(encoding="utf-8", errors="ignore")[:500]
                first_line = sample.splitlines()[0] if sample.splitlines() else ""

                if "<DATE>" in first_line.upper() or "<TIME>" in first_line.upper():
                    df = pd.read_csv(csv_file)
                    df.columns = [c.replace("<", "").replace(">", "").strip().lower() for c in df.columns]
                    df["datetime"] = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str))
                    df.set_index("datetime", inplace=True)
                elif first_line and first_line[0].isdigit() and ("." in first_line[:10] or "/" in first_line[:10]):
                    # Standard MT4 headerless export: YYYY.MM.DD,HH:MM,Open,High,Low,Close,Volume
                    cols = ["date", "time", "open", "high", "low", "close", "volume"]
                    df = pd.read_csv(csv_file, header=None, names=cols[: len(first_line.split(","))])
                    df["datetime"] = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str))
                    df.set_index("datetime", inplace=True)
                else:
                    df = pd.read_csv(csv_file, parse_dates=True, index_col=0)
                    df.columns = [c.lower() for c in df.columns]

                df = df[["open", "high", "low", "close"]].astype(float).sort_index()
                if hasattr(df.index, "tz") and df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
                df_m5 = df
                df_m15 = df_m5.resample("15min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
                df_m30 = df_m5.resample("30min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
                df_h1 = df_m5.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
                df_h4 = df_m5.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
                logger.info("Loaded %d historical bars for %s from %s", len(df_m5), asset, csv_file)
                return {"M5": df_m5, "M15": df_m15, "M30": df_m30, "H1": df_h1, "H4": df_h4}
            except Exception as e:
                logger.warning("Could not parse CSV %s (%s), trying next", csv_file, e)


    # Synthetic Multi-timeframe generation
    rng = np.random.default_rng(42)
    rets = rng.normal(0, 0.0015, n_bars)
    close = start_price * np.cumprod(1 + rets)
    high = close * (1 + rng.uniform(0, 0.0015, n_bars))
    low = close * (1 - rng.uniform(0, 0.0015, n_bars))
    open_ = np.roll(close, 1)
    open_[0] = start_price

    idx = pd.date_range("2024-01-01", periods=n_bars, freq="5min")
    df_m5 = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=idx)
    df_m15 = df_m5.resample("15min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    df_m30 = df_m5.resample("30min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    df_h1 = df_m5.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    df_h4 = df_m5.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()

    return {"M5": df_m5, "M15": df_m15, "M30": df_m30, "H1": df_h1, "H4": df_h4}


def run_backtest(
    strategy: str = "adaptive_portfolio",
    asset: str = "XAUUSD",
    from_date: str = "2024-01-01",
    enable_rl: bool = True,
    timeframe: str = "M15",
    explore: bool = True,
) -> BacktestResult:
    data = _load_or_generate_ohlc(asset)
    df_m5 = data["M5"]
    df_m15 = data["M15"]
    df_h4 = data["H4"]

    # Choose primary trading timeframe dynamically
    tf_key = timeframe.upper()
    df_primary = data.get(tf_key, df_m15)

    sim = ExnessCFDSimulator(news_multiplier=1.0)
    rl = TradeRLPolicy(learning_rate=0.15, exploration_rate=0.08)

    equity = 10_000.0
    peak = equity
    max_dd = 0.0
    position = 0  # 1 = long, -1 = short, 0 = flat
    trade_units = 0.0
    entry_price = 0.0
    stop_price = 0.0
    stop_dist = 0.0
    best_fav_price = 0.0
    breakeven_active = False
    partial_taken = False
    cur_sl_mult = 1.5
    cur_be_r = 1.0
    cur_partial_r = 2.0
    cur_trail_mult = 2.0
    active_exp: TradeExperience | None = None
    trades = 0
    wins = 0
    pnls: list[float] = []

    warmup = 50
    for i in range(warmup, len(df_primary)):
        window_primary = df_primary.iloc[: i + 1]
        cur_ts = window_primary.index[-1]
        if cur_ts < pd.Timestamp(from_date):
            continue

        bar_high = float(window_primary["high"].iloc[-1])
        bar_low = float(window_primary["low"].iloc[-1])
        cur_px = float(window_primary["close"].iloc[-1])

        window_m15 = df_m15[df_m15.index <= cur_ts]
        window_h4 = df_h4[df_h4.index <= cur_ts]
        window_m5 = df_m5[df_m5.index <= cur_ts]

        is_adaptive = "adaptive" in strategy.lower() or strategy.lower() in (
            "xauusd_trend",
            "eurusd_mean_revert",
            "usoil_vol_breakout",
        )

        if is_adaptive:
            strat_res = adaptive_router.evaluate_asset(
                asset=asset,
                df_m15=window_m15,
                df_h4=window_h4 if not window_h4.empty else window_m15,
                timestamp=cur_ts,
            )
            sig_side = strat_res.get("side", "none")
            sig_score = strat_res.get("score", 50.0)
            atr = max(strat_res.get("atr", 1.0), cur_px * 0.0005)
            trade_sl_mult = strat_res.get("sl_mult", 1.5)
            trade_be_r = strat_res.get("be_r", 1.0)
            trade_partial_r = strat_res.get("partial_r", 2.0)
            trade_trail_mult = strat_res.get("trail_mult", 2.0)

            rl_decision = rl.evaluate_setup(
                asset=asset,
                regime="risk-on",
                htf_trend=strat_res.get("reason", "setup"),
                mtf_setup="m15_adaptive",
                micro_trigger=sig_side,
                raw_score=sig_score,
                explore=(enable_rl and explore),
            )
            approved = rl_decision["approved"] if enable_rl else (sig_score >= 65.0)
        else:
            # Step 1: MTF State Evaluation
            mtf_state = MultiTimeframeTracker.synthesize_state(
                asset=asset,
                current_price=cur_px,
                df_h4=window_h4 if not window_h4.empty else window_m15,
                df_m15=window_m15,
                df_m5=window_primary,
                timestamp=cur_ts,
            )

            # Step 2: RL Policy Evaluation
            rl_decision = rl.evaluate_setup(
                asset=asset,
                regime="risk-on",
                htf_trend=mtf_state.htf_trend,
                mtf_setup=mtf_state.mtf_setup,
                micro_trigger=mtf_state.micro_trigger,
                raw_score=mtf_state.alignment_score,
                explore=(enable_rl and explore),
            )

            sig_side = mtf_state.suggested_side
            approved = rl_decision["approved"] if enable_rl else (mtf_state.alignment_score >= 65.0)
            atr = max(mtf_state.atr_m5, cur_px * 0.0005)
            trade_sl_mult = 1.5
            trade_be_r = 1.0
            trade_partial_r = 2.0
            trade_trail_mult = 2.0

        # Entry logic
        if position == 0 and approved and sig_side in ("long", "short"):
            cur_sl_mult = trade_sl_mult
            cur_be_r = trade_be_r
            cur_partial_r = trade_partial_r
            cur_trail_mult = trade_trail_mult

            risk_budget = equity * 0.01  # 1% risk per trade
            stop_dist = max(cur_sl_mult * atr, cur_px * 0.0005)
            size_mult = rl_decision.get("size_multiplier", 1.0) if enable_rl else 1.0
            trade_units = max((risk_budget / stop_dist) * size_mult, 0.0001)

            fill = sim.simulate_fill(asset, sig_side, cur_px)
            position = 1 if sig_side == "long" else -1
            entry_price = fill.fill_price
            best_fav_price = entry_price
            stop_price = entry_price - stop_dist if position == 1 else entry_price + stop_dist
            breakeven_active = False
            partial_taken = False

            trades += 1
            active_exp = TradeExperience(
                trade_id=f"bt_{trades}",
                asset=asset,
                strategy=strategy,
                state_key=rl_decision["state_key"],
                action=rl_decision["action"],
                side=sig_side,
                entry_price=entry_price,
                spread_cost=fill.spread_cost * trade_units,
            )

        # In-position management (breakeven lock, partial profit bank, Chandelier runner)
        elif position != 0 and active_exp is not None:
            hit_exit = False

            if position == 1:
                best_fav_price = max(best_fav_price, bar_high)
                favorable_r = (bar_high - entry_price) / max(stop_dist, 1e-6)

                # Lock breakeven at cur_be_r
                if favorable_r >= cur_be_r and not breakeven_active:
                    stop_price = entry_price + (0.2 * atr)
                    breakeven_active = True

                # Scale out 50% partial profit at cur_partial_r to bank risk budget
                if favorable_r >= cur_partial_r and not partial_taken:
                    partial_units = trade_units * 0.5
                    fill_part = sim.simulate_fill(asset, "short", entry_price + (cur_partial_r * stop_dist))
                    realized = (fill_part.fill_price - entry_price) * partial_units
                    equity += realized
                    trade_units -= partial_units
                    partial_taken = True
                    wins += 1

                # Dynamic Chandelier Trailing Stop on runner
                if favorable_r >= cur_partial_r:
                    chandelier_stop = best_fav_price - (cur_trail_mult * atr)
                    stop_price = max(stop_price, chandelier_stop)

                hit_exit = bar_low <= stop_price

            else:
                best_fav_price = min(best_fav_price, bar_low)
                favorable_r = (entry_price - bar_low) / max(stop_dist, 1e-6)

                # Lock breakeven at cur_be_r
                if favorable_r >= cur_be_r and not breakeven_active:
                    stop_price = entry_price - (0.2 * atr)
                    breakeven_active = True

                # Scale out 50% partial profit at cur_partial_r to bank risk budget
                if favorable_r >= cur_partial_r and not partial_taken:
                    partial_units = trade_units * 0.5
                    fill_part = sim.simulate_fill(asset, "long", entry_price - (cur_partial_r * stop_dist))
                    realized = (entry_price - fill_part.fill_price) * partial_units
                    equity += realized
                    trade_units -= partial_units
                    partial_taken = True
                    wins += 1

                # Dynamic Chandelier Trailing Stop on runner
                if favorable_r >= cur_partial_r:
                    chandelier_stop = best_fav_price + (cur_trail_mult * atr)
                    stop_price = min(stop_price, chandelier_stop)

                hit_exit = bar_high >= stop_price

            if hit_exit:
                exit_side = "short" if position == 1 else "long"
                fill = sim.simulate_fill(asset, exit_side, stop_price)
                pnl = (fill.fill_price - entry_price) * position * trade_units
                equity += pnl
                pnls.append(pnl)
                if pnl > 0 and not partial_taken:
                    wins += 1

                # RL Learning Feedback Loop
                if enable_rl:
                    active_exp.exit_price = fill.fill_price
                    active_exp.realized_pnl = pnl
                    active_exp.closed = True
                    active_exp.compute_reward(risk_amount=equity * 0.01)
                    rl.learn_from_trade(active_exp)

                position = 0
                active_exp = None
                peak = max(peak, equity)
                dd = (peak - equity) / peak * 100
                max_dd = max(max_dd, dd)

    rets = np.array(pnls) if pnls else np.array([0.0])
    std = float(rets.std(ddof=1)) if rets.size > 1 else 0.0
    sharpe = float(rets.mean() / std * np.sqrt(252 * 24)) if std > 0 else 0.0
    win_rate = round(wins / max(trades, 1) * 100, 2) if trades > 0 else 0.0

    result = BacktestResult(
        trades=trades,
        net_pnl=round(equity - 10_000.0, 2),
        win_rate_pct=win_rate,
        sharpe=round(sharpe, 3),
        max_dd_pct=round(max_dd, 3),
        rl_policy_summary=rl.get_policy_summary() if enable_rl else None,
    )

    logger.info(
        "Backtest Result [%s %s (%s)]: Trades=%d WinRate=%.1f%% NetPnL=$%.2f Sharpe=%.3f MaxDD=%.2f%%",
        strategy,
        asset,
        timeframe,
        result.trades,
        result.win_rate_pct,
        result.net_pnl,
        result.sharpe,
        result.max_dd_pct,
    )
    return result


def run_portfolio_backtest(
    strategy: str = "adaptive_portfolio",
    assets: list[str] | None = None,
    from_date: str = "2024-01-01",
    enable_rl: bool = True,
    timeframe: str = "M15",
    explore: bool = True,
) -> dict[str, BacktestResult]:
    """Run backtests across institutional CFD assets and summarize unified portfolio performance."""
    if assets is None:
        # Isolate BTCUSD to focus on prime CFD assets
        assets = ["XAUUSD", "EURUSD", "USOIL"]

    results = {}
    total_trades = 0
    total_wins = 0
    total_pnl = 0.0

    print("\n" + "=" * 70)
    print(f">> RUNNING INSTITUTIONAL ALPHA PORTFOLIO BACKTEST: {strategy.upper()} [{timeframe}]")
    print(f">> ASSETS: {', '.join(assets)}")
    print("=" * 70)

    for asset in assets:
        res = run_backtest(strategy, asset, from_date=from_date, enable_rl=enable_rl, timeframe=timeframe, explore=explore)
        results[asset] = res
        total_trades += res.trades
        total_wins += int(round(res.trades * (res.win_rate_pct / 100.0)))
        total_pnl += res.net_pnl

    agg_win_rate = round((total_wins / max(total_trades, 1) * 100), 2) if total_trades > 0 else 0.0
    print("\n" + "=" * 70)
    print(f"[PORTFOLIO SUMMARY] Total Trades={total_trades} | Agg WinRate={agg_win_rate}% | Combined Net PnL=${total_pnl:.2f}")
    print("=" * 70 + "\n")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="QuantEdge Institutional Alpha Engine Backtester")
    parser.add_argument("--strategy", default="adaptive_portfolio")
    parser.add_argument("--asset", default="all", help="Asset symbol (e.g. XAUUSD, EURUSD, USOIL) or 'all'")
    parser.add_argument("--timeframe", default="M15", choices=["M5", "M15", "M30", "H1", "H4"], help="Execution timeframe")
    parser.add_argument("--from", dest="from_date", default="2024-01-01")
    parser.add_argument("--no-rl", dest="disable_rl", action="store_true", help="Disable RL feedback")
    parser.add_argument("--exploit", action="store_true", help="Freeze RL policy in exploitation-only mode")
    args = parser.parse_args()

    explore_mode = not args.exploit
    if args.asset.lower() in ("all", "portfolio"):
        run_portfolio_backtest(
            args.strategy,
            from_date=args.from_date,
            enable_rl=not args.disable_rl,
            timeframe=args.timeframe,
            explore=explore_mode,
        )
    else:
        run_backtest(
            args.strategy,
            args.asset,
            args.from_date,
            enable_rl=not args.disable_rl,
            timeframe=args.timeframe,
            explore=explore_mode,
        )


if __name__ == "__main__":
    main()



