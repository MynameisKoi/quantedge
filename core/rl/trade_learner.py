"""Contextual Bandit / Q-Learning policy for adaptive trade execution and sizing."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import random
from typing import Any

from config.settings import settings
from core.rl.trade_memory import TradeExperience, trade_memory

logger = logging.getLogger(__name__)

ACTIONS = ["execute_full", "execute_scaled", "skip"]

STRATEGY_ARCHETYPES = [
    "momentum_impulse",     # High ADX (>=22), rides EMA 9 impulse without waiting for deep retracements
    "value_pullback",       # Moderate ADX, value zone pullback tap into EMA 21 / EMA 50
    "volatility_breakout",  # High ATR / consolidation expansion, channel breakout
    "mean_revert",          # Low ADX (<20), Bollinger Band liquidity sweep & RSI exhaustion
]


class TradeRLPolicy:
    """Adaptive RL policy that scores setups, chooses optimal strategy archetypes, and adapts sizing from trade outcomes and missed opportunities."""

    def __init__(
        self,
        learning_rate: float | None = None,
        exploration_rate: float | None = None,
        policy_file: str | Path | None = None,
    ) -> None:
        self.alpha = learning_rate or settings.rl_learning_rate
        self.epsilon = exploration_rate or settings.rl_exploration_rate
        self.policy_file = Path(policy_file or "data/rl_policy_state.json")
        # Q-table: state_key -> {action: q_value}
        self.q_table: dict[str, dict[str, float]] = {}
        self.action_counts: dict[str, dict[str, int]] = {}
        # Strategy selection Q-table: state_key -> {archetype: q_value}
        self.strategy_q_table: dict[str, dict[str, float]] = {}
        self.strategy_counts: dict[str, dict[str, int]] = {}
        if not self.load_policy():
            self._bootstrap_from_memory()

    def build_strategy_state_key(
        self,
        asset: str,
        regime: str,
        adx: float,
        atr_pct: float,
    ) -> str:
        """Discretized state signature for strategy archetype selection."""
        adx_tier = "trending_strong" if adx >= 28.0 else ("trending_moderate" if adx >= 20.0 else "ranging_chop")
        vol_tier = "high_vol" if atr_pct >= 0.008 else "normal_vol"
        return f"{asset}|{regime}|{adx_tier}|{vol_tier}"

    def _get_strategy_q_values(self, state_key: str, adx: float = 20.0) -> dict[str, float]:
        if state_key not in self.strategy_q_table:
            # Informed Bayesian prior based on quantitative principles:
            # Strong trend -> momentum & pullback favored; ranging -> mean revert & breakout
            if "trending_strong" in state_key:
                priors = {
                    "momentum_impulse": 0.45,
                    "value_pullback": 0.30,
                    "volatility_breakout": 0.25,
                    "mean_revert": -0.40,
                }
            elif "trending_moderate" in state_key:
                priors = {
                    "value_pullback": 0.40,
                    "momentum_impulse": 0.30,
                    "volatility_breakout": 0.20,
                    "mean_revert": 0.05,
                }
            else:  # ranging_chop
                priors = {
                    "mean_revert": 0.40,
                    "volatility_breakout": 0.25,
                    "value_pullback": 0.10,
                    "momentum_impulse": -0.20,
                }
            self.strategy_q_table[state_key] = priors.copy()
            self.strategy_counts[state_key] = {a: 0 for a in STRATEGY_ARCHETYPES}
        return self.strategy_q_table[state_key]

    def select_strategy(
        self,
        asset: str,
        regime: str,
        adx: float,
        atr_pct: float = 0.005,
        explore: bool = True,
    ) -> dict[str, Any]:
        """
        Dynamically select the optimal strategy archetype using Contextual Bandit Q-values.
        Returns:
            - selected_strategy: best archetype name
            - q_values: candidate archetype expected rewards
            - state_key: state signature
            - confidence: softmax/margin confidence score
            - exploration: whether choice was an exploration
        """
        state_key = self.build_strategy_state_key(asset, regime, adx, atr_pct)
        q_vals = self._get_strategy_q_values(state_key, adx=adx)

        is_exploration = False
        if explore and random.random() < self.epsilon:
            chosen = random.choice(STRATEGY_ARCHETYPES)
            is_exploration = True
        else:
            chosen = max(q_vals, key=lambda a: q_vals[a])

        sorted_candidates = sorted(
            [{"archetype": a, "q_value": round(q, 3), "samples": self.strategy_counts[state_key].get(a, 0)} for a, q in q_vals.items()],
            key=lambda x: x["q_value"],
            reverse=True,
        )

        return {
            "selected_strategy": chosen,
            "q_values": {a: round(q, 3) for a, q in q_vals.items()},
            "candidates": sorted_candidates,
            "state_key": state_key,
            "exploration": is_exploration,
            "top_q": round(q_vals[chosen], 3),
        }

    def learn_from_missed_opportunity(
        self,
        asset: str,
        regime: str,
        adx: float,
        move_r: float,
        optimal_archetype: str,
    ) -> None:
        """
        Penalize strategies that caused starvation during large moves, and boost optimal archetype.
        """
        state_key = self.build_strategy_state_key(asset, regime, adx, 0.005)
        q_vals = self._get_strategy_q_values(state_key, adx=adx)
        
        # Boost optimal archetype
        old_q = q_vals.get(optimal_archetype, 0.0)
        reward = min(2.0, max(0.5, move_r * 0.5))
        new_q = old_q + self.alpha * (reward - old_q)
        q_vals[optimal_archetype] = round(new_q, 4)
        self.strategy_counts[state_key][optimal_archetype] = self.strategy_counts[state_key].get(optimal_archetype, 0) + 1

        # Penalize over-restrictive counter-trend or sleeping archetypes in this state
        for arch in STRATEGY_ARCHETYPES:
            if arch != optimal_archetype:
                q_vals[arch] = round(q_vals[arch] - (self.alpha * 0.2), 4)

        self.save_policy()
        logger.info(
            "RL Policy Adapted from Missed Opportunity: state=%s boosted=%s (+%.2f) new_Q=%.3f",
            state_key,
            optimal_archetype,
            reward,
            new_q,
        )

    def build_state_key(
        self,
        asset: str,
        regime: str,
        htf_trend: str,
        mtf_setup: str,
        micro_trigger: str,
    ) -> str:
        """Create a consistent discretized state signature."""
        return f"{asset}|{regime}|{htf_trend}|{mtf_setup}|{micro_trigger}"

    def _get_q_values(self, state_key: str) -> dict[str, float]:
        if state_key not in self.q_table:
            # Default prior: small positive expectation for full execution
            self.q_table[state_key] = {
                "execute_full": 0.2,
                "execute_scaled": 0.1,
                "skip": 0.0,
            }
            self.action_counts[state_key] = {a: 0 for a in ACTIONS}
        return self.q_table[state_key]

    def evaluate_setup(
        self,
        asset: str,
        regime: str,
        htf_trend: str,
        mtf_setup: str,
        micro_trigger: str,
        raw_score: float = 65.0,
        explore: bool = True,
    ) -> dict[str, Any]:
        """
        Evaluate candidate setup and return policy decision.
        Returns:
            - approved (bool): whether policy allows order
            - action (str): execute_full, execute_scaled, or skip
            - size_multiplier (float): 1.0 (full), 0.5 (scaled), 0.0 (skip)
            - adjusted_score (float): raw score modulated by RL expected value
            - q_value (float): expected reward
            - state_key (str): state signature
        """
        if not settings.rl_enabled:
            return {
                "approved": True,
                "action": "execute_full",
                "size_multiplier": 1.0,
                "adjusted_score": raw_score,
                "q_value": 0.0,
                "state_key": "rl_disabled",
                "reasoning": "RL disabled in settings; standard execution",
            }

        state_key = self.build_state_key(asset, regime, htf_trend, mtf_setup, micro_trigger)
        q_values = self._get_q_values(state_key)

        # Exploration check (epsilon-greedy)
        if explore and random.random() < self.epsilon:
            action = random.choice(ACTIONS)
            reasoning = f"RL Exploration ({action}) for state {state_key}"
        else:
            # Greedy choice
            action = max(q_values, key=lambda a: q_values[a])
            q_best = q_values[action]
            reasoning = f"RL Policy {action} (Q={q_best:.2f}) for state {state_key}"

        size_mult = 1.0 if action == "execute_full" else (0.5 if action == "execute_scaled" else 0.0)
        approved = action != "skip"

        # Modulate score with expected value (Q-value): +/- 10 points
        expected_r = q_values[action]
        adjusted_score = min(100.0, max(0.0, raw_score + (expected_r * 5.0)))

        return {
            "approved": approved,
            "action": action,
            "size_multiplier": size_mult,
            "adjusted_score": round(adjusted_score, 1),
            "q_value": round(expected_r, 3),
            "state_key": state_key,
            "reasoning": reasoning,
        }

    def save_policy(self) -> None:
        """Persist learned Q-tables and sample counts to disk."""
        try:
            self.policy_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "q_table": self.q_table,
                "action_counts": self.action_counts,
                "strategy_q_table": self.strategy_q_table,
                "strategy_counts": self.strategy_counts,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(self.policy_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning("Failed saving RL policy: %s", e)

    def load_policy(self) -> bool:
        """Load persisted Q-tables from disk if available."""
        if not self.policy_file.exists():
            return False
        try:
            with open(self.policy_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.q_table = data.get("q_table", {})
            self.action_counts = data.get("action_counts", {})
            self.strategy_q_table = data.get("strategy_q_table", {})
            self.strategy_counts = data.get("strategy_counts", {})
            if self.q_table or self.strategy_q_table:
                logger.info("Loaded persisted RL policy: %d action states, %d strategy states", len(self.q_table), len(self.strategy_q_table))
                return True
            return False
        except Exception as e:
            logger.warning("Failed loading persisted RL policy: %s", e)
            return False

    def learn_from_strategy_outcome(
        self,
        asset: str,
        regime: str,
        adx: float,
        atr_pct: float,
        archetype: str,
        reward: float,
    ) -> None:
        """Directly update the strategy archetype Contextual Bandit from a realized trade outcome."""
        if not settings.rl_enabled or archetype not in STRATEGY_ARCHETYPES:
            return

        state_key = self.build_strategy_state_key(asset, regime, adx, atr_pct)
        q_vals = self._get_strategy_q_values(state_key, adx=adx)
        old_q = q_vals.get(archetype, 0.0)

        # Bandit temporal difference update: Q(s,a) = Q(s,a) + alpha * (reward - Q(s,a))
        new_q = old_q + self.alpha * (reward - old_q)
        q_vals[archetype] = round(new_q, 4)
        self.strategy_counts[state_key][archetype] = self.strategy_counts[state_key].get(archetype, 0) + 1

        self.save_policy()
        logger.info(
            "RL Strategy Q-Table Updated: state=%s archetype=%s reward=%.3f old_Q=%.3f new_Q=%.3f (samples=%d)",
            state_key,
            archetype,
            reward,
            old_q,
            new_q,
            self.strategy_counts[state_key][archetype],
        )

    def learn_from_trade(self, experience: TradeExperience) -> None:
        """Update Q-values from completed trade outcome."""
        if not settings.rl_enabled or not experience.closed:
            return

        state_key = experience.state_key
        action = experience.action
        reward = experience.reward

        q_values = self._get_q_values(state_key)
        old_q = q_values.get(action, 0.0)

        # Temporal difference / bandit update: Q(s,a) = Q(s,a) + alpha * (reward - Q(s,a))
        new_q = old_q + self.alpha * (reward - old_q)
        q_values[action] = round(new_q, 4)
        self.action_counts[state_key][action] = self.action_counts[state_key].get(action, 0) + 1

        # Also update strategy archetype Q-table if state_key or strategy corresponds to archetype
        matched_archetype = None
        for a in STRATEGY_ARCHETYPES:
            if a in state_key or a in (experience.strategy or ""):
                matched_archetype = a
                break
        if matched_archetype:
            strat_state_key = self.build_strategy_state_key(experience.asset, "risk-on", 24.0, 0.005)
            sq_vals = self._get_strategy_q_values(strat_state_key)
            old_sq = sq_vals.get(matched_archetype, 0.0)
            new_sq = old_sq + self.alpha * (reward - old_sq)
            sq_vals[matched_archetype] = round(new_sq, 4)
            self.strategy_counts[strat_state_key][matched_archetype] = self.strategy_counts[strat_state_key].get(matched_archetype, 0) + 1

        self.save_policy()
        logger.info(
            "RL Policy Updated: state=%s action=%s reward=%.3f old_Q=%.3f new_Q=%.3f (samples=%d)",
            state_key,
            action,
            reward,
            old_q,
            new_q,
            self.action_counts[state_key][action],
        )

    def _bootstrap_from_memory(self) -> None:
        """Replay loaded memory and MT4 history on startup to reconstruct policy table."""
        for exp in trade_memory.experiences:
            if exp.closed:
                self.learn_from_trade(exp)

        # Also bootstrap strategy Q-table from historical MT4 closed trades if strategy_q_table is empty
        try:
            from execution.bridge.mt4_history_parser import mt4_history_parser
            closed_trades = mt4_history_parser.parse_closed_trades(days_back=14)
            for ct in closed_trades:
                pnl = float(ct.get("pnl", 0.0))
                sym = ct.get("symbol", "XAUUSD")
                reward = 2.0 if pnl > 0 else -1.0
                arch = "volatility_breakout" if sym in ("USOIL", "BTCUSD") else "value_pullback"
                strat_state = self.build_strategy_state_key(sym, "risk-on", 24.0, 0.005)
                sq = self._get_strategy_q_values(strat_state)
                old_q = sq.get(arch, 0.0)
                sq[arch] = round(old_q + self.alpha * (reward - old_q), 4)
                self.strategy_counts[strat_state][arch] = self.strategy_counts[strat_state].get(arch, 0) + 1
        except Exception as e:
            logger.debug("MT4 history bootstrap skipped: %s", e)

        self.save_policy()
        if self.q_table or self.strategy_q_table:
            logger.info("RL Policy bootstrapped: %d action states, %d strategy states", len(self.q_table), len(self.strategy_q_table))

    def get_policy_summary(self) -> dict[str, Any]:
        return {
            "total_states": len(self.q_table),
            "total_strategy_states": len(self.strategy_q_table),
            "learning_rate": self.alpha,
            "exploration_rate": self.epsilon,
            "strategy_q_table": self.strategy_q_table,
            "strategy_counts": self.strategy_counts,
            "memory_stats": trade_memory.summary(),
            "top_positive_states": sorted(
                [
                    {"state": s, "best_action": max(q, key=lambda a: q[a]), "best_q": max(q.values())}
                    for s, q in self.q_table.items()
                ],
                key=lambda x: x["best_q"],
                reverse=True,
            )[:5],
        }


rl_policy = TradeRLPolicy()
