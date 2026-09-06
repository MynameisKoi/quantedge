"""Bridge facade — file (MT4) or TCP (MT5)."""

from __future__ import annotations

from typing import Any, Protocol

from config.settings import settings


class BridgeLike(Protocol):
    connected: bool
    ea_info: dict[str, Any]

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def request(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
        timeout: float = 8.0,
    ) -> dict[str, Any]: ...


_active: BridgeLike | None = None


def get_bridge() -> BridgeLike:
    global _active
    if _active is not None:
        return _active
    transport = (settings.bridge_transport or "file").lower()
    if transport == "tcp":
        from execution.bridge.server import bridge_server

        _active = bridge_server
    else:
        from execution.bridge.file_bridge import file_bridge

        _active = file_bridge
    return _active


async def ensure_bridge() -> BridgeLike:
    bridge = get_bridge()
    await bridge.start()
    return bridge
