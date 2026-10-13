"""A short-lived cache for approval previews, with one build shared by concurrent callers.

A preview is worth caching only briefly: it is built from the memo and from the CRM's current
values. The key therefore carries a fingerprint of the whole memo row, so any change to the memo
(a re-extraction, a retype, an approval) is a different key and nothing stale is ever served for
it; the TTL bounds how long a CRM-side edit can go unseen.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Generic, Hashable, Optional, TypeVar

T = TypeVar("T")

# Changing constantly and read by nothing a preview shows.
_VOLATILE_MEMO_KEYS = frozenset({
    "pipeline_meta",
    "pipeline_run_id",
    "pipeline_run_started_at",
    "followup",
    "recording_path",
    "audio_url",
    "audio_duration",
})


def memo_fingerprint(memo: dict[str, Any]) -> str:
    """Identifies this state of the memo: every column except the volatile ones above."""
    stable = {key: value for key, value in memo.items() if key not in _VOLATILE_MEMO_KEYS}
    raw = json.dumps(stable, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


class PreviewCache(Generic[T]):
    """Key -> value for `ttl_s` seconds, at most `max_entries` of them (least recently used out).

    `get_or_build` runs `build` once per key at a time: callers that arrive while it runs wait for
    that same result. A build that fails stores nothing and fails for everyone waiting on it;
    one caller giving up does not cancel the build for the others."""

    def __init__(
        self,
        ttl_s: float = 90.0,
        max_entries: int = 64,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_s = ttl_s
        self._max_entries = max_entries
        self._clock = clock
        self._items: "OrderedDict[Hashable, tuple[float, T]]" = OrderedDict()
        self._inflight: dict[Hashable, "asyncio.Future[T]"] = {}

    def _fresh(self, key: Hashable) -> Optional[T]:
        hit = self._items.get(key)
        if hit is None:
            return None
        stored_at, value = hit
        if self._clock() - stored_at > self._ttl_s:
            del self._items[key]
            return None
        self._items.move_to_end(key)
        return value

    def _store(self, key: Hashable, value: T) -> None:
        self._items[key] = (self._clock(), value)
        self._items.move_to_end(key)
        while len(self._items) > self._max_entries:
            self._items.popitem(last=False)

    async def _build(self, key: Hashable, build: Callable[[], Awaitable[T]]) -> T:
        try:
            value = await build()
            self._store(key, value)
            return value
        finally:
            self._inflight.pop(key, None)

    async def get_or_build(self, key: Hashable, build: Callable[[], Awaitable[T]]) -> T:
        value = self._fresh(key)
        if value is not None:
            return value
        pending = self._inflight.get(key)
        if pending is None:
            pending = asyncio.ensure_future(self._build(key, build))
            self._inflight[key] = pending
        return await asyncio.shield(pending)

    def clear(self) -> None:
        self._items.clear()
