"""Production 24/7 Live Bot Supervisor for QuantEdge & Exness MetaTrader 4.

Features:
- Continuous 24/7 execution loop with auto-recovery on unhandled exceptions.
- MT4 FileBridge watchdog: Monitors heartbeat.json; alerts and pauses safely if MT4 drops.
- Precision Macro & News Scheduling: Minimizes API costs by only firing at critical market windows.
- Pre-News Spread Guard: Automatically suppresses new entries during spread spikes.
- Graceful shutdown on SIGINT / SIGTERM with open position safety preservation.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
import time
from datetime import UTC, datetime

import msvcrt
import os
from pathlib import Path

from config.settings import settings
from core.engine import QuantEdgeEngine
from execution.bridge.facade import ensure_bridge, get_bridge

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("quantedge.live_bot")

_BOT_LOCK_FILE = None


def acquire_instance_lock() -> bool:
    """Ensure strictly one instance of QuantEdge Live Bot runs across the operating system."""
    global _BOT_LOCK_FILE
    lock_path = Path("data/quantedge_live_bot.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        f = open(lock_path, "a+")
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        f.seek(0)
        f.truncate()
        f.write(f"PID={os.getpid()} | Started={datetime.now(UTC).isoformat()}\n")
        f.flush()
        _BOT_LOCK_FILE = f
        return True
    except (BlockingIOError, OSError):
        return False


async def verify_mt4_bridge(timeout: float = 30.0) -> dict[str, any] | None:
    """Check if Exness MT4 FileBridge is running and return account info."""
    bridge = await ensure_bridge()
    logger.info("Connecting to MT4 FileBridge (FILE_COMMON\\quantedge)...")
    start_t = time.time()
    while time.time() - start_t < timeout:
        if bridge.connected:
            info = bridge.ea_info
            logger.info("✓ MT4 EA Connected successfully: %s", info)
            return info
        await asyncio.sleep(1.0)
    logger.warning("MT4 EA heartbeat not detected after %.0f seconds.", timeout)
    logger.warning("Please ensure MT4 is running with QuantEdgeBridge.mq4 attached to a chart.")
    return None


async def run_supervised_engine(auto_restart: bool = True, max_restarts: int = 100) -> None:
    """Run QuantEdge engine with automatic watchdog supervision."""
    restart_count = 0
    stop_event = asyncio.Event()

    def _on_signal(*_: object) -> None:
        logger.info("Shutdown signal received — stopping engine gracefully...")
        stop_event.set()

    # Handle OS termination signals
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop_event.set())

    while not stop_event.is_set():
        engine = QuantEdgeEngine()
        engine_task = None
        try:
            logger.info("=" * 70)
            logger.info("STARTING QUANTEDGE 24/7 LIVE ENGINE (Session: %d)", restart_count + 1)
            logger.info("Live Trading Enabled: %s (Exness Type: %s)", settings.enable_live_trading, settings.exness_account_type)
            logger.info("=" * 70)

            # Check MT4 link before launching main tasks
            bridge = get_bridge()
            if settings.enable_live_trading and not bridge.connected:
                logger.info("Waiting for MT4 EA heartbeat before placing trades...")
                await verify_mt4_bridge(timeout=15.0)

            engine_task = asyncio.create_task(engine.start(), name="quantedge_engine")

            # Wait until either the engine terminates unexpectedly or user sends stop signal
            done, pending = await asyncio.wait(
                [engine_task, asyncio.create_task(stop_event.wait())],
                return_when=asyncio.FIRST_COMPLETED,
            )

            if stop_event.is_set():
                break

            # If engine_task failed unexpectedly
            for t in done:
                if t is engine_task and t.exception():
                    exc = t.exception()
                    logger.error("QuantEdgeEngine encountered unhandled exception: %s", exc, exc_info=exc)

        except asyncio.CancelledError:
            logger.info("Supervisor task cancelled")
            break
        except Exception as e:
            logger.exception("Supervisor encountered fatal loop error: %s", e)
        finally:
            if engine:
                logger.info("Shutting down engine instance...")
                await engine.stop()

        if stop_event.is_set():
            break

        if not auto_restart or restart_count >= max_restarts:
            logger.error("Auto-restart disabled or max restarts reached. Terminating.")
            break

        restart_count += 1
        backoff_sec = min(30, 5 * restart_count)
        logger.warning("Rebooting QuantEdge engine in %d seconds (Attempt %d/%d)...", backoff_sec, restart_count, max_restarts)
        await asyncio.sleep(backoff_sec)

    logger.info("QuantEdge 24/7 Supervisor exited cleanly.")


def main() -> None:
    parser = argparse.ArgumentParser(description="QuantEdge 24/7 Production Live Trading Supervisor")
    parser.add_argument("--no-restart", action="store_true", help="Disable automatic recovery on crash")
    parser.add_argument("--check-bridge", action="store_true", help="Only verify MT4 bridge connection and exit")
    args = parser.parse_args()

    if args.check_bridge:
        async def _check() -> int:
            info = await verify_mt4_bridge(timeout=10.0)
            if info:
                print("\n[OK] MT4 Bridge is ACTIVE.")
                print(f"Account: {info.get('account')}")
                print(f"Server: {info.get('server')}")
                print(f"Balance: ${info.get('balance')}")
                print(f"Equity: ${info.get('equity')}")
                return 0
            print("\n[FAIL] MT4 Bridge is NOT connected.")
            return 1

        sys.exit(asyncio.run(_check()))

    if not args.check_bridge:
        if not acquire_instance_lock():
            print("\n" + "=" * 75)
            print("[FATAL ERROR] Another instance of QuantEdge Live Bot is already running!")
            print("Strictly 1 engine instance is permitted to route orders to Exness MT4.")
            print("Please terminate any duplicate console/terminal window before launching.")
            print("=" * 75 + "\n")
            logger.error("Duplicate bot process rejected via OS instance lock.")
            sys.exit(1)

    try:
        asyncio.run(run_supervised_engine(auto_restart=not args.no_restart))
    except (KeyboardInterrupt, SystemExit):
        logger.info("Program terminated by user")
    finally:
        if _BOT_LOCK_FILE:
            try:
                msvcrt.locking(_BOT_LOCK_FILE.fileno(), msvcrt.LK_UNLCK, 1)
                _BOT_LOCK_FILE.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
