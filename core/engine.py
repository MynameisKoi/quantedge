"""Main execution loop — paper / live orchestration."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import time
from datetime import UTC, datetime

from config.settings import settings
from core.events import Event, EventType, bus
from core.portfolio import portfolio
from core.rl.trade_memory import trade_memory
from macro.regime_classifier import RegimeClassifier
from macro.scheduler import macro_scheduler
from risk.manager import RiskManager
from strategies.registry import load_strategies

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("quantedge.engine")


class QuantEdgeEngine:
    """Event-driven orchestrator: regime → signals → risk → orders."""

    def __init__(self) -> None:
        self.regime = RegimeClassifier()
        self.risk = RiskManager()
        self.strategies = load_strategies()
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._last_heartbeat_t: float = 0.0
        self._last_order_time: dict[str, float] = {}
        self._in_flight_orders: set[str] = set()

    async def start(self) -> None:
        if settings.enable_live_trading:
            logger.warning("ENABLE_LIVE_TRADING=true — orders may route to Exness")
            from execution.bridge.facade import ensure_bridge
            from execution.bridge.paths import default_bridge_dir

            await ensure_bridge()
            logger.info(
                "Bridge transport=%s path/host=%s — attach QuantEdgeBridge.mq4",
                settings.bridge_transport,
                default_bridge_dir() if settings.bridge_transport == "file" else f"{settings.zmq_host}:{settings.zmq_req_port}",
            )
        else:
            logger.info("Paper mode (ENABLE_LIVE_TRADING=false)")

        self._running = True
        bus.subscribe(EventType.EMERGENCY_STOP, self._on_emergency_stop)
        bus.subscribe(EventType.REGIME_CHANGE, self._on_regime_change)

        self._tasks = [
            asyncio.create_task(self._regime_loop(), name="regime_loop"),
            asyncio.create_task(self._signal_loop(), name="signal_loop"),
        ]
        logger.info("QuantEdge engine started with %d strategies", len(self.strategies))
        await asyncio.gather(*self._tasks)

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("QuantEdge engine stopped")

    async def _regime_loop(self) -> None:
        # Bootstrap initial baseline regime on engine startup
        try:
            init_res = await self.regime.refresh()
            if init_res.changed:
                await bus.publish(
                    Event(
                        type=EventType.REGIME_CHANGE,
                        payload=init_res.as_dict(),
                        source="regime_classifier",
                    )
                )
        except Exception:
            logger.warning("Initial regime bootstrap failed, maintaining default: %s", self.regime.current.name)

        while self._running:
            if portfolio.emergency_stopped:
                await asyncio.sleep(5)
                continue
            try:
                should_run, event_name = macro_scheduler.should_refresh_macro()
                if should_run:
                    logger.info("Triggering scheduled market catalyst macro refresh: %s", event_name)
                    result = await self.regime.refresh()
                    if result.changed:
                        await bus.publish(
                            Event(
                                type=EventType.REGIME_CHANGE,
                                payload=result.as_dict(),
                                source="regime_classifier",
                            )
                        )
            except Exception:
                logger.exception("Scheduled regime refresh failed")

            # Check hourly asset-specific macro & news refresh
            try:
                from macro.asset_macro_manager import asset_macro_manager
                from macro.scheduler import macro_scheduler
                if asset_macro_manager.is_stale():
                    any_open = any(macro_scheduler.is_asset_market_open(a)[0] for a in asset_macro_manager.ASSETS)
                    if any_open:
                        await asset_macro_manager.refresh_all()
                    else:
                        logger.debug("All asset markets closed/down; skipping hourly LLM trend analysis.")
            except Exception as e:
                logger.debug("Hourly asset macro refresh check failed: %s", e)

            await asyncio.sleep(30)  # Check schedule every 30 seconds (zero API cost)

    async def _signal_loop(self) -> None:
        while self._running:
            if portfolio.emergency_stopped:
                await asyncio.sleep(2)
                continue

            # 1. Sync live MT4 balance, equity, and active open positions
            from execution.bridge.facade import get_bridge
            bridge = get_bridge()
            if bridge.connected:
                info = bridge.ea_info
                if "balance" in info or "equity" in info:
                    bal = float(info.get("balance", portfolio.balance))
                    eq = float(info.get("equity", bal))
                    portfolio.sync_mt4(bal, eq)

                try:
                    pos_reply = await bridge.request("POSITIONS", timeout=2.0)
                    if pos_reply.get("ok"):
                        raw_positions = (pos_reply.get("payload") or {}).get("positions", [])
                        portfolio.positions.clear()
                        for p_data in raw_positions:
                            raw_sym = str(p_data.get("symbol", ""))
                            norm_sym = raw_sym.upper().rstrip("M")
                            p_type = str(p_data.get("type", "buy")).lower()
                            p_side = "long" if "buy" in p_type else "short"
                            portfolio.open_position(
                                Position(
                                    symbol=norm_sym,
                                    side=p_side,
                                    volume=float(p_data.get("volume", 0.01)),
                                    entry_price=float(p_data.get("open_price", 0.0)),
                                    stop_loss=float(p_data.get("sl", 0.0)) if p_data.get("sl") else None,
                                    take_profit=float(p_data.get("tp", 0.0)) if p_data.get("tp") else None,
                                    unrealized_pnl=float(p_data.get("profit", 0.0)),
                                    ticket=str(p_data.get("ticket", "")),
                                )
                            )
                except Exception:
                    pass

            # 2. Pre-News Spread Guard: Pause fresh entries 5 min before Tier-1 releases
            is_blackout, blackout_reason = macro_scheduler.is_pre_news_blackout()
            if is_blackout and blackout_reason != "weekend_closed":
                logger.debug("Active pre-news blackout: %s — suppressing fresh market entries", blackout_reason)
                await asyncio.sleep(settings.signal_interval_sec)
                continue

            regime = self.regime.current

            # Periodic heartbeat log every 30 seconds so operator knows engine is active
            if time.time() - self._last_heartbeat_t >= 30.0:
                self._last_heartbeat_t = time.time()
                mt4_stat_str = f"Connected (${portfolio.balance:.2f})" if bridge.connected else "Standby"
                assets_str = ", ".join(self.strategies[0].assets) if self.strategies else "None"
                logger.info(
                    "[Heartbeat] 24/7 Engine active | MT4: %s | Regime: %s | Monitoring M15: %s | Open: %d",
                    mt4_stat_str,
                    regime.name.upper(),
                    assets_str,
                    len(portfolio.positions),
                )

            for strategy in self.strategies:
                try:
                    signals = strategy.compute_signals(
                        {"regime": regime.name, "timestamp": datetime.now(UTC).isoformat()}
                    )
                    for asset, signal in signals.items():
                        score = float(signal.get("score", 0))
                        if score < settings.signal_threshold:
                            continue

                        canon_asset = asset.upper().rstrip("M")

                        # 1. Market Hours Gate: Check if asset is actively tradable (avoids weekend err_132)
                        is_open, mkt_status = macro_scheduler.is_asset_market_open(canon_asset)
                        if not is_open:
                            logger.debug("[Market Gate] %s market closed: %s. Suppressing order dispatch.", canon_asset, mkt_status)
                            continue

                        # 2. Deduplication Guard: Strictly 1 consolidated position per asset (checks live MT4 ground truth)
                        from core.order_lifecycle_agent import order_lifecycle_agent

                        live_pos = await order_lifecycle_agent.sync_live_positions()
                        held_assets = {str(p.get("symbol", "")).upper().rstrip("M") for p in live_pos} | {p.symbol.upper().rstrip("M") for p in portfolio.positions.values()}
                        if canon_asset in held_assets:
                            continue

                        # 3. In-flight Lock: Prevent dispatching while previous request is pending in MT4
                        if canon_asset in self._in_flight_orders:
                            continue

                        # 4. Post-Loss Cooldown Guard: Enforce 60-minute lockout following a losing exit to eliminate churning
                        rem_loss_cd = order_lifecycle_agent.get_post_loss_cooldown(canon_asset)
                        if rem_loss_cd > 0:
                            logger.debug("[Post-Loss Cooldown] %s locked for %ds following previous loss.", canon_asset, int(rem_loss_cd))
                            continue

                        # 5. Standard Entry Cooldown Lock: Minimum 30 minutes between entries for the same asset
                        last_t = self._last_order_time.get(canon_asset, 0.0)
                        if time.time() - last_t < 1800.0:
                            remaining_cd = int(1800.0 - (time.time() - last_t))
                            logger.debug("[Cooldown Lock] %s in cooldown (%ds remaining). Skipping duplicate order.", canon_asset, remaining_cd)
                            continue

                        from core.order_agent import order_decision_agent

                        decision = order_decision_agent.decide_order(
                            asset=asset,
                            side=signal.get("side", "long"),
                            price=float(signal.get("price", 0.0)),
                        )
                        logger.info(
                            "[OrderDecisionAgent] %s | score=%.1f | approved=%s | reason=%s | vol=%s | px=%s | sl=%s | tp=%s",
                            asset,
                            score,
                            decision.get("approved"),
                            decision.get("reason"),
                            decision.get("volume"),
                            decision.get("price"),
                            decision.get("stop_loss"),
                            decision.get("take_profit"),
                        )

                        state_key = signal.get("state_key", f"{asset}|{regime.name}|default")
                        rl_action = signal.get("rl_action", "execute_full")

                        await bus.publish(
                            Event(
                                type=EventType.SIGNAL,
                                payload={
                                    "strategy": strategy.name,
                                    "asset": asset,
                                    "signal": signal,
                                    "risk": decision,
                                    "rl_state": state_key,
                                    "rl_action": rl_action,
                                },
                                source=strategy.name,
                            )
                        )
                        if decision.get("approved") and settings.enable_live_trading:
                            self._in_flight_orders.add(canon_asset)
                            try:
                                res = await order_decision_agent.fire_order(
                                    asset=asset,
                                    side=decision.get("side"),
                                    price=decision.get("price"),
                                )
                                if res.get("ok"):
                                    self._last_order_time[canon_asset] = time.time()
                            finally:
                                self._in_flight_orders.discard(canon_asset)
                except Exception:
                    logger.exception("Strategy %s failed", strategy.name)

            # 3. Multi-Order Lifecycle & Scale-In Management
            try:
                from core.order_lifecycle_agent import order_lifecycle_agent
                await order_lifecycle_agent.run_lifecycle_management_tick(auto_close=True)
            except Exception as e:
                logger.debug("Order lifecycle management tick failed: %s", e)

            await asyncio.sleep(settings.signal_interval_sec)

    async def _on_emergency_stop(self, event: Event) -> None:
        portfolio.emergency_stopped = True
        closed = portfolio.close_all()
        logger.critical("EMERGENCY STOP — closed %d positions: %s", len(closed), closed)

    async def _on_regime_change(self, event: Event) -> None:
        regime = event.payload.get("regime", "unknown")
        logger.info("Regime change → %s", regime)
        for strategy in self.strategies:
            strategy.on_regime_change(regime)


async def _main() -> None:
    engine = QuantEdgeEngine()

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _signal_handler(*_: object) -> None:
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows
            signal.signal(sig, lambda *_: stop_event.set())

    runner = asyncio.create_task(engine.start())
    await stop_event.wait()
    await engine.stop()
    runner.cancel()
    await asyncio.gather(runner, return_exceptions=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QuantEdge live/paper engine")
    parser.parse_args()
    asyncio.run(_main())
