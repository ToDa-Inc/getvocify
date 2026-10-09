"""A small time-bounded cache for values that are read far more often than they change."""

from __future__ import annotations

import threading
import time
from typing import Callable, Generic, Hashable, Optional, TypeVar

V = TypeVar("V")


class TtlCache(Generic[V]):
    """Thread-safe key -> value cache whose entries expire `ttl_s` seconds after being stored.

    Only what the caller stores is kept: a lookup that failed is simply not stored, so the next
    read tries again. `clock` is injectable so expiry is testable without sleeping."""

    def __init__(self, ttl_s: float, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl_s = ttl_s
        self._clock = clock
        self._lock = threading.Lock()
        self._items: dict[Hashable, tuple[float, V]] = {}

    def get(self, key: Hashable) -> Optional[V]:
        with self._lock:
            hit = self._items.get(key)
            if hit is None:
                return None
            stored_at, value = hit
            if self._clock() - stored_at > self._ttl_s:
                del self._items[key]
                return None
            return value

    def put(self, key: Hashable, value: V) -> None:
        with self._lock:
            self._items[key] = (self._clock(), value)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
