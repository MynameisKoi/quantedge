"""Bayesian hyperparameter optimization with walk-forward validation."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def walk_forward_sharpe(returns: np.ndarray) -> float:
    if returns.size < 2:
        return 0.0
    std = float(returns.std(ddof=1))
    if std == 0:
        return 0.0
    return float(returns.mean() / std * np.sqrt(252))


class BayesianOptimizer:
    """Thin wrapper around scikit-optimize for strategy params."""

    def __init__(self, space: list[Any], n_calls: int = 30) -> None:
        self.space = space
        self.n_calls = n_calls

    def optimize(
        self,
        objective: Callable[[list[Any]], float],
    ) -> dict[str, Any]:
        try:
            from skopt import gp_minimize
        except ImportError as exc:
            raise RuntimeError("scikit-optimize is required for BayesianOptimizer") from exc

        result = gp_minimize(
            objective,
            self.space,
            n_calls=self.n_calls,
            random_state=42,
        )
        logger.info("Bayesian opt best score=%.4f params=%s", -result.fun, result.x)
        return {"best_params": result.x, "best_score": float(-result.fun)}
