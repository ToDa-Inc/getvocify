"""In-process fan-out of live calls to each rep's connected clients.

Production runs a single API process, so one in-memory hub sees every event.
Running more than one process needs a shared broker (Redis, Postgres NOTIFY)
behind this same publish/current/subscribe surface.
"""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable, Optional

from app.services.live_calls.state import LiveCall

ENDED_TTL_SECONDS = 120.0
OPEN_TTL_SECONDS = 4 * 3600.0
SUBSCRIBER_QUEUE_SIZE = 32


class LiveCallHub:
    def __init__(
        self,
        *,
        ended_ttl_s: float = ENDED_TTL_SECONDS,
        open_ttl_s: float = OPEN_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._ended_ttl_s = ended_ttl_s
        self._open_ttl_s = open_ttl_s
        self._clock = clock
        self._calls: dict[str, LiveCall] = {}
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._lock = threading.Lock()

    def current(self, user_id: str) -> Optional[LiveCall]:
        """The rep's latest call, or None once it has gone stale."""
        with self._lock:
            call = self._calls.get(user_id)
            if call is None:
                return None
            ttl = self._open_ttl_s if call.is_open else self._ended_ttl_s
            if self._clock() - call.updated_at > ttl:
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
                # A client that stopped reading loses intermediate states;
                # the next event or a reconnect snapshot catches it up.
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
