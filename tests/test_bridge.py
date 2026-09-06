import asyncio

import pytest

from execution.bridge.mock_ea import mock_ea_session
from execution.bridge.server import BridgeServer


@pytest.mark.asyncio
async def test_bridge_handshake_and_ping():
    server = BridgeServer(host="127.0.0.1", port=0)
    # Bind ephemeral port
    await server.start()
    assert server._server is not None
    socks = server._server.sockets
    assert socks
    port = socks[0].getsockname()[1]

    ea_task = asyncio.create_task(mock_ea_session("127.0.0.1", port))
    try:
        for _ in range(50):
            if server.connected:
                break
            await asyncio.sleep(0.05)
        assert server.connected
        assert server.ea_info.get("account") == 999001

        ping = await server.request("PING")
        assert ping.get("ok") is True
        assert ping.get("payload", {}).get("pong") is True

        account = await server.request("ACCOUNT")
        assert account.get("ok") is True
        assert account["payload"]["trade_mode"] == "Demo"

        order = await server.request(
            "OPEN",
            {"symbol": "EURUSD", "side": "buy", "volume": 0.01},
        )
        assert order.get("ok") is True
        assert order["payload"]["ticket"] == 123456
    finally:
        ea_task.cancel()
        await asyncio.gather(ea_task, return_exceptions=True)
        await server.stop()
