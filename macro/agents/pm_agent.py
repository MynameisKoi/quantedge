"""Portfolio Manager — synthesizes agent debate into a regime decision."""

from __future__ import annotations

from collections import Counter
from typing import Any

from config.settings import settings
from macro.agents.base import OpenAIAgent


class PortfolioManagerAgent(OpenAIAgent):
    name = "portfolio_manager"
    role = (
        "Synthesize hawkish, dovish, and commodity specialist debates into a single "
        "weighted Macro Regime decision for QuantEdge."
    )
    model = settings.primary_macro_model

    def synthesize(self, debates: list[dict[str, Any]]) -> dict[str, Any]:
        """Weighted vote over regime hints; works offline without OpenAI."""
        if not debates:
            return {
                "regime": "risk-on",
                "confidence": 0.0,
                "summary": "No agent input",
                "debates": [],
            }

        weights = {
            "hawkish": 1.0,
            "dovish": 1.0,
            "commodity_specialist": 0.8,
        }
        scores: Counter[str] = Counter()
        for d in debates:
            hint = d.get("regime_hint", "risk-on")
            conf = float(d.get("confidence", 0.5))
            w = weights.get(d.get("agent", ""), 1.0)
            scores[hint] += conf * w

        regime, raw = scores.most_common(1)[0]
        total = sum(scores.values()) or 1.0
        confidence = raw / total
        summary = "; ".join(
            f"{d['agent']}: {d.get('rationale', '')[:120]}" for d in debates
        )
        return {
            "regime": regime,
            "confidence": round(confidence, 3),
            "summary": summary,
            "debates": debates,
            "scores": dict(scores),
        }
