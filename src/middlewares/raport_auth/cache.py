"""Shared TTL cache for authorization answers.

Redis so that all uvicorn workers and all replicas share one answer per user; an in-process
dict as a fallback, because a cache outage must not take authentication down with it. The cache
is an optimisation, so failures here are swallowed — unlike failures of Raport itself.
"""

import json
import time
from typing import Any, Optional

from src.config.logger import LoggerProvider

log = LoggerProvider().get_logger(__name__)

# Bound on the in-process fallback; irrelevant while Redis is up.
_LOCAL_LIMIT = 2000


class AuthCache:
    """`key -> payload` with a TTL, backed by Redis when it is reachable."""

    def __init__(self, redis_client: Any = None, prefix: str = "raport-auth:") -> None:
        self._redis = redis_client
        self._prefix = prefix
        self._local: dict[str, tuple[float, Any]] = {}
        self._redis_broken = False

    async def get(self, key: str) -> Optional[Any]:
        if self._redis is not None and not self._redis_broken:
            try:
                raw = await self._redis.get(self._prefix + key)
                return json.loads(raw) if raw else None
            except Exception as e:  # noqa: BLE001 — any Redis failure degrades to the local cache
                self._on_redis_failure(e)
        return self._local_get(key)

    async def set(self, key: str, value: Any, ttl: int) -> None:
        if ttl <= 0:
            return
        if self._redis is not None and not self._redis_broken:
            try:
                await self._redis.set(self._prefix + key, json.dumps(value), ex=ttl)
                return
            except Exception as e:  # noqa: BLE001
                self._on_redis_failure(e)
        self._local_set(key, value, ttl)

    async def delete(self, key: str) -> None:
        if self._redis is not None and not self._redis_broken:
            try:
                await self._redis.delete(self._prefix + key)
            except Exception as e:  # noqa: BLE001
                self._on_redis_failure(e)
        self._local.pop(key, None)

    def _on_redis_failure(self, error: Exception) -> None:
        # Logged once per process: a broken Redis would otherwise fill the log on every request.
        if not self._redis_broken:
            log.warning(f"Redis is unavailable, auth cache falls back to the process-local one: {error}")
        self._redis_broken = True

    def _local_get(self, key: str) -> Optional[Any]:
        entry = self._local.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at <= time.time():
            self._local.pop(key, None)
            return None
        return value

    def _local_set(self, key: str, value: Any, ttl: int) -> None:
        now = time.time()
        if len(self._local) >= _LOCAL_LIMIT:
            for stale in [k for k, (expires_at, _) in self._local.items() if expires_at <= now]:
                self._local.pop(stale, None)
            if len(self._local) >= _LOCAL_LIMIT:
                self._local.clear()
        self._local[key] = (now + ttl, value)

    def clear(self) -> None:
        """Drop the local half of the cache — used by tests."""
        self._local.clear()
        self._redis_broken = False
