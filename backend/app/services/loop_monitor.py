"""Tells when something holds the event loop.

A request handler that does blocking work on the loop stalls every other request until it is
done. This sleeps for a short interval in a loop and measures how late it wakes: that lateness
is exactly how long the loop was held. Stalls above the threshold are logged, so a slow page can
be traced to a blocked loop instead of guessed at.

The lateness is only known once the loop is free again, so a thread also watches the loop's
heartbeat: when the loop has been held longer than STACK_DUMP_S, it logs the loop thread's stack
while it is still stuck, which names the exact line doing the blocking.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
import traceback
from typing import Optional

logger = logging.getLogger(__name__)

INTERVAL_S = 0.05
STALL_LOG_S = 0.25
STACK_DUMP_S = 2.0

_task: Optional[asyncio.Task] = None
_watchdog: Optional["_StackWatchdog"] = None


class _StackWatchdog(threading.Thread):
    """Logs the loop thread's stack once per stall that outlasts `dump_after_s`."""

    def __init__(self, loop_thread_id: int, dump_after_s: float = STACK_DUMP_S) -> None:
        super().__init__(name="loop-stack-watchdog", daemon=True)
        self.loop_thread_id = loop_thread_id
        self.dump_after_s = dump_after_s
        self.heartbeat = time.monotonic()
        self._stopped = threading.Event()

    def beat(self) -> None:
        self.heartbeat = time.monotonic()

    def stop(self) -> None:
        self._stopped.set()

    def run(self) -> None:
        dumped_for = None
        while not self._stopped.wait(self.dump_after_s / 4):
            beat = self.heartbeat
            if beat == dumped_for or time.monotonic() - beat < self.dump_after_s:
                continue
            frame = sys._current_frames().get(self.loop_thread_id)
            if frame is None:
                continue
            dumped_for = beat
            logger.warning(
                "event loop held for over %.0f s, it is at:\n%s",
                self.dump_after_s,
                "".join(traceback.format_stack(frame)),
                extra={"domain": "loop", "phase": "stall_stack"},
            )


async def _watch(
    interval_s: float = INTERVAL_S,
    stall_s: float = STALL_LOG_S,
    watchdog: Optional[_StackWatchdog] = None,
) -> None:
    while True:
        if watchdog is not None:
            watchdog.beat()
        before = time.perf_counter()
        await asyncio.sleep(interval_s)
        late = time.perf_counter() - before - interval_s
        if late >= stall_s:
            logger.warning(
                "event loop held for %.0f ms",
                late * 1000,
                extra={"domain": "loop", "phase": "stall", "stall_ms": round(late * 1000)},
            )


def start() -> None:
    global _task, _watchdog
    if _task is None or _task.done():
        _watchdog = _StackWatchdog(threading.get_ident())
        _watchdog.start()
        _task = asyncio.get_running_loop().create_task(_watch(watchdog=_watchdog), name="loop-monitor")


def stop() -> None:
    global _task, _watchdog
    if _task is not None:
        _task.cancel()
        _task = None
    if _watchdog is not None:
        _watchdog.stop()
        _watchdog = None
