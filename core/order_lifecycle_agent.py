"""Multi-Order Lifecycle & Scale-In Management Agent.

Monitors, controls, and manages multiple concurrent orders across assets using
Institutional Quantitative Paradigms:
1. The Triple-Barrier Method (Marcos López de Prado):
   - Upper Barrier: Asymmetric profit target (+2.0R or custom TP).
   - Lower Barrier: Structural stop loss (-1.0R broker stop / -0.5R confirmed defensive cut).
   - Vertical Barrier: Dynamic time expiration based on volatility / bar counts.
     Detects Alpha Decay when a position fails to develop traction within the vertical barrier.
2. Volatility-Adjusted (Bar-Based) Breathing Windows:
   - Dynamic breathing windows scaled by asset type and liquidity session
     (e.g., shorter for high-beta BTCUSD, longer for Asian session EURUSD).
3. State-Based Invalidation (MAE & MFE Tracking):
   - Continuous tracking of Maximum Favorable Excursion (MFE) and Maximum Adverse Excursion (MAE).
   - Trailing peak giveback protection when peak profit pulls back excessively.
4. Bar-Close Confirmation:
   - Eliminates intrabar wick shakeouts by requiring candle-close confirmation beyond key levels.
5. Audited Price Sources & Spread Cushioning:
   - Liquidates Longs at Bid and Shorts at Ask with broker spread padding to prevent artificial stops.
6. Pyramiding & Scale-In:
   - Identifies high-momentum winners with positive expectancy to safely add exposure.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import time
from typing import Any

from config.settings import settings
from core.order_agent import order_decision_agent
from core.portfolio import Position, portfolio
from data.feeds.live_price_feed import live_price_feed
from execution.bridge.facade import get_bridge
from execution.order_manager import OrderManager
from macro.scheduler import macro_scheduler
from strategies.strategy_allocator import strategy_allocator

logger = logging.getLogger(__name__)


class OrderLifecycleAgent:
    """Specialized agent managing the full lifecycle of concurrent multi-asset orders."""

    def __init__(self) -> None:
        self.order_manager = OrderManager()
        self._ticket_first_seen: dict[str, float] = {}
        self._ticket_mfe: dict[str, float] = {}  # Max Favorable Excursion (in R-multiples)
        self._ticket_mae: dict[str, float] = {}  # Max Adverse Excursion (in R-multiples)
        self._ticket_invalidation_ticks: dict[str, int] = {}  # Bar-close confirmation counter
        self._ticket_invalidation_start: dict[str, float] = {}  # Invalidation start timestamp
        self._post_loss_cooldown: dict[str, float] = {}  # Asset -> timestamp of last losing exit

    def get_dynamic_session_window(self, asset: str, atr: float = 1.0) -> tuple[float, float, str]:
        """
        Calculate volatility- and session-adjusted breathing window and vertical barrier (Triple-Barrier).
        Returns: (breathing_window_sec, vertical_barrier_sec, session_name)
        """
        now_dt = datetime.now(UTC)
        hour = now_dt.hour
        canon = asset.upper().rstrip("M")

        # Session detection (UTC):
        # Asian / Pacific: 21:00 - 07:00 UTC
        # London Open: 07:00 - 13:00 UTC
        # London / NY Overlap: 13:00 - 17:00 UTC
        # NY Afternoon: 17:00 - 21:00 UTC
        if 7 <= hour < 13:
            session = "London"
        elif 13 <= hour < 17:
            session = "London/NY Overlap"
        elif 17 <= hour < 21:
            session = "New York"
        else:
            session = "Asian (Off-Hours)"

        # Asset-specific breathing window & vertical time barrier
        if canon == "BTCUSD":
            # 24/7 high-beta crypto: 900s baseline (3 M5 bars), 7200s vertical barrier (2 hours)
            base_breathing = 900.0
            vertical_barrier = 7200.0
        elif canon == "EURUSD":
            # FX Asian session is low-volatility consolidation; expand breathing window to 1800s (2 M15 bars)
            # Active European/US overlap: 900s (1 M15 bar)
            base_breathing = 1800.0 if session == "Asian (Off-Hours)" else 900.0
            vertical_barrier = 7200.0 if session == "Asian (Off-Hours)" else 5400.0
        elif canon == "USOIL":
            # Crude oil actively trades during US/London energy hours
            base_breathing = 900.0 if session in ("London/NY Overlap", "New York") else 1200.0
            vertical_barrier = 3600.0
        elif canon == "XAUUSD":
            # Gold: 900s during active liquidity, 1200s off-hours
            base_breathing = 900.0 if session in ("London", "London/NY Overlap", "New York") else 1200.0
            vertical_barrier = 5400.0
        else:
            base_breathing = 900.0
            vertical_barrier = 3600.0

        return base_breathing, vertical_barrier, session

    async def sync_live_positions(self) -> list[dict[str, Any]]:
        """Fetch real-time open positions directly from MT4 bridge, falling back to portfolio."""
        bridge = get_bridge()
        positions: list[dict[str, Any]] = []
        if bridge.connected:
            try:
                reply = await bridge.request("POSITIONS", timeout=2.0)
                if reply.get("ok"):
                    positions = (reply.get("payload") or {}).get("positions", [])
            except Exception as e:
                logger.debug("Failed syncing live MT4 positions: %s", e)

        mt4_tickets = {str(p.get("ticket")) for p in positions}
        for k, pos in portfolio.positions.items():
            t_str = str(pos.ticket or k)
            if t_str not in mt4_tickets:
                positions.append(
                    {
                        "ticket": t_str,
                        "symbol": pos.symbol,
                        "side": pos.side,
                        "volume": pos.volume,
                        "entry_price": pos.entry_price,
                        "sl": pos.stop_loss,
                        "tp": pos.take_profit,
                        "profit": pos.unrealized_pnl,
                    }
                )
        return positions

    async def evaluate_open_positions(self) -> list[dict[str, Any]]:
        """
        Concurrently evaluate all open positions across multiple assets using:
        1. Triple-Barrier Method (Upper horizontal, Lower horizontal, Vertical time barrier)
        2. Session- and Volatility-Adjusted Breathing Windows
        3. State-Based Invalidation with MAE & MFE Tracking
        4. Bar-Close Confirmation (no intrabar wick shakeouts)
        5. Broker Bid/Ask Spread Cushioning
        """
        raw_positions = await self.sync_live_positions()
        live_quotes = live_price_feed.get_live_quotes()
        all_allocations = strategy_allocator.allocate_all()
        is_blackout, blackout_reason = macro_scheduler.is_pre_news_blackout()

        analyses: list[dict[str, Any]] = []
        now_ts = datetime.now(UTC).timestamp()

        # Active ticket set for housekeeping
        active_tickets = set()

        for p in raw_positions:
            raw_sym = str(p.get("symbol", ""))
            canon_sym = raw_sym.upper().rstrip("M")
            ticket = str(p.get("ticket", "0"))
            active_tickets.add(ticket)

            side = str(p.get("side", p.get("type", "buy"))).lower()
            canonical_side = "long" if "buy" in side or "long" in side else "short"
            volume = float(p.get("volume", 0.01))
            entry_px = float(p.get("open_price", p.get("entry_price", 0.0)))
            sl = float(p.get("sl", 0.0)) if p.get("sl") else None
            tp = float(p.get("tp", 0.0)) if p.get("tp") else None
            profit = float(p.get("profit", p.get("unrealized_pnl", 0.0)))

            alloc = all_allocations.get(canon_sym, {})
            indicators = alloc.get("indicators", {})
            atr = float(alloc.get("atr", indicators.get("atr", 1.0)))

            # -----------------------------------------------------------------
            # 1. Volatility- and Session-Adjusted Breathing Window & Vertical Barrier
            # -----------------------------------------------------------------
            open_time = float(p.get("open_time", 0.0))
            if open_time > 1000000000:
                holding_sec = max(0.0, now_ts - open_time)
            else:
                first_seen = self._ticket_first_seen.setdefault(ticket, now_ts)
                holding_sec = max(0.0, now_ts - first_seen)

            breathing_sec, vertical_barrier_sec, session_name = self.get_dynamic_session_window(canon_sym, atr=atr)
            in_breathing_window = holding_sec < breathing_sec

            # -----------------------------------------------------------------
            # 2. Audited Price Sources & Spread Cushioning
            # -----------------------------------------------------------------
            quote = live_quotes.get(canon_sym, {})
            bid_px = float(quote.get("bid") or 0.0)
            ask_px = float(quote.get("ask") or 0.0)
            if bid_px <= 0 or ask_px <= 0:
                bid_px = ask_px = entry_px

            # Long liquidation executes at BID; Short liquidation executes at ASK
            curr_px = bid_px if canonical_side == "long" else ask_px
            mid_px = (bid_px + ask_px) / 2.0 if bid_px > 0 and ask_px > 0 else curr_px
            spread = max(0.0, ask_px - bid_px)

            # -----------------------------------------------------------------
            # 3. R-Multiple & Excursion Tracking (MAE / MFE)
            # -----------------------------------------------------------------
            stop_dist = abs(entry_px - sl) if sl and abs(entry_px - sl) > 0 else (atr * 1.5)
            direction = 1.0 if canonical_side == "long" else -1.0
            price_delta = (curr_px - entry_px) * direction
            r_multiple = round(price_delta / max(stop_dist, 1e-4), 2)

            # Update MFE and MAE
            cur_mfe = self._ticket_mfe.get(ticket, r_multiple)
            cur_mae = self._ticket_mae.get(ticket, r_multiple)
            cur_mfe = max(cur_mfe, r_multiple)
            cur_mae = min(cur_mae, r_multiple)
            self._ticket_mfe[ticket] = cur_mfe
            self._ticket_mae[ticket] = cur_mae

            # Spread ratio to stop distance
            spread_r = round(spread / max(stop_dist, 1e-4), 3)

            # -----------------------------------------------------------------
            # 4. Bar-Close Confirmation for Trend Invalidation
            # -----------------------------------------------------------------
            trend = indicators.get("trend", "neutral")
            ema21 = float(indicators.get("ema21", entry_px))
            ema50 = float(indicators.get("ema50", entry_px))

            # Structural condition: candle close beyond key level (EMA 50 or EMA 21 with confirmed opposing trend)
            is_structurally_against = False
            if canonical_side == "long" and (mid_px < ema50 or (mid_px < ema21 and trend == "bearish")):
                is_structurally_against = True
            elif canonical_side == "short" and (mid_px > ema50 or (mid_px > ema21 and trend == "bullish")):
                is_structurally_against = True

            if is_structurally_against:
                consec_ticks = self._ticket_invalidation_ticks.get(ticket, 0) + 1
                self._ticket_invalidation_ticks[ticket] = consec_ticks
                inv_start = self._ticket_invalidation_start.setdefault(ticket, now_ts)
                inv_duration_sec = max(0.0, now_ts - inv_start)
            else:
                self._ticket_invalidation_ticks[ticket] = 0
                self._ticket_invalidation_start.pop(ticket, None)
                consec_ticks = 0
                inv_duration_sec = 0.0

            # Require persistent invalidation lasting at least 15 minutes (900s) to confirm candle-close
            bar_close_confirmed = inv_duration_sec >= 900.0

            # Spread-cushioned defensive trigger: require -1.0R adverse excursion so normal pullback doesn't cut trade
            defensive_threshold = -1.0 - max(0.0, spread_r - 0.1)

            # -----------------------------------------------------------------
            # 5. Triple-Barrier Dynamic Decision Logic
            # -----------------------------------------------------------------
            action = "HOLD"
            action_type = "hold"
            urgency = "low"
            can_scale_in = False

            dev_min_str = f"{int(breathing_sec/60)}-min"
            if in_breathing_window:
                reason = (
                    f"Position in initial {dev_min_str} development window "
                    f"({int(holding_sec)}s/{int(breathing_sec)}s, {r_multiple:+.2f}R, {session_name}). "
                    f"S/L and T/P active."
                )
            else:
                reason = (
                    f"Position trending at {r_multiple:+.2f}R [MFE: {cur_mfe:+.2f}R / MAE: {cur_mae:+.2f}R] "
                    f"({int(holding_sec/60)}m elapsed, {session_name}). Monitoring M15 structure."
                )

            # BARRIER 1 (Upper Barrier): Take Profit (+2.0R or TP price hit)
            if r_multiple >= 2.0 or (tp and ((canonical_side == "long" and curr_px >= tp) or (canonical_side == "short" and curr_px <= tp))):
                action = "CLOSE_TAKE_PROFIT"
                action_type = "close"
                reason = f"Upper Barrier (+2.0R) achieved at {r_multiple:+.2f}R. Bank profit and secure capital."
                urgency = "high"

            # Strict Breathing Window Protection:
            # During the initial development window, allow the position to breathe and absorb spread/pullbacks.
            # Do NOT cut defensively or exit for alpha decay during breathing window.
            elif in_breathing_window:
                action = "HOLD"
                action_type = "hold"
                urgency = "low"

            # BARRIER 2 (Lower Barrier): Confirmed Structural Invalidation (Post-Breathing Window)
            elif not in_breathing_window and is_structurally_against and bar_close_confirmed and r_multiple <= defensive_threshold:
                action = "CLOSE_DEFENSIVE"
                action_type = "close"
                reason = (
                    f"M15 candle-close confirmed structural reversal ({trend.upper()}) over {int(inv_duration_sec)}s at {r_multiple:+.2f}R "
                    f"(cushioned for {spread_r:.2f}R spread). Defensive exit to preserve capital."
                )
                urgency = "high"

            # BARRIER 3 (Vertical Barrier): Time Expiration & Alpha Decay
            elif not in_breathing_window and holding_sec >= vertical_barrier_sec:
                if cur_mfe < 0.20:
                    action = "CLOSE_ALPHA_DECAY"
                    action_type = "close"
                    reason = (
                        f"Vertical time barrier expired ({int(holding_sec/60)}m / {session_name}) with zero traction "
                        f"(MFE {cur_mfe:+.2f}R, current {r_multiple:+.2f}R). Alpha decay detected; scratch exit."
                    )
                    urgency = "medium"
                elif r_multiple >= 1.0:
                    action = "MOVE_BREAKEVEN"
                    action_type = "adjust_sl"
                    reason = f"Vertical time barrier elapsed while trade is profitable ({r_multiple:+.2f}R). Lock breakeven."
                    urgency = "medium"

            # RULE 4: Peak Giveback Guard (Trailing Protection after reaching +1.5R)
            elif cur_mfe >= 1.5 and r_multiple <= (cur_mfe * 0.5) and r_multiple >= 0.4:
                action = "CLOSE_TRAIL_EXIT"
                action_type = "close"
                reason = (
                    f"Peak profit reached +{cur_mfe:.2f}R; current retracement to {r_multiple:+.2f}R gave back >50% of gains. "
                    f"Trailing profit protection exit triggered."
                )
                urgency = "high"

            # RULE 5: Breakeven Ratchet (+1.0R achieved)
            elif r_multiple >= 1.0 and (sl is None or abs(sl - entry_px) > (stop_dist * 0.5)):
                action = "MOVE_BREAKEVEN"
                action_type = "adjust_sl"
                reason = f"Floating profit at {r_multiple:+.2f}R (Peak MFE: {cur_mfe:+.2f}R). Move stop loss to entry ({entry_px:.2f}) for zero risk."
                urgency = "medium"

            # RULE 6: Pre-News Blackout De-risking
            elif is_blackout and blackout_reason != "weekend_closed" and not in_breathing_window and r_multiple < 0.5:
                action = "CLOSE_PRE_NEWS"
                action_type = "close"
                reason = f"Tier-1 news event blackout active ({blackout_reason}). Close to avoid spread slippage."
                urgency = "medium"

            # RULE 7: Scale-In / Pyramiding Opportunity
            score = float(alloc.get("score", 0.0))
            threshold = float(alloc.get("threshold", 65.0))
            consensus_met = alloc.get("agent_consensus", {}).get("all_agreed", False)

            if not in_breathing_window and r_multiple >= 0.8 and score >= threshold and consensus_met and not is_structurally_against:
                can_scale_in = True
                if action == "HOLD":
                    action = "SCALE_IN"
                    action_type = "scale_in"
                    reason = (
                        f"Winner running at {r_multiple:+.2f}R (MFE {cur_mfe:+.2f}R) with strong momentum (Score {score:.1f}/{threshold:.0f}, "
                        f"{trend.upper()} trend). Eligible to add incremental scale-in order."
                    )
                    urgency = "medium"

            analyses.append({
                "ticket": ticket,
                "symbol": raw_sym,
                "canonical_symbol": canon_sym,
                "side": canonical_side,
                "volume": volume,
                "entry_price": entry_px,
                "current_price": curr_px,
                "bid_price": bid_px,
                "ask_price": ask_px,
                "spread": spread,
                "spread_r": spread_r,
                "stop_loss": sl,
                "take_profit": tp,
                "unrealized_pnl": profit,
                "r_multiple": r_multiple,
                "mfe": cur_mfe,
                "mae": cur_mae,
                "triple_barrier": {
                    "upper_barrier_r": 2.0,
                    "lower_barrier_r": -1.0,
                    "vertical_barrier_sec": vertical_barrier_sec,
                    "vertical_elapsed_pct": min(100.0, round((holding_sec / vertical_barrier_sec) * 100.0, 1)),
                },
                "stop_distance": round(stop_dist, 4 if "EUR" in canon_sym else 2),
                "action": action,
                "action_type": action_type,
                "reason": reason,
                "urgency": urgency,
                "can_scale_in": can_scale_in,
                "strategy_name": alloc.get("strategy_name", "Adaptive M15"),
                "trend": trend,
                "holding_seconds": int(holding_sec),
                "breathing_window_sec": int(breathing_sec),
                "in_breathing_window": in_breathing_window,
                "session": session_name,
                "bar_close_confirmed": bar_close_confirmed,
                "timestamp": datetime.now(UTC).isoformat(),
            })

        # Housekeeping: prune records for closed tickets
        stale_tickets = set(self._ticket_first_seen.keys()) - active_tickets
        for st in stale_tickets:
            self._ticket_first_seen.pop(st, None)
            self._ticket_mfe.pop(st, None)
            self._ticket_mae.pop(st, None)
            self._ticket_invalidation_ticks.pop(st, None)
            self._ticket_invalidation_start.pop(st, None)

        return analyses

    def get_post_loss_cooldown(self, asset: str) -> float:
        """Return remaining post-loss cooldown in seconds (0.0 if not in cooldown)."""
        canon = asset.upper().rstrip("M")
        last_loss = self._post_loss_cooldown.get(canon, 0.0)
        cooldown_duration = 5400.0 if canon in ("BTCUSD", "EURUSD") else 3600.0  # 90 mins for BTC/EUR, 60 mins for others
        elapsed = time.time() - last_loss
        if elapsed < cooldown_duration:
            return cooldown_duration - elapsed
        return 0.0

    async def execute_action(self, ticket: int | str, action: str | None = None) -> dict[str, Any]:
        """
        Execute an action on a specific ticket (close ticket or fire scale-in).
        """
        analyses = await self.evaluate_open_positions()
        pos_analysis = next((a for a in analyses if str(a["ticket"]) == str(ticket)), None)

        if not pos_analysis and not action:
            return {"ok": False, "error": "ticket_not_found", "ticket": ticket}

        target_action = action or (pos_analysis["action"] if pos_analysis else "CLOSE")

        if target_action in ("CLOSE_TAKE_PROFIT", "CLOSE_DEFENSIVE", "CLOSE_PRE_NEWS", "CLOSE", "TRAIL_EXIT", "CLOSE_ALPHA_DECAY", "CLOSE_TRAIL_EXIT"):
            logger.info("OrderLifecycleAgent executing CLOSE on ticket #%s: action=%s", ticket, target_action)
            res = await self.order_manager.close_ticket(ticket)
            # Prune cached metrics for closed ticket
            t_str = str(ticket)
            self._ticket_first_seen.pop(t_str, None)
            self._ticket_mfe.pop(t_str, None)
            self._ticket_mae.pop(t_str, None)
            self._ticket_invalidation_ticks.pop(t_str, None)
            self._ticket_invalidation_start.pop(t_str, None)

            # Record post-loss cooldown on the asset to prevent whiplash churning
            if pos_analysis:
                canon_asset = pos_analysis.get("canonical_symbol", "")
                r_mult = float(pos_analysis.get("r_multiple", 0.0))
                pnl = float(pos_analysis.get("unrealized_pnl", 0.0))
                if target_action in ("CLOSE_DEFENSIVE", "CLOSE_ALPHA_DECAY") or pnl < 0 or r_mult < 0:
                    self._post_loss_cooldown[canon_asset] = time.time()
                    duration_min = 90 if canon_asset in ("BTCUSD", "EURUSD") else 60
                    logger.warning(
                        "[Post-Loss Cooldown] Set %d-min re-entry lockout on %s after losing exit (%s, PnL: $%.2f, R: %.2f)",
                        duration_min, canon_asset, target_action, pnl, r_mult
                    )

            return {
                "ok": res.get("ok", False),
                "action": target_action,
                "ticket": ticket,
                "result": res,
                "message": f"Successfully closed ticket #{ticket} ({target_action})",
            }

        elif target_action == "SCALE_IN":
            if not pos_analysis:
                return {"ok": False, "error": "cannot_scale_in_unknown_ticket", "ticket": ticket}
            asset = pos_analysis["canonical_symbol"]
            side = pos_analysis["side"]
            logger.info("OrderLifecycleAgent executing SCALE_IN on %s #%s (%s)", asset, ticket, side)
            scale_res = await order_decision_agent.fire_order(asset=asset, side=side, force=True)
            return {
                "ok": scale_res.get("ok", False),
                "action": "SCALE_IN",
                "ticket": ticket,
                "scale_in_order": scale_res,
                "message": f"Scale-in order submitted for {asset} ({side.upper()}) alongside ticket #{ticket}",
            }

        return {
            "ok": True,
            "action": target_action,
            "ticket": ticket,
            "analysis": pos_analysis,
            "message": f"Action {target_action} recorded for ticket #{ticket}.",
        }

    async def run_lifecycle_management_tick(self, auto_close: bool = False) -> list[dict[str, Any]]:
        """
        Autonomous periodic check called by the engine loop.
        Monitors all positions and optionally auto-executes high-urgency closures.
        """
        evaluations = await self.evaluate_open_positions()
        if auto_close:
            for ev in evaluations:
                if ev["action"] in ("CLOSE_TAKE_PROFIT", "CLOSE_DEFENSIVE", "CLOSE_ALPHA_DECAY", "CLOSE_TRAIL_EXIT") and ev["urgency"] in ("high", "medium"):
                    logger.warning(
                        "[OrderLifecycleAgent Auto-Cut] Ticket #%s (%s %s) triggered %s: %s",
                        ev["ticket"], ev["canonical_symbol"], ev["side"], ev["action"], ev["reason"]
                    )
                    await self.execute_action(ev["ticket"], ev["action"])
        return evaluations


# Global singleton lifecycle agent
order_lifecycle_agent = OrderLifecycleAgent()

