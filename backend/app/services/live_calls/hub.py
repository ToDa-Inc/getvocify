"""In-process store and fan-out of each rep's live call.

Production runs a single API process, so one in-memory hub sees every update.
More than one process needs a shared broker (Redis, Postgres NOTIFY) behind
this same surface.
"""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable, Optional

from app.services.live_calls.state import LiveCall

ENDED_CALL_TTL_SECONDS = 10 * 60.0
LIVE_CALL_TTL_SECONDS = 4 * 3600.0
SUBSCRIBER_QUEUE_SIZE = 32


class LiveCallHub:
    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._calls: dict[str, LiveCall] = {}
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._lock = threading.Lock()

    def current(self, user_id: str) -> Optional[LiveCall]:
        """The rep's call, or None once it has gone stale."""
        with self._lock:
            call = self._calls.get(user_id)
            if call is None:
                return None
            since = self._clock() - (call.ended_at or call.started_at)
            ttl = LIVE_CALL_TTL_SECONDS if call.is_live else ENDED_CALL_TTL_SECONDS
            if since > ttl:
                del self._calls[user_id]
                return None
            return call

    def publish(self, user_id: str, call: LiveCall) -> None:
        with self._lock:
            self._calls[user_id] = call
            queues = list(self._subscribers.get(user_id, ()))
        for queue in queues:
            try:
                queue.put_nowait(call)
            except asyncio.QueueFull:
                # A client that stopped reading skips intermediate states; the
                # next update or a reconnect snapshot catches it up.
                continue

    @asynccontextmanager
    async def subscribe(self, user_id: str) -> AsyncIterator[asyncio.Queue]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        with self._lock:
            self._subscribers.setdefault(user_id, set()).add(queue)
        try:
            yield queue
        finally:
            with self._lock:
                subs = self._subscribers.get(user_id)
                if subs is not None:
                    subs.discard(queue)
                    if not subs:
                        del self._subscribers[user_id]

    def subscriber_count(self, user_id: str) -> int:
        with self._lock:
            return len(self._subscribers.get(user_id, ()))


live_call_hub = LiveCallHub()
