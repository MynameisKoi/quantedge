"""Mock MT5 EA client for offline bridge smoke tests."""

from __future__ import annotations

import asyncio
import json
from typing import Any


async def mock_ea_session(
    host: str,
    port: int,
    handle_open: bool = True,
) -> None:
    reader, writer = await asyncio.open_connection(host, port)
    hello = {
        "type": "hello",
        "payload": {
            "account": 999001,
            "server": "Exness-MT5Trial",
            "trade_mode": "Demo",
            "balance": 10000.0,
            "equity": 10000.0,
        },
    }
    writer.write((json.dumps(hello) + "\n").encode())
    await writer.drain()

    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            msg = json.loads(line.decode().strip())
            if msg.get("type") != "cmd":
                continue
            cmd_id = msg["id"]
            action = msg["action"]
            payload = msg.get("payload") or {}
            reply: dict[str, Any]
            if action == "PING":
                reply = {"type": "reply", "id": cmd_id, "ok": True, "payload": {"pong": True}}
            elif action == "ACCOUNT":
                reply = {
                    "type": "reply",
                    "id": cmd_id,
                    "ok": True,
                    "payload": {
                        "account": 999001,
                        "server": "Exness-MT5Trial",
                        "trade_mode": "Demo",
                        "balance": 10000.0,
                        "equity": 10000.0,
                        "currency": "USD",
                        "leverage": 500,
                    },
                }
            elif action == "POSITIONS":
                reply = {"type": "reply", "id": cmd_id, "ok": True, "payload": {"positions": []}}
            elif action == "OPEN" and handle_open:
                reply = {
                    "type": "reply",
                    "id": cmd_id,
                    "ok": True,
                    "payload": {
                        "ticket": 123456,
                        "price": 1.0851,
                        "volume": payload.get("volume", 0.01),
                        "symbol": payload.get("symbol", "EURUSD"),
                        "retcode": 10009,
                    },
                }
            elif action == "CLOSE_ALL":
                reply = {"type": "reply", "id": cmd_id, "ok": True, "payload": {"closed": 0}}
            else:
                reply = {
                    "type": "reply",
                    "id": cmd_id,
                    "ok": False,
                    "error": f"mock_unsupported:{action}",
                    "payload": {},
                }
            writer.write((json.dumps(reply) + "\n").encode())
            await writer.drain()
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
