"""Portfolio state management."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class Position:
    symbol: str
    side: str  # long | short
    volume: float
    entry_price: float
    stop_loss: float | None = None
    take_profit: float | None = None
    unrealized_pnl: float = 0.0
    opened_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ticket: str | None = None

    def mark(self, price: float, contract_size: float = 1.0) -> None:
        direction = 1.0 if self.side == "long" else -1.0
        self.unrealized_pnl = (price - self.entry_price) * self.volume * contract_size * direction


@dataclass
class Portfolio:
    balance: float = 10_000.0
    equity: float = 10_000.0
    peak_equity: float = 10_000.0
    daily_pnl: float = 0.0
    currency: str = "USD"
    positions: dict[str, Position] = field(default_factory=dict)
    closed_pnl: float = 0.0
    emergency_stopped: bool = False
    daily_starting_equity: float = 0.0
    daily_date_str: str = ""

    def update_equity(self) -> None:
        unrealized = sum(p.unrealized_pnl for p in self.positions.values())
        self.equity = self.balance + unrealized
        self.peak_equity = max(self.peak_equity, self.equity)

    def sync_mt4(self, balance: float, equity: float) -> None:
        """Synchronize live MT4 balance and equity, calibrating peak_equity and daily starting equity."""
        self.balance = balance
        self.equity = equity

        # Track and reset daily starting baseline each UTC day
        today_str = datetime.now(UTC).strftime("%Y-%m-%d")
        if self.daily_date_str != today_str or self.daily_starting_equity <= 0.0:
            self.daily_date_str = today_str
            self.daily_starting_equity = max(balance, equity)

        # Calibrate lifetime peak equity
        if self.peak_equity <= 0.0 or (self.peak_equity == 10_000.0 and balance < 5_000.0):
            self.peak_equity = max(balance, equity)
        else:
            self.peak_equity = max(self.peak_equity, equity)

    @property
    def drawdown_pct(self) -> float:
        """Daily drawdown percentage measured against today's starting equity."""
        base = self.daily_starting_equity if self.daily_starting_equity > 0 else self.peak_equity
        if base <= 0:
            return 0.0
        return max(0.0, (base - self.equity) / base * 100.0)

    @property
    def open_heat_pct(self) -> float:
        """Rough portfolio heat: sum of risked notionals vs equity."""
        if self.equity <= 0:
            return 0.0
        risked = 0.0
        for pos in self.positions.values():
            if pos.stop_loss is None:
                continue
            risked += abs(pos.entry_price - pos.stop_loss) * pos.volume
        return (risked / self.equity) * 100.0

    def open_position(self, position: Position) -> None:
        key = f"{position.symbol}:{position.side}"
        self.positions[key] = position
        self.update_equity()

    def close_position(self, key: str, exit_price: float, contract_size: float = 1.0) -> float:
        pos = self.positions.pop(key, None)
        if pos is None:
            return 0.0
        direction = 1.0 if pos.side == "long" else -1.0
        pnl = (exit_price - pos.entry_price) * pos.volume * contract_size * direction
        self.balance += pnl
        self.closed_pnl += pnl
        self.daily_pnl += pnl
        self.update_equity()
        return pnl

    def close_all(self, marks: dict[str, float] | None = None) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for key in list(self.positions.keys()):
            pos = self.positions[key]
            price = (marks or {}).get(pos.symbol, pos.entry_price)
            pnl = self.close_position(key, price)
            results.append({"key": key, "symbol": pos.symbol, "pnl": pnl})
        return results

    def summary(self) -> dict[str, Any]:
        self.update_equity()
        return {
            "balance": round(self.balance, 2),
            "equity": round(self.equity, 2),
            "currency": self.currency,
            "daily_pnl": round(self.daily_pnl, 2),
            "closed_pnl": round(self.closed_pnl, 2),
            "drawdown_pct": round(self.drawdown_pct, 3),
            "portfolio_heat_pct": round(self.open_heat_pct, 3),
            "open_positions": len(self.positions),
            "emergency_stopped": self.emergency_stopped,
        }


# Shared in-memory portfolio for API / paper engine.
portfolio = Portfolio()
