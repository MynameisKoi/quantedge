"""Core risk gate — deterministic 1% rule; LLMs never size trades."""

from __future__ import annotations

from typing import Any

from config.settings import settings
from core.portfolio import portfolio
from risk.correlation_guard import allows_new_exposure
from risk.position_sizer import atr_position_size


class RiskManager:
    def evaluate(
        self,
        asset: str,
        side: str,
        score: float,
        atr: float,
        price: float,
        sl_mult: float = 1.5,
        be_r: float = 1.0,
        partial_r: float = 2.0,
    ) -> dict[str, Any]:
        if portfolio.emergency_stopped:
            return self._reject("emergency_stop")

        if portfolio.drawdown_pct >= settings.max_daily_drawdown_pct:
            return self._reject("max_daily_drawdown")

        if portfolio.open_heat_pct >= settings.max_portfolio_heat_pct:
            return self._reject("max_portfolio_heat")

        open_symbols = [p.symbol.upper().rstrip("M") for p in portfolio.positions.values()]
        if asset.upper().rstrip("M") in open_symbols:
            return self._reject(f"already_holding_{asset}")

        if not allows_new_exposure(asset, open_symbols):
            return self._reject("correlation_guard")

        sizing = atr_position_size(
            price=price,
            atr=atr,
            asset=asset,
            atr_stop_mult=sl_mult,
            tp_r_mult=partial_r,
            be_r_mult=be_r,
        )
        stop = sizing["stop_loss_long"] if side == "long" else sizing["stop_loss_short"]
        tp = sizing["take_profit_long"] if side == "long" else sizing["take_profit_short"]
        be = sizing["breakeven_long"] if side == "long" else sizing["breakeven_short"]

        return {
            "approved": True,
            "asset": asset,
            "side": side,
            "score": score,
            "price": price,
            "volume": sizing["volume"],
            "stop_loss": stop,
            "take_profit": tp,
            "breakeven_trigger": be,
            "risk_amount": sizing["risk_amount"],
            "stop_distance": sizing["stop_distance"],
            "reason": "passed_risk_gates",
        }

    @staticmethod
    def _reject(reason: str) -> dict[str, Any]:
        return {"approved": False, "reason": reason}
