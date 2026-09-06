"""Exness MT4/MT5 bridge adapter.

Historically named for ZeroMQ (DWX-style ports in .env). The production path is
a TCP JSON bridge: Python binds ZMQ_HOST:ZMQ_REQ_PORT and the MT5 EA connects in
(MQL5 cannot host ZeroMQ without a third-party DLL).
"""

from __future__ import annotations

import logging
from typing import Any

from config.settings import settings

logger = logging.getLogger(__name__)


class ZeroMQAdapter:
    """Facade over the TCP bridge server for order routing."""

    def __init__(self) -> None:
        self._connected = False

    def connect(self) -> bool:
        """Sync helper — prefer async ensure + request in callers."""
        if settings.enable_live_trading is False:
            logger.info("Bridge dry-run (ENABLE_LIVE_TRADING=false)")
            self._connected = False
            return False
        self._connected = True
        return True

    async def ensure_server(self):
        from execution.bridge.server import ensure_bridge_server

        return await ensure_bridge_server()

    async def request(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if settings.enable_live_trading is False and action in {"OPEN", "CLOSE", "CLOSE_ALL"}:
            return {"ok": True, "mode": "paper", "action": action, "payload": payload or {}}

        server = await self.ensure_server()
        if not server.connected:
            return {"ok": False, "error": "ea_not_connected", "hint": "Attach QuantEdgeBridge.mq4 on Exness MT4"}
        return await server.request(action, payload)

    def send_order(self, order: dict[str, Any]) -> dict[str, Any]:
        """Legacy sync entrypoint — schedules async request when a loop exists."""
        import asyncio

        action = str(order.get("action", "OPEN"))
        payload = {k: v for k, v in order.items() if k != "action"}

        if settings.enable_live_trading is False:
            return {"ok": True, "mode": "paper", "echo": order}

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.request(action, payload))

        # Called from async context incorrectly as sync — return deferred error guidance
        logger.warning("send_order() called from running loop; use await request() instead")
        fut = asyncio.ensure_future(self.request(action, payload))
        return {"ok": False, "error": "use_async_request", "future": fut}

    def close(self) -> None:
        self._connected = False
