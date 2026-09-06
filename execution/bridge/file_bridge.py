"""File-based bridge for Exness MT4 (no Socket* API / no DLL).

Layout under MetaQuotes Common\\Files\\quantedge\\:
  hello.json              — EA presence / account snapshot
  heartbeat.json          — refreshed every few seconds
  cmd/<id>.json           — Python → EA command
  reply/<id>.json         — EA → Python reply
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from execution.bridge.paths import default_bridge_dir
from execution.bridge.protocol import command

logger = logging.getLogger(__name__)


class FileBridge:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_bridge_dir()
        self.cmd_dir = self.root / "cmd"
        self.reply_dir = self.root / "reply"
        self._started = False
        self._lock = asyncio.Lock()

    def _ensure_dirs(self) -> None:
        self.cmd_dir.mkdir(parents=True, exist_ok=True)
        self.reply_dir.mkdir(parents=True, exist_ok=True)

    async def start(self) -> None:
        self._ensure_dirs()
        self._started = True
        logger.info("File bridge ready at %s (MT4 EA uses FILE_COMMON\\\\quantedge)", self.root)

    async def stop(self) -> None:
        self._started = False

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            raw = path.read_text(encoding="utf-8").strip()
            if not raw:
                return None
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    @property
    def connected(self) -> bool:
        """EA is considered online if heartbeat/hello is fresh (< 8s)."""
        for name in ("heartbeat.json", "hello.json"):
            path = self.root / name
            if not path.exists():
                continue
            age = time.time() - path.stat().st_mtime
            if age <= 8.0:
                return True
        return False

    @property
    def ea_info(self) -> dict[str, Any]:
        for name in ("heartbeat.json", "hello.json"):
            data = self._read_json(self.root / name)
            if not data:
                continue
            if data.get("type") in {"hello", "heartbeat"}:
                return dict(data.get("payload") or {})
            return dict(data)
    def get_history(self) -> list[dict[str, Any]]:
        """Read closed trades history exported by MT4 EA."""
        path = self.root / "history.json"
        data = self._read_json(path)
        if data and isinstance(data.get("trades"), list):
            return data["trades"]
        return []

    async def request(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
        timeout: float = 12.0,
    ) -> dict[str, Any]:
        if not self._started:
            await self.start()
        if not self.connected:
            return {
                "ok": False,
                "error": "ea_not_connected",
                "hint": "Attach QuantEdgeBridge.mq4 and wait for heartbeat.json",
                "path": str(self.root),
            }

        cmd = command(action, payload)  # type: ignore[arg-type]
        cmd_id = cmd["id"]
        cmd_path = self.cmd_dir / f"{cmd_id}.json"
        pending_path = self.cmd_dir / "pending.json"
        reply_path = self.reply_dir / f"{cmd_id}.json"

        body = json.dumps(cmd, separators=(",", ":"))

        async with self._lock:
            if reply_path.exists():
                reply_path.unlink(missing_ok=True)
            cmd_path.write_text(body, encoding="utf-8")
            # MT4 polls this single file (no directory listing APIs needed).
            pending_path.write_text(body, encoding="utf-8")

        deadline = time.monotonic() + timeout
        try:
            while time.monotonic() < deadline:
                reply = self._read_json(reply_path)
                if reply is not None:
                    try:
                        reply_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                    return reply
                await asyncio.sleep(0.1)
            return {"ok": False, "error": "timeout", "id": cmd_id}
        finally:
            for p in (cmd_path, pending_path):
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass


file_bridge = FileBridge()
