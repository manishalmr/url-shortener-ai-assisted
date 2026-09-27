"""
In-process fixed-window rate limiter.

Chosen over a token-bucket implementation for simplicity/readability given
the assignment's time-box; the interface is small enough to swap for a
Redis-backed sliding-window limiter later without touching call sites
(see docs/testing-and-limitations.md).
"""
import time
from threading import Lock


class FixedWindowRateLimiter:
    def __init__(self, limit_per_minute: int):
        self._limit = limit_per_minute
        self._window_seconds = 60
        self._lock = Lock()
        # key -> (window_start_epoch, count)
        self._counters: dict[str, tuple[float, int]] = {}

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            window_start, count = self._counters.get(key, (now, 0))
            if now - window_start >= self._window_seconds:
                window_start, count = now, 0
            count += 1
            self._counters[key] = (window_start, count)
            return count <= self._limit

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
