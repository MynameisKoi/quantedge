import asyncio
import json
from pathlib import Path

import pytest

from execution.bridge.file_bridge import FileBridge


@pytest.mark.asyncio
async def test_file_bridge_handshake(tmp_path: Path):
    bridge = FileBridge(root=tmp_path)
    await bridge.start()

    hello = {
        "type": "hello",
        "payload": {
            "account": 42,
            "server": "Exness-Demo",
            "trade_mode": "Demo",
            "balance": 10000.0,
            "equity": 10000.0,
            "platform": "MT4",
        },
    }
    (tmp_path / "hello.json").write_text(json.dumps(hello), encoding="utf-8")
    (tmp_path / "heartbeat.json").write_text(
        json.dumps({"type": "heartbeat", "payload": hello["payload"]}),
        encoding="utf-8",
    )

    assert bridge.connected
    assert bridge.ea_info["account"] == 42

    async def ea_worker():
        # Simulate MT4 polling pending.json
        for _ in range(50):
            pending = tmp_path / "cmd" / "pending.json"
            if pending.exists():
                cmd = json.loads(pending.read_text(encoding="utf-8"))
                reply = {
                    "type": "reply",
                    "id": cmd["id"],
                    "ok": True,
                    "payload": {"pong": True, "platform": "MT4"},
                }
                (tmp_path / "reply" / f"{cmd['id']}.json").write_text(
                    json.dumps(reply), encoding="utf-8"
                )
                pending.unlink(missing_ok=True)
                return
            await asyncio.sleep(0.05)

    worker = asyncio.create_task(ea_worker())
    resp = await bridge.request("PING", timeout=3.0)
    await worker
    assert resp.get("ok") is True
    assert resp["payload"]["pong"] is True
    await bridge.stop()
