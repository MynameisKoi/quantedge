"""QuantEdge ↔ MT5 bridge message schema (newline-delimited JSON)."""

from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

Action = Literal[
    "PING",
    "ACCOUNT",
    "POSITIONS",
    "OPEN",
    "CLOSE",
    "CLOSE_ALL",
]


def new_id() -> str:
    return str(uuid4())


def command(action: Action, payload: dict[str, Any] | None = None, cmd_id: str | None = None) -> dict[str, Any]:
    return {
        "type": "cmd",
        "id": cmd_id or new_id(),
        "action": action,
        "payload": payload or {},
    }


def reply(cmd_id: str, ok: bool, payload: dict[str, Any] | None = None, error: str | None = None) -> dict[str, Any]:
    msg: dict[str, Any] = {"type": "reply", "id": cmd_id, "ok": ok, "payload": payload or {}}
    if error:
        msg["error"] = error
    return msg


def hello(account: int, server: str, trade_mode: str, balance: float, equity: float) -> dict[str, Any]:
    return {
        "type": "hello",
        "payload": {
            "account": account,
            "server": server,
            "trade_mode": trade_mode,
            "balance": balance,
            "equity": equity,
        },
    }
