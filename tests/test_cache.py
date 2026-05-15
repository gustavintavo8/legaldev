import pytest

from app.cache import _TTLCache, clear, get, make_key
from app.cache import set as cache_set


def test_set_and_get_basic():
    cache = _TTLCache(maxsize=10, ttl=60)
    cache.set("key1", "value1")
    assert cache.get("key1") == "value1"


def test_get_returns_none_for_missing_key():
    cache = _TTLCache(maxsize=10, ttl=60)
    assert cache.get("nonexistent") is None


def test_ttl_expiry(monkeypatch):
    t = [0.0]
    monkeypatch.setattr("app.cache.time.monotonic", lambda: t[0])

    cache = _TTLCache(maxsize=10, ttl=1.0)
    cache.set("key", "value")
    assert cache.get("key") == "value"

    t[0] = 1.5  # past TTL
    assert cache.get("key") is None


def test_ttl_not_expired_within_window(monkeypatch):
    t = [0.0]
    monkeypatch.setattr("app.cache.time.monotonic", lambda: t[0])

    cache = _TTLCache(maxsize=10, ttl=1.0)
    cache.set("key", "value")
    t[0] = 0.9  # still within TTL
    assert cache.get("key") == "value"


def test_eviction_removes_oldest_when_full(monkeypatch):
    t = [0.0]
    monkeypatch.setattr("app.cache.time.monotonic", lambda: t[0])

    cache = _TTLCache(maxsize=2, ttl=60)
    t[0] = 1.0
    cache.set("key1", "value1")
    t[0] = 2.0
    cache.set("key2", "value2")
    t[0] = 3.0
    cache.set("key3", "value3")  # evicts key1 (oldest timestamp)

    assert cache.get("key1") is None
    assert cache.get("key2") == "value2"
    assert cache.get("key3") == "value3"


def test_clear_removes_all_entries():
    cache = _TTLCache(maxsize=10, ttl=60)
    cache.set("key1", "v1")
    cache.set("key2", "v2")
    cache.clear()
    assert cache.get("key1") is None
    assert cache.get("key2") is None


def test_set_overwrites_existing_key():
    cache = _TTLCache(maxsize=10, ttl=60)
    cache.set("key", "original")
    cache.set("key", "updated")
    assert cache.get("key") == "updated"


def test_module_level_get_set_clear():
    clear()
    cache_set("k", "v")
    assert get("k") == "v"
    clear()
    assert get("k") is None


def test_make_key_is_deterministic():
    assert make_key("payload") == make_key("payload")


def test_make_key_differs_for_different_payloads():
    assert make_key("payload_a") != make_key("payload_b")
