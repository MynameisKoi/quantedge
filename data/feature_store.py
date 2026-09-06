"""Redis-backed feature cache with in-memory fallback."""

from __future__ import annotations

import json
import logging
from typing import Any

from config.settings import settings

logger = logging.getLogger(__name__)


class FeatureStore:
    def __init__(self) -> None:
        self._memory: dict[str, Any] = {}
        self._redis = None

    def _client(self):
        if self._redis is not None:
            return self._redis
        try:
            import redis

            client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            client.ping()
            self._redis = client
            return self._redis
        except Exception:
            logger.warning("Redis unavailable — using in-memory feature store")
            return None

    def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        self._memory[key] = value
        client = self._client()
        if client is None:
            return
        client.setex(key, ttl_seconds, json.dumps(value, default=str))

    def get(self, key: str, default: Any = None) -> Any:
        client = self._client()
        if client is not None:
            raw = client.get(key)
            if raw is not None:
                return json.loads(raw)
        return self._memory.get(key, default)


feature_store = FeatureStore()
