"""CLI: handshake, positions, open/close against Exness MT4 EA (file bridge).

Examples:
  python -m execution.bridge_test --wait --ping --account
  python -m execution.bridge_test --wait --positions
  python -m execution.bridge_test --wait --order --symbol BTCUSD --volume 0.01 --i-understand-demo
  python -m execution.bridge_test --wait --close --ticket 198453070 --i-understand-demo
  python -m execution.bridge_test --wait --close-all --i-understand-demo
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from config.settings import settings
from execution.bridge.facade import ensure_bridge
from execution.bridge.paths import default_bridge_dir
from execution.bridge.symbols import to_broker_symbol

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("quantedge.bridge_test")


async def wait_for_ea(timeout: float = 120.0) -> bool:
    bridge = await ensure_bridge()
    logger.info(
        "Waiting for QuantEdgeBridge.mq4 via %s transport (timeout %.0fs)…",
        settings.bridge_transport,
        timeout,
    )
    logger.info("File path: %s", default_bridge_dir())
    elapsed = 0.0
    while elapsed < timeout:
        if bridge.connected:
            logger.info("EA connected: %s", bridge.ea_info)
            return True
        await asyncio.sleep(0.5)
        elapsed += 0.5
    logger.error("Timed out waiting for EA heartbeat/hello")
    return False


def _require_demo_confirm(args: argparse.Namespace) -> int | None:
    if not args.i_understand_demo:
        logger.error("Refusing trade action without --i-understand-demo")
        return 2
    if settings.exness_account_type.lower() != "demo":
        logger.error("EXNESS_ACCOUNT_TYPE must be Demo")
        return 2
    return None


async def run(args: argparse.Namespace) -> int:
    bridge = await ensure_bridge()

    if args.wait or not bridge.connected:
        ok = await wait_for_ea(timeout=args.timeout)
        if not ok:
            return 1

    any_action = args.ping or args.account or args.positions or args.order or args.close or args.close_all
    if not any_action:
        args.ping = True

    if args.ping:
        resp = await bridge.request("PING", {})
        print("PING:", resp)
        if not resp.get("ok"):
            return 1

    if args.account:
        resp = await bridge.request("ACCOUNT", {})
        print("ACCOUNT:", resp)
        if not resp.get("ok"):
            return 1

    if args.positions:
        resp = await bridge.request("POSITIONS", {})
        print("POSITIONS:", resp)
        if not resp.get("ok"):
            return 1

    if args.order:
        err = _require_demo_confirm(args)
        if err is not None:
            return err
        if args.volume > 0.02:
            logger.error("bridge_test caps volume at 0.02 lots for safety")
            return 2
        symbol = to_broker_symbol(args.symbol)
        resp = await bridge.request(
            "OPEN",
            {
                "symbol": symbol,
                "side": args.side,
                "volume": args.volume,
                "sl": args.sl,
                "tp": args.tp,
                "client_id": "bridge_test",
            },
        )
        print("ORDER:", resp)
        if not resp.get("ok"):
            return 1

    if args.close:
        err = _require_demo_confirm(args)
        if err is not None:
            return err
        if not args.ticket:
            logger.error("--close requires --ticket")
            return 2
        resp = await bridge.request("CLOSE", {"ticket": int(args.ticket)})
        print("CLOSE:", resp)
        if not resp.get("ok"):
            return 1

    if args.close_all:
        err = _require_demo_confirm(args)
        if err is not None:
            return err
        resp = await bridge.request("CLOSE_ALL", {})
        print("CLOSE_ALL:", resp)
        if not resp.get("ok"):
            return 1

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="QuantEdge MT4 file-bridge handshake / demo trades")
    parser.add_argument("--wait", action="store_true", help="Block until EA heartbeat appears")
    parser.add_argument("--timeout", type=float, default=120.0, help="EA wait timeout seconds")
    parser.add_argument("--ping", action="store_true")
    parser.add_argument("--account", action="store_true")
    parser.add_argument("--positions", action="store_true")
    parser.add_argument("--order", action="store_true", help="Send a min-lot market order")
    parser.add_argument("--close", action="store_true", help="Close one ticket")
    parser.add_argument("--close-all", action="store_true", help="Close all QuantEdge magic positions")
    parser.add_argument("--ticket", type=int, default=None, help="MT4 ticket for --close")
    parser.add_argument("--symbol", default="BTCUSD", help="Canonical or broker symbol (BTCUSD→BTCUSDm)")
    parser.add_argument("--side", choices=["buy", "sell", "long", "short"], default="buy")
    parser.add_argument("--volume", type=float, default=0.01)
    parser.add_argument("--sl", type=float, default=None)
    parser.add_argument("--tp", type=float, default=None)
    parser.add_argument(
        "--i-understand-demo",
        action="store_true",
        help="Required confirmation for order/close (Exness Demo only)",
    )
    args = parser.parse_args()

    args.side = "buy" if args.side in ("long", "buy") else "sell"

    try:
        code = asyncio.run(run(args))
    except KeyboardInterrupt:
        code = 130
    sys.exit(code)


if __name__ == "__main__":
    main()
