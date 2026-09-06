from strategies.adaptive.live_strategy import AdaptiveM15LiveStrategy
from strategies.base import BaseStrategy


def load_strategies() -> list[BaseStrategy]:
    """Production live strategies for Exness MT4."""
    return [
        AdaptiveM15LiveStrategy(),
    ]

