"""Trade experience replay and journal memory for reinforcement learning."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class TradeExperience:
    trade_id: str
    asset: str
    strategy: str
    state_key: str  # Discretized state string e.g. "XAUUSD|stagflation|bullish_trend|pullback|m5_break"
    action: str  # "execute_full", "execute_scaled", "skip"
    side: str  # "long" or "short"
    entry_price: float
    exit_price: float = 0.0
    r_multiple: float = 0.0
    realized_pnl: float = 0.0
    spread_cost: float = 0.0
    duration_sec: float = 0.0
    reward: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    closed: bool = False

    def compute_reward(self, risk_amount: float = 100.0) -> float:
        """
        Compute RL reward based on realized R-multiple, spread friction, and asymmetric payoff.
        R >= +2.0R -> high positive reward (+2.5)
        R <= -1.0R -> negative penalty (-1.0)
        Spread drag deducted proportionally.
        """
        if risk_amount <= 0:
            risk_amount = 100.0
        r_mult = self.realized_pnl / risk_amount if self.realized_pnl != 0 else self.r_multiple
        spread_drag = (self.spread_cost / risk_amount) if risk_amount > 0 else 0.0

        # Base reward is the R-multiple minus spread friction
        base_reward = r_mult - (spread_drag * 0.5)

        # Asymmetric bonus for big winners (let winners run)
        if r_mult >= 2.0:
            base_reward += 0.5
        elif r_mult < -1.0:
            base_reward -= 0.5

        self.reward = round(base_reward, 4)
        return self.reward


class TradeMemory:
    """In-memory and persisted experience replay buffer."""

    def __init__(self, persistence_path: str | None = None) -> None:
        self.path = Path(persistence_path or settings.rl_memory_file)
        self.experiences: list[TradeExperience] = []
        self._active_trades: dict[str, TradeExperience] = {}
        self.load()

    def record_entry(
        self,
        trade_id: str,
        asset: str,
        strategy: str,
        state_key: str,
        action: str,
        side: str,
        entry_price: float,
        spread_cost: float = 0.0,
    ) -> TradeExperience:
        exp = TradeExperience(
            trade_id=trade_id,
            asset=asset,
            strategy=strategy,
            state_key=state_key,
            action=action,
            side=side,
            entry_price=entry_price,
            spread_cost=spread_cost,
        )
        self._active_trades[trade_id] = exp
        return exp

    def record_exit(
        self,
        trade_id: str,
        exit_price: float,
        realized_pnl: float,
        risk_amount: float = 100.0,
        duration_sec: float = 0.0,
    ) -> TradeExperience | None:
        exp = self._active_trades.pop(trade_id, None)
        if exp is None:
            # Check if already in closed experiences
            for item in reversed(self.experiences):
                if item.trade_id == trade_id and not item.closed:
                    exp = item
                    break
        if exp is None:
            return None

        exp.exit_price = exit_price
        exp.realized_pnl = realized_pnl
        exp.duration_sec = duration_sec
        exp.closed = True
        exp.compute_reward(risk_amount=risk_amount)

        self.experiences.append(exp)
        self.save()
        logger.info(
            "RL Trade Experience recorded: id=%s asset=%s state=%s reward=%.3f pnl=%.2f",
            exp.trade_id,
            exp.asset,
            exp.state_key,
            exp.reward,
            exp.realized_pnl,
        )
        try:
            from core.rl.trade_learner import rl_policy
            rl_policy.learn_from_trade(exp)
        except Exception as e:
            logger.debug("Failed notifying RL policy from record_exit: %s", e)
        return exp

    def get_recent(self, n: int = 50) -> list[TradeExperience]:
        return self.experiences[-n:]

    def summary(self) -> dict[str, Any]:
        closed = [e for e in self.experiences if e.closed]
        if not closed:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "avg_reward": 0.0,
                "total_pnl": 0.0,
                "active_trades": len(self._active_trades),
            }
        wins = sum(1 for e in closed if e.realized_pnl > 0)
        total_pnl = sum(e.realized_pnl for e in closed)
        avg_reward = sum(e.reward for e in closed) / len(closed)
        return {
            "total_trades": len(closed),
            "win_rate": round(wins / len(closed) * 100, 2),
            "avg_reward": round(avg_reward, 3),
            "total_pnl": round(total_pnl, 2),
            "active_trades": len(self._active_trades),
        }

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = [asdict(e) for e in self.experiences]
            self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as err:
            logger.warning("Failed to save RL trade memory: %s", err)

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            content = self.path.read_text(encoding="utf-8")
            raw = json.loads(content)
            self.experiences = [TradeExperience(**item) for item in raw]
            logger.info("Loaded %d RL trade experiences from %s", len(self.experiences), self.path)
        except Exception as err:
            logger.warning("Failed to load RL trade memory from %s: %s", self.path, err)


trade_memory = TradeMemory()
