"""Internal event bus for QuantEdge."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    MARKET_TICK = "market_tick"
    NEWS = "news"
    REGIME_CHANGE = "regime_change"
    SIGNAL = "signal"
    ORDER = "order"
    FILL = "fill"
    RISK_BREACH = "risk_breach"
    EMERGENCY_STOP = "emergency_stop"
    COPILOT = "copilot"


@dataclass(slots=True)
class Event:
    type: EventType
    payload: dict[str, Any]
    source: str = "system"
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


Handler = Callable[[Event], Awaitable[None] | None]


class EventBus:
    """Simple async pub/sub bus used by the engine and API."""

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Handler]] = defaultdict(list)
        self._history: list[Event] = []
        self._max_history = 500
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: Handler) -> None:
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    async def publish(self, event: Event) -> None:
        async with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history :]

        handlers = list(self._handlers.get(event.type, []))
        for handler in handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("Handler failed for %s", event.type)

    def recent(self, event_type: EventType | None = None, limit: int = 50) -> list[Event]:
        events = self._history if event_type is None else [
            e for e in self._history if e.type == event_type
        ]
        return events[-limit:]


# Process-wide bus shared by API and engine in single-process mode.
bus = EventBus()
