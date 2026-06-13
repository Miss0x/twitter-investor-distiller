"""Distributed cache layer — Redis with in-memory fallback.

Provides:
- CacheInterface: abstract get/set/delete with TTL
- RedisCache: production Redis client
- MemoryCache: dev fallback (in-process dict)
- get_cache(): auto-selects Redis if available
"""

from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from typing import Any


class CacheInterface(ABC):
    @abstractmethod
    def get(self, key: str) -> Any | None: ...

    @abstractmethod
    def set(self, key: str, value: Any, ttl: int = 60) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def ping(self) -> bool: ...


class MemoryCache(CacheInterface):
    """In-process dict cache — dev fallback when Redis unavailable."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expire = entry
        if time.time() > expire:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: int = 60) -> None:
        self._store[key] = (value, time.time() + ttl)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    def ping(self) -> bool:
        return True


class RedisCache(CacheInterface):
    """Redis-backed distributed cache."""

    def __init__(self, url: str = "redis://localhost:6379/0") -> None:
        self.url = url
        self._client = None
        self._connected = False
        self._connect()

    def _connect(self) -> None:
        try:
            import redis
            self._client = redis.Redis.from_url(self.url, socket_connect_timeout=2, decode_responses=False)
            self._client.ping()
            self._connected = True
        except Exception:
            self._connected = False

    def get(self, key: str) -> Any | None:
        if not self._connected or self._client is None:
            return None
        try:
            raw = self._client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl: int = 60) -> None:
        if not self._connected or self._client is None:
            return
        try:
            self._client.setex(key, ttl, json.dumps(value, default=str))
        except Exception:
            pass

    def delete(self, key: str) -> None:
        if not self._connected or self._client is None:
            return
        try:
            self._client.delete(key)
        except Exception:
            pass

    def exists(self, key: str) -> bool:
        if not self._connected or self._client is None:
            return False
        try:
            return bool(self._client.exists(key))
        except Exception:
            return False

    def ping(self) -> bool:
        if not self._connected or self._client is None:
            return False
        try:
            return self._client.ping()  # type: ignore[no-any-return]
        except Exception:
            self._connected = False
            return False


# ── 全局单例 ──
_cache: CacheInterface | None = None


def get_cache() -> CacheInterface:
    """Auto-select Redis or fallback to MemoryCache."""
    global _cache
    if _cache is not None:
        return _cache

    redis_url = os.getenv("REDIS_URL", "")
    if redis_url:
        rc = RedisCache(redis_url)
        if rc.ping():
            _cache = rc
            return _cache

    _cache = MemoryCache()
    return _cache
