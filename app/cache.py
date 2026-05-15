import hashlib
import time
from typing import Any


class _TTLCache:
    def __init__(self, maxsize: int, ttl: float) -> None:
        self._maxsize = maxsize
        self._ttl = ttl
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, ts = entry
        if time.monotonic() - ts > self._ttl:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        if len(self._store) >= self._maxsize:
            oldest = min(self._store, key=lambda k: self._store[k][1])
            del self._store[oldest]
        self._store[key] = (value, time.monotonic())

    def clear(self) -> None:
        self._store.clear()


_response_cache = _TTLCache(maxsize=256, ttl=3600)


def make_key(payload: str) -> str:
    return hashlib.sha256(payload.encode()).hexdigest()


def get(key: str) -> Any | None:
    return _response_cache.get(key)


def set(key: str, value: Any) -> None:
    _response_cache.set(key, value)


def clear() -> None:
    _response_cache.clear()
