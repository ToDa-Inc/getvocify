"""In-process TTL cache + singleflight for identical in-flight async work."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")


class CoalesceCache:
    def __init__(self, ttl_seconds: float = 30.0):
        self.ttl = ttl_seconds
        self._values: dict[str, tuple[float, Any]] = {}
        self._inflight: dict[str, asyncio.Task] = {}

    async def get_or_set(self, key: str, factory: Callable[[], Awaitable[T]]) -> T:
        now = time.monotonic()
        hit = self._values.get(key)
        if hit and now < hit[0]:
            return hit[1]
        task = self._inflight.get(key)
        if task is None:
            task = asyncio.create_task(factory())
            self._inflight[key] = task
            try:
                value = await task
                self._values[key] = (time.monotonic() + self.ttl, value)
                return value
            finally:
                if self._inflight.get(key) is task:
                    del self._inflight[key]
        return await task
