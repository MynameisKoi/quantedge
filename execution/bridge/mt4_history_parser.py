"""MT4 execution log parser and ground truth metrics engine."""

from __future__ import annotations

import glob
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import settings

logger = logging.getLogger(__name__)

CONTRACT_SIZES: dict[str, float] = {
    "XAUUSD": 100.0,
    "USOIL": 1000.0,
    "EURUSD": 100000.0,
    "BTCUSD": 1.0,
}


class MT4HistoryParser:
    """Parses ground-truth trade executions from local MT4 terminal logs and bridge history."""

    def __init__(self, log_dir: str | None = None) -> None:
        self.log_dir = log_dir or self._discover_terminal_log_dir()

    def _discover_terminal_log_dir(self) -> str | None:
        """Dynamically locate the active MetaQuotes MT4 terminal logs directory."""
        # 1. Environment APPDATA
        appdata = os.environ.get("APPDATA")
        if appdata:
            base_pattern = os.path.join(appdata, "MetaQuotes", "Terminal", "*", "logs")
            matches = glob.glob(base_pattern)
            if matches:
                # Pick the folder with the most recent .log file
                scored = []
                for m in matches:
                    logs = glob.glob(os.path.join(m, "20*.log"))
                    if logs:
                        latest = max(os.path.getmtime(l) for l in logs)
                        scored.append((latest, m))
                if scored:
                    scored.sort(reverse=True)
                    return scored[0][1]

        # 2. Check relative to bridge directory
        if settings.bridge_dir:
            p = Path(settings.bridge_dir).resolve()
            # Bridge is usually in <terminal>/MQL4/Files/quantedge
            terminal_root = p.parent.parent.parent
            candidate = terminal_root / "logs"
            if candidate.exists():
                return str(candidate)

        return None

    def parse_closed_trades(self, days_back: int = 7) -> list[dict[str, Any]]:
        """Parse all closed trade executions from MT4 daily logs."""
        if not self.log_dir or not os.path.isdir(self.log_dir):
            return []

        log_files = sorted(glob.glob(os.path.join(self.log_dir, "20*.log")))
        if not log_files:
            return []

        target_files = log_files[-max(1, days_back):]

        close_pattern = re.compile(
            r"order\s+#(\d+)\s+(buy|sell)\s+([\d\.]+)\s+(\w+)\s+at\s+([\d\.]+)"
            r"(?:.*?(closed due stop-loss|closed due take-profit|closed))\s+at price\s+([\d\.]+)"
        )

        closed_trades: list[dict[str, Any]] = []

        for filepath in target_files:
            date_str = os.path.basename(filepath).replace(".log", "")
            try:
                with open(filepath, "r", encoding="latin-1") as fp:
                    for line in fp:
                        m = close_pattern.search(line)
                        if m:
                            ticket, side, lots, sym, op, reason, cp = m.groups()
                            canon = sym.rstrip("m").rstrip("M").upper()
                            csize = CONTRACT_SIZES.get(canon, 1.0)
                            op_f = float(op)
                            cp_f = float(cp)
                            lots_f = float(lots)

                            if side == "buy":
                                pnl = (cp_f - op_f) * lots_f * csize
                            else:
                                pnl = (op_f - cp_f) * lots_f * csize

                            time_part = line.split()[1] if len(line.split()) > 1 else "00:00:00"
                            iso_ts = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}T{time_part}Z"

                            close_tag = "stop_loss" if "stop-loss" in reason else (
                                "take_profit" if "take-profit" in reason else "market_close"
                            )

                            closed_trades.append({
                                "ticket": str(ticket),
                                "symbol": canon,
                                "side": side,
                                "lots": lots_f,
                                "open_price": op_f,
                                "close_price": cp_f,
                                "close_reason": close_tag,
                                "raw_reason": reason,
                                "pnl": round(pnl, 2),
                                "timestamp": iso_ts,
                                "date": date_str,
                            })
            except Exception as e:
                logger.warning("Error reading MT4 log file %s: %s", filepath, e)

        return closed_trades

    def compute_performance_metrics(self, trades: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Compute full institutional performance stats: Win Rate, Net PnL, Profit Factor, Max Drawdown."""
        if trades is None:
            trades = self.parse_closed_trades(days_back=14)

        if not trades:
            return {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "scratches": 0,
                "win_rate_pct": 0.0,
                "net_pnl": 0.0,
                "gross_profit": 0.0,
                "gross_loss": 0.0,
                "profit_factor": 0.0,
                "max_drawdown_pct": 0.0,
                "max_drawdown_usd": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "win_loss_ratio": 0.0,
                "asset_breakdown": {},
                "trades": [],
            }

        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] < 0]
        scratches = [t for t in trades if t["pnl"] == 0]

        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))
        net_pnl = gross_profit - gross_loss

        total_count = len(trades)
        win_rate_pct = round((len(wins) / total_count * 100.0), 1) if total_count > 0 else 0.0
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        avg_win = round(gross_profit / len(wins), 2) if wins else 0.0
        avg_loss = round(gross_loss / len(losses), 2) if losses else 0.0
        wl_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0

        # Calculate high water mark equity curve and maximum drawdown
        cum_pnl = 0.0
        hwm = 0.0
        max_dd_usd = 0.0
        for t in trades:
            cum_pnl += t["pnl"]
            if cum_pnl > hwm:
                hwm = cum_pnl
            dd = hwm - cum_pnl
            if dd > max_dd_usd:
                max_dd_usd = dd

        # Approximate drawdown percentage based on baseline equity (~$2,000)
        baseline_equity = max(2000.0, 2000.0 + hwm)
        max_dd_pct = round((max_dd_usd / baseline_equity * 100.0), 2)

        # Asset Breakdown
        breakdown: dict[str, dict[str, Any]] = {}
        for sym in ("XAUUSD", "BTCUSD", "USOIL", "EURUSD"):
            sym_trades = [t for t in trades if t["symbol"] == sym]
            if sym_trades:
                s_wins = [t for t in sym_trades if t["pnl"] > 0]
                s_losses = [t for t in sym_trades if t["pnl"] < 0]
                s_pnl = sum(t["pnl"] for t in sym_trades)
                breakdown[sym] = {
                    "trades": len(sym_trades),
                    "wins": len(s_wins),
                    "losses": len(s_losses),
                    "win_rate_pct": round(len(s_wins) / len(sym_trades) * 100.0, 1),
                    "net_pnl": round(s_pnl, 2),
                }

        return {
            "total_trades": total_count,
            "wins": len(wins),
            "losses": len(losses),
            "scratches": len(scratches),
            "win_rate_pct": win_rate_pct,
            "net_pnl": round(net_pnl, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "profit_factor": profit_factor,
            "max_drawdown_pct": max_dd_pct,
            "max_drawdown_usd": round(max_dd_usd, 2),
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "win_loss_ratio": wl_ratio,
            "asset_breakdown": breakdown,
            "trades": trades,
        }


mt4_history_parser = MT4HistoryParser()
