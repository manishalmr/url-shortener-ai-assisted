"""
Small in-process LRU+TTL cache used to keep the hot redirect path fast
without hitting the database on every click.

Explicitly scoped as a *single-instance* optimization - see
docs/testing-and-limitations.md for the multi-instance caveat and the
production recommendation (Redis) if this service is horizontally scaled.
"""
import time
from collections import OrderedDict
from threading import Lock
from typing import Any


class TTLLRUCache:
    def __init__(self, max_size: int, ttl_seconds: int):
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            value, expires_at = item
            if time.monotonic() >= expires_at:
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (value, time.monotonic() + self._ttl)
            while len(self._store) > self._max_size:
                self._store.popitem(last=False)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def __len__(self) -> int:
        return len(self._store)
