"""TCP bridge server — MT5 EA connects in (MQL5 is socket-client only).

Uses the same host/port as ZMQ_HOST / ZMQ_REQ_PORT in .env so the README
wiring stays unchanged. Messages are newline-delimited JSON.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from config.settings import settings
from execution.bridge.protocol import command

logger = logging.getLogger(__name__)


class BridgeServer:
    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self.host = host or settings.zmq_host
        self.port = port or settings.zmq_req_port
        self._server: asyncio.AbstractServer | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._ea_info: dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._read_task: asyncio.Task | None = None

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    @property
    def ea_info(self) -> dict[str, Any]:
        return dict(self._ea_info)

    async def start(self) -> None:
        if self._server is not None:
            return
        self._server = await asyncio.start_server(self._on_connect, self.host, self.port)
        sockets = self._server.sockets or []
        where = ", ".join(str(s.getsockname()) for s in sockets) or f"{self.host}:{self.port}"
        logger.info("Bridge server listening on %s (MT5 EA should connect here)", where)

    async def stop(self) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ConnectionError("bridge stopped"))
        self._pending.clear()
        if self._read_task:
            self._read_task.cancel()
            await asyncio.gather(self._read_task, return_exceptions=True)
            self._read_task = None
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _on_connect(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        logger.info("MT5 EA connected from %s", peer)
        # Single EA session — drop previous if any
        if self._writer is not None:
            logger.warning("Replacing previous EA connection")
            self._writer.close()
        self._reader = reader
        self._writer = writer
        self._read_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        assert self._reader is not None
        try:
            while True:
                line = await self._reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode("utf-8").strip())
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from EA: %r", line[:200])
                    continue
                await self._handle_message(msg)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("EA read loop failed")
        finally:
            logger.info("MT5 EA disconnected")
            self._writer = None
            self._reader = None
            self._ea_info = {}
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(ConnectionError("EA disconnected"))
            self._pending.clear()

    async def _handle_message(self, msg: dict[str, Any]) -> None:
        mtype = msg.get("type")
        if mtype == "hello":
            self._ea_info = dict(msg.get("payload") or {})
            logger.info("EA hello: %s", self._ea_info)
            return
        if mtype == "heartbeat":
            payload = msg.get("payload") or {}
            self._ea_info.update(payload)
            return
        if mtype == "reply":
            cmd_id = str(msg.get("id", ""))
            fut = self._pending.pop(cmd_id, None)
            if fut and not fut.done():
                fut.set_result(msg)
            return
        if mtype == "event":
            logger.info("EA event: %s", msg)
            return
        logger.debug("Unhandled EA message: %s", msg)

    async def request(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
        timeout: float = 8.0,
    ) -> dict[str, Any]:
        if not self.connected or self._writer is None:
            return {"ok": False, "error": "ea_not_connected"}

        cmd = command(action, payload)  # type: ignore[arg-type]
        cmd_id = cmd["id"]
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[cmd_id] = fut

        async with self._lock:
            data = (json.dumps(cmd, separators=(",", ":")) + "\n").encode("utf-8")
            self._writer.write(data)
            await self._writer.drain()

        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except TimeoutError:
            self._pending.pop(cmd_id, None)
            return {"ok": False, "error": "timeout", "id": cmd_id}
        except Exception as exc:
            self._pending.pop(cmd_id, None)
            return {"ok": False, "error": str(exc), "id": cmd_id}


# Process-wide server used by CLI / order manager / engine.
bridge_server = BridgeServer()


async def ensure_bridge_server() -> BridgeServer:
    await bridge_server.start()
    return bridge_server
