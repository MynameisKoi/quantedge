from datetime import UTC, datetime

from fastapi import APIRouter

from macro.regime_classifier import regime_classifier
from strategies.registry import load_strategies

router = APIRouter()


@router.get("/signals")
async def list_signals():
    regime = regime_classifier.current.name
    payload = {
        "regime": regime,
        "as_of": datetime.now(UTC).isoformat(),
        "signals": [],
    }
    for strategy in load_strategies():
        computed = strategy.compute_signals({"regime": regime})
        for asset, signal in computed.items():
            payload["signals"].append(
                {
                    "strategy": strategy.name,
                    "asset": asset,
                    **signal,
                }
            )
    return payload
