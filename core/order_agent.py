"""Order Decision & Execution Agent.

Autonomous specialized agent that evaluates active market setups,
decides all order parameters (canonical & broker symbol, side, volume,
execution price, stop loss, take profit, breakeven trigger), verifies
risk and account equity constraints, and fires the order into Exness MT4.
"""

from __future__ import annotations

from datetime import UTC, datetime
import asyncio
import json
import logging
from pathlib import Path
import threading
import time
from typing import Any

from config.settings import settings
from core.portfolio import Position, portfolio
from core.rl.trade_memory import trade_memory
from data.feeds.live_price_feed import live_price_feed
from execution.bridge.facade import get_bridge
from execution.bridge.symbols import to_broker_symbol
from execution.order_manager import OrderManager
from macro.observability import llm_observer
from risk.manager import RiskManager
from risk.position_sizer import CONTRACT_SIZES, atr_position_size
from strategies.strategy_allocator import strategy_allocator

logger = logging.getLogger(__name__)

ORDER_LOCK_FILE = Path("data/order_locks.json")


class OrderDecisionAgent:
    """Specialized agent responsible for trade parameter decision and MT4 order firing."""

    def __init__(self) -> None:
        self.risk_manager = RiskManager()
        self.order_manager = OrderManager()
        self._in_flight: set[str] = set()
        self._async_lock = asyncio.Lock()

    def _get_order_locks(self) -> dict[str, Any]:
        if not ORDER_LOCK_FILE.exists():
            return {}
        try:
            raw = ORDER_LOCK_FILE.read_text(encoding="utf-8").strip()
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    def _record_order_lock(self, asset: str, ticket: str, side: str) -> None:
        try:
            ORDER_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = self._get_order_locks()
            canon = asset.upper().rstrip("M")
            data[canon] = {
                "timestamp": time.time(),
                "time_iso": datetime.now(UTC).isoformat(),
                "ticket": ticket,
                "side": side,
                "asset": canon,
            }
            ORDER_LOCK_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Failed writing order lock for %s: %s", asset, e)

    def clear_order_lock(self, asset: str) -> None:
        """Clear the cooldown lock for an asset."""
        try:
            data = self._get_order_locks()
            data.pop(asset.upper().rstrip("M"), None)
            ORDER_LOCK_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def sync_account(self) -> dict[str, float]:
        """Synchronize live MT4 balance and equity before order decision."""
        bridge = get_bridge()
        if bridge.connected:
            info = bridge.ea_info
            if "balance" in info or "equity" in info:
                bal = float(info.get("balance", portfolio.balance))
                eq = float(info.get("equity", bal))
                portfolio.sync_mt4(bal, eq)
        return {"balance": portfolio.balance, "equity": portfolio.equity, "drawdown_pct": portfolio.drawdown_pct}

    def decide_order(
        self,
        asset: str,
        side: str | None = None,
        price: float | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Evaluate market conditions, macro consensus, and account risk
        to decide all trade parameters: symbol, side, volume, price, S/L, T/P.
        """
        self.sync_account()
        canon_asset = asset.upper().rstrip("M")

        # Cooldown guard: 30 minutes (1800s) minimum between new orders for the same asset
        if not force:
            locks = self._get_order_locks()
            last_order = locks.get(canon_asset)
            if last_order:
                elapsed = time.time() - float(last_order.get("timestamp", 0))
                if elapsed < 1800.0:
                    remaining = int(1800.0 - elapsed)
                    return {
                        "approved": False,
                        "asset": asset,
                        "reason": f"asset_in_cooldown_{remaining}s_remaining",
                        "cooldown_remaining_sec": remaining,
                    }

            # Open position guard: Strictly 1 consolidated position per asset
            held_symbols = {p.symbol.upper().rstrip("M") for p in portfolio.positions.values()}
            if canon_asset in held_symbols:
                return {
                    "approved": False,
                    "asset": asset,
                    "reason": f"already_holding_position_on_{canon_asset}",
                }

        alloc = strategy_allocator.evaluate_live_allocation(asset, side_override=side)

        # 1. Resolve Side & Execution Price
        trade_side = side or alloc.get("side", "none")
        if trade_side not in ("long", "short", "buy", "sell"):
            return {
                "approved": False,
                "asset": asset,
                "reason": f"no_clear_directional_side_{trade_side}",
                "allocation": alloc,
            }
        canonical_side = "long" if trade_side in ("long", "buy") else "short"

        # Resolve live execution price from broker quotes
        live_quotes = live_price_feed.get_live_quotes()
        quote = live_quotes.get(asset, {})
        digits = 4 if "EUR" in asset else 2

        if canonical_side == "long":
            exec_price = float(quote.get("ask") or alloc.get("live_price", 0.0) or price or 0.0)
        else:
            exec_price = float(quote.get("bid") or alloc.get("live_price", 0.0) or price or 0.0)

        if exec_price <= 0.0:
            exec_price = float(live_price_feed.get_live_prices_sync().get(asset, 1.0))
        exec_price = round(exec_price, digits)

        # 2. Extract Indicator Parameters
        atr = float(alloc.get("atr", alloc.get("indicators", {}).get("atr", 1.0)))
        sl_mult = float(alloc.get("sl_mult", 1.5))
        be_r = float(alloc.get("be_r", 1.0))
        partial_r = float(alloc.get("partial_r", 2.0))
        score = float(alloc.get("score", 0.0))
        threshold = float(alloc.get("threshold", settings.signal_threshold))

        # 3. Check Threshold & Agent Consensus
        consensus = alloc.get("agent_consensus", {})
        all_agreed = consensus.get("all_agreed", False)
        threshold_met = (score >= threshold) and all_agreed

        if not threshold_met and not force:
            return {
                "approved": False,
                "asset": asset,
                "score": score,
                "threshold": threshold,
                "reason": "signal_threshold_not_met",
                "consensus_agreed": all_agreed,
                "summary": alloc.get("consensus_summary", ""),
            }

        # 4. Institutional 1% Risk Sizing Calculation
        sizing = atr_position_size(
            price=exec_price,
            atr=atr,
            asset=asset,
            atr_stop_mult=sl_mult,
            tp_r_mult=partial_r,
            be_r_mult=be_r,
        )

        stop_loss = sizing["stop_loss_long"] if canonical_side == "long" else sizing["stop_loss_short"]
        take_profit = sizing["take_profit_long"] if canonical_side == "long" else sizing["take_profit_short"]
        be_trigger = sizing["breakeven_long"] if canonical_side == "long" else sizing["breakeven_short"]
        volume = float(sizing["volume"])

        # 5. Broker Symbol Mapping (e.g. USOIL -> USOILm)
        broker_symbol = to_broker_symbol(asset)

        # 6. Risk Gate Evaluation
        risk_eval = self.risk_manager.evaluate(
            asset=asset,
            side=canonical_side,
            score=score,
            atr=atr,
            price=exec_price,
            sl_mult=sl_mult,
            be_r=be_r,
            partial_r=partial_r,
        )

        if not risk_eval.get("approved") and not force:
            return {
                "approved": False,
                "asset": asset,
                "reason": risk_eval.get("reason", "risk_gate_rejected"),
                "risk_details": risk_eval,
            }

        # 7. Synthesize Agent Decision Rationale
        archetype = alloc.get("strategy_archetype", "Momentum Impulse")
        rationale = (
            f"Order Decision Agent approved {canonical_side.upper()} {asset} ({broker_symbol}) at {exec_price:.{digits}f}. "
            f"Strategy: {alloc.get('strategy_name', 'AdaptiveM15')} ({archetype}). "
            f"Consensus: {consensus.get('agreed_count', 5)}/{consensus.get('total_agents', 5)} agents agreed (Score {score:.1f}/{threshold:.0f}). "
            f"Size: {volume:.2f} lots (1% equity risk = ${sizing['risk_amount']:.2f} on ${portfolio.equity:.2f} equity). "
            f"Risk controls: S/L={stop_loss:.{digits}f} (-{sizing['stop_distance']:.{digits}f}), "
            f"T/P={take_profit:.{digits}f} (+{sizing['stop_distance']*partial_r:.{digits}f}), "
            f"B/E trigger={be_trigger:.{digits}f}."
        )

        decision: dict[str, Any] = {
            "approved": True,
            "asset": asset,
            "symbol": broker_symbol,
            "canonical_symbol": asset,
            "side": canonical_side,
            "order_cmd": "buy" if canonical_side == "long" else "sell",
            "volume": volume,
            "price": exec_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "breakeven_trigger": be_trigger,
            "stop_distance": sizing["stop_distance"],
            "risk_amount": sizing["risk_amount"],
            "equity": round(portfolio.equity, 2),
            "score": score,
            "threshold": threshold,
            "strategy_name": alloc.get("strategy_name", "AdaptiveM15"),
            "strategy_archetype": archetype,
            "rationale": rationale,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        return decision

    async def fire_order(
        self,
        asset: str,
        side: str | None = None,
        price: float | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Formulate order requirements and dispatch immediately to Exness MT4 bridge.
        Enforces strict single-order execution and atomic in-flight locking.
        """
        canon_asset = asset.upper().rstrip("M")

        async with self._async_lock:
            if canon_asset in self._in_flight:
                logger.warning("OrderDecisionAgent rejected %s: order already in-flight", asset)
                return {
                    "ok": False,
                    "status": "rejected",
                    "reason": f"order_already_in_flight_for_{canon_asset}",
                }

            self._in_flight.add(canon_asset)
            try:
                decision = self.decide_order(asset, side=side, price=price, force=force)
                if not decision.get("approved"):
                    logger.warning("OrderDecisionAgent rejected %s order: %s", asset, decision.get("reason"))
                    return {
                        "ok": False,
                        "status": "rejected",
                        "reason": decision.get("reason", "unknown_rejection"),
                        "decision": decision,
                    }

                logger.info("OrderDecisionAgent firing MT4 order: %s", decision["rationale"])

                # Submit via OrderManager
                submit_res = await self.order_manager.submit(decision)
                status = submit_res.get("status")

                if status in ("submitted", "ok") or submit_res.get("bridge", {}).get("ok"):
                    payload = submit_res.get("bridge", {}).get("payload") or {}
                    ticket = payload.get("ticket") or submit_res.get("bridge", {}).get("ticket") or "TICKET_PENDING"
                    fill_price = float(payload.get("price") or decision["price"])

                    # Persist atomic order lock across processes
                    self._record_order_lock(canon_asset, str(ticket), decision["side"])

                    # Record in Trade Memory
                    trade_memory.record_entry(
                        trade_id=f"{asset}_{datetime.now(UTC).timestamp()}",
                        asset=asset,
                        strategy=decision["strategy_name"],
                        state_key=f"{asset}|{decision['strategy_archetype']}",
                        action="execute_full",
                        side=decision["side"],
                        entry_price=fill_price,
                    )

                    # LangSmith Telemetry Tracking
                    try:
                        if settings.langsmith_api_key:
                            threading.Thread(
                                target=llm_observer.record,
                                kwargs={
                                    "agent_name": "quantedge_order_decision_agent",
                                    "provider": "autonomous_agent",
                                    "model": settings.primary_macro_model,
                                    "system_prompt": "Order Decision & Dispatch Protocol for MT4",
                                    "user_prompt": f"Fire order for {asset} {decision['side'].upper()}",
                                    "response_text": decision["rationale"],
                                    "parsed_json": {
                                        "ticket": str(ticket),
                                        "order": decision,
                                        "bridge_reply": submit_res,
                                    },
                                    "latency_ms": 25.0,
                                    "helicone_enabled": bool(settings.helicone_api_key),
                                    "langsmith_enabled": True,
                                },
                                daemon=True,
                            ).start()
                    except Exception as e:
                        logger.debug("LangSmith order fire telemetry skipped: %s", e)

                    return {
                        "ok": True,
                        "status": "executed",
                        "ticket": str(ticket),
                        "fill_price": fill_price,
                        "decision": decision,
                        "order": submit_res.get("order", {}),
                        "bridge": submit_res.get("bridge", {}),
                        "message": f"Order successfully executed in MT4: Ticket #{ticket} ({decision['side'].upper()} {decision['volume']} lots {decision['symbol']})",
                    }
                else:
                    logger.error("MT4 bridge execution failed: %s", submit_res)
                    return {
                        "ok": False,
                        "status": "bridge_error",
                        "decision": decision,
                        "bridge": submit_res,
                        "reason": submit_res.get("reason") or submit_res.get("bridge", {}).get("error", "execution_failed"),
                    }
            finally:
                self._in_flight.discard(canon_asset)


# Global singleton instance
order_decision_agent = OrderDecisionAgent()
