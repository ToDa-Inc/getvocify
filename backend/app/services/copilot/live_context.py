"""What live help reads before it writes a card, kept for a short time instead of read again for every card.

Each card used to read the rep's offer, the company's knowledge, the call type's playbook and the rep's timezone from
the database, one after another, on the server's event loop. That was the largest part of the time between "the turn
check said objection" and "the card is written" (0.4-2.8 s on a real call; the model itself takes 0.5-0.9 s).

Rules, so that this can never make live help wrong:
  * An entry lives COPILOT_CONTEXT_TTL_S seconds (0 turns the cache off: every read goes to the database, as before).
  * Only a read that SUCCEEDED is kept. A failed read gives the caller's fallback for that one request and is read
    again by the next (a transient database error is never remembered).
  * The key carries everything the value depends on (rep, company, call type). The call type is never decided here:
    it comes with each request, so a type changed mid-call simply reads (and then keeps) the new type's entry.
  * Publishing, pausing or restoring a playbook clears the company's playbooks at once (invalidate_company), so an
    edit is live on the next card in the same process; other processes catch up within the TTL.
  * Reads run in worker threads (never blocking the event loop) and the independent ones run at the same time.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Hashable, Optional

from fastapi.concurrency import run_in_threadpool

from app.config import settings

logger = logging.getLogger(__name__)

MAX_ENTRIES = 1000
_MISSING = object()


class TtlCache:
    """A small thread-safe cache with an expiry per entry and a bounded size (the oldest entries go first)."""

    def __init__(self, max_entries: int = MAX_ENTRIES) -> None:
        self._data: dict[Hashable, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._max = max_entries

    def get(self, key: Hashable, ttl_s: float) -> Any:
        with self._lock:
            found = self._data.get(key)
            if found is None:
                return _MISSING
            stored_at, value = found
            if time.monotonic() - stored_at >= ttl_s:
                del self._data[key]
                return _MISSING
            return value

    def put(self, key: Hashable, value: Any) -> None:
        with self._lock:
            if key not in self._data and len(self._data) >= self._max:
                oldest = min(self._data, key=lambda k: self._data[k][0])
                del self._data[oldest]
            self._data[key] = (time.monotonic(), value)

    def drop(self, matches: Callable[[Hashable], bool]) -> int:
        with self._lock:
            doomed = [key for key in self._data if matches(key)]
            for key in doomed:
                del self._data[key]
            return len(doomed)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


_cache = TtlCache()


def ttl_s() -> float:
    return float(settings.COPILOT_CONTEXT_TTL_S or 0)


@dataclass(frozen=True)
class Loaded:
    """One read: its value, whether it came from the cache, and whether the read failed (fallback used, not kept)."""

    value: Any
    hit: bool = False
    failed: bool = False


async def cached(key: Hashable, loader: Callable[[], Any], *, fallback: Any = None) -> Loaded:
    """The value for `key`: from the cache while it is fresh, else read by `loader` in a worker thread and kept.
    A loader that raises gives `fallback` (not kept) so the request goes on as it did before the cache existed."""
    ttl = ttl_s()
    if ttl > 0:
        found = _cache.get(key, ttl)
        if found is not _MISSING:
            return Loaded(found, hit=True)
    try:
        value = await run_in_threadpool(loader)
    except Exception:
        logger.warning("live help: could not read %s", key[0] if isinstance(key, tuple) else key, exc_info=True)
        return Loaded(fallback, failed=True)
    if ttl > 0:
        _cache.put(key, value)
    return Loaded(value)


def cache_state(reads: list[Loaded]) -> str:
    """For the event log: "off" (no caching), "hit" (every read from the cache), "cold" (none), else "partial"."""
    if ttl_s() <= 0:
        return "off"
    if not reads:
        return "hit"
    hits = sum(1 for read in reads if read.hit)
    return "hit" if hits == len(reads) else "cold" if hits == 0 else "partial"


def invalidate_company(company_id: Optional[str]) -> int:
    """A playbook of this company changed (published, paused, resumed, restored, «Cómo trabajamos» saved): its playbooks
    are read again."""
    if not company_id:
        return 0
    return _cache.drop(lambda key: isinstance(key, tuple) and len(key) > 1 and key[0] in ("grounding", "conduct") and key[1] == company_id)


def clear() -> None:
    _cache.clear()
