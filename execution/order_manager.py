"""Order lifecycle management."""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from config.settings import settings
from core.portfolio import Position, portfolio
from execution.bridge.facade import get_bridge
from execution.bridge.symbols import to_broker_symbol

logger = logging.getLogger(__name__)


class OrderManager:
    def __init__(self) -> None:
        self.bridge = get_bridge()

    async def submit(self, decision: dict[str, Any]) -> dict[str, Any]:
        if not decision.get("approved"):
            return {"status": "rejected", "reason": decision.get("reason")}

        client_id = str(uuid4())
        side = decision["side"]
        broker_symbol = to_broker_symbol(decision["asset"])
        order = {
            "action": "OPEN",
            "symbol": broker_symbol,
            "side": side,
            "volume": float(decision["volume"]),
            "sl": decision.get("stop_loss"),
            "tp": decision.get("take_profit"),
            "account": settings.exness_account_type,
            "client_id": client_id,
        }

        if settings.enable_live_trading:
            result = await self.bridge.request(
                "OPEN",
                {
                    "symbol": order["symbol"],
                    "side": order["side"],
                    "volume": order["volume"],
                    "sl": order["sl"],
                    "tp": order["tp"],
                    "client_id": client_id,
                },
            )
        else:
            result = {"ok": True, "mode": "paper", "echo": order}

        ok = bool(result.get("ok", False)) or result.get("mode") == "paper"
        if not ok:
            logger.error("Order rejected by bridge: %s", result)
            return {"status": "bridge_error", "order": order, "bridge": result}

        payload = result.get("payload") or {}
        ticket = payload.get("ticket") or result.get("ticket") or client_id
        fill_price = float(payload.get("price") or decision["price"])

        portfolio.open_position(
            Position(
                symbol=decision["asset"],
                side=side,
                volume=float(decision["volume"]),
                entry_price=fill_price,
                stop_loss=decision.get("stop_loss"),
                take_profit=decision.get("take_profit"),
                ticket=str(ticket),
            )
        )
        logger.info("Order submitted: %s → %s", order, result)
        return {"status": "submitted", "order": order, "bridge": result}

    async def close_ticket(self, ticket: int | str) -> dict[str, Any]:
        """Close a specific open order ticket in MT4."""
        ticket_int = int(ticket) if str(ticket).isdigit() else 0
        bridge_result: dict[str, Any] = {"ok": True, "mode": "paper"}
        if settings.enable_live_trading and ticket_int > 0:
            bridge_result = await self.bridge.request("CLOSE", {"ticket": ticket_int})
            if not bridge_result.get("ok"):
                logger.error("Failed closing ticket #%s in MT4: %s", ticket, bridge_result)
                return {
                    "ok": False,
                    "ticket": ticket,
                    "error": bridge_result.get("error", "close_failed"),
                    "bridge": bridge_result,
                }

        # Remove from in-memory portfolio positions
        matching_key = None
        for key, pos in list(portfolio.positions.items()):
            if str(pos.ticket) == str(ticket):
                matching_key = key
                break
        if matching_key:
            portfolio.positions.pop(matching_key, None)
            portfolio.update_equity()

        logger.info("Successfully closed ticket #%s in MT4: %s", ticket, bridge_result)
        return {"ok": True, "ticket": ticket, "status": "closed", "bridge": bridge_result}

    async def emergency_flat(self) -> dict[str, Any]:
        portfolio.emergency_stopped = True
        bridge_result: dict[str, Any] = {"ok": True, "mode": "paper"}
        if settings.enable_live_trading:
            bridge_result = await self.bridge.request("CLOSE_ALL", {})
        closed = portfolio.close_all()
        return {"closed": closed, "emergency_stopped": True, "bridge": bridge_result}
