"""In-process store and fan-out of each rep's open record and live call.

Production runs a single API process, so one in-memory hub sees every update.
More than one process needs a shared broker (Redis, Postgres NOTIFY) behind
this same surface.
"""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Callable, Optional

from app.services.live_calls.state import LiveCall, RecordPresence

PRESENCE_TTL_SECONDS = 12 * 3600.0
ENDED_CALL_TTL_SECONDS = 10 * 60.0
LIVE_CALL_TTL_SECONDS = 4 * 3600.0
SUBSCRIBER_QUEUE_SIZE = 32


@dataclass(frozen=True)
class LiveState:
    presence: Optional[RecordPresence]
    call: Optional[LiveCall]

    def to_dict(self) -> dict:
        return {
            "presence": self.presence.to_dict() if self.presence else None,
            "call": self.call.to_dict() if self.call else None,
        }


class LiveCallHub:
    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._presence: dict[str, RecordPresence] = {}
        self._calls: dict[str, LiveCall] = {}
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._lock = threading.Lock()

    def state(self, user_id: str) -> LiveState:
        now = self._clock()
        with self._lock:
            presence = self._presence.get(user_id)
            if presence and now - presence.seen_at > PRESENCE_TTL_SECONDS:
                del self._presence[user_id]
                presence = None
            call = self._calls.get(user_id)
            if call:
                since = now - (call.ended_at or call.started_at)
                ttl = LIVE_CALL_TTL_SECONDS if call.is_live else ENDED_CALL_TTL_SECONDS
                if since > ttl:
                    del self._calls[user_id]
                    call = None
            return LiveState(presence=presence, call=call)

    def set_presence(self, user_id: str, presence: RecordPresence) -> None:
        with self._lock:
            self._presence[user_id] = presence
        self._notify(user_id)

    def set_call(self, user_id: str, call: LiveCall) -> None:
        with self._lock:
            self._calls[user_id] = call
        self._notify(user_id)

    def _notify(self, user_id: str) -> None:
        snapshot = self.state(user_id)
        with self._lock:
            queues = list(self._subscribers.get(user_id, ()))
        for queue in queues:
            try:
                queue.put_nowait(snapshot)
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
