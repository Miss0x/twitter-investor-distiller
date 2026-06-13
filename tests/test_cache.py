"""Tests for distributed cache layer."""
from src.storage.cache import MemoryCache, get_cache


def test_memory_cache_set_get():
    mc = MemoryCache()
    mc.set("test", {"value": 42}, ttl=999)
    assert mc.get("test") == {"value": 42}


def test_memory_cache_expiry():
    mc = MemoryCache()
    mc.set("expired", "x", ttl=-1)  # immediate expiry
    assert mc.get("expired") is None


def test_memory_cache_delete():
    mc = MemoryCache()
    mc.set("del", "y")
    mc.delete("del")
    assert mc.get("del") is None


def test_memory_cache_exists():
    mc = MemoryCache()
    mc.set("exists_test", "z")
    assert mc.exists("exists_test")
    assert not mc.exists("nonexistent")


def test_memory_cache_ping():
    assert MemoryCache().ping() is True


def test_get_cache_returns_memory_when_no_redis():
    import os
    old = os.environ.pop("REDIS_URL", None)
    from src.storage.cache import _cache
    _cache = None
    try:
        c = get_cache()
        assert c.ping() is True  # memory cache always pings
    finally:
        if old:
            os.environ["REDIS_URL"] = old
