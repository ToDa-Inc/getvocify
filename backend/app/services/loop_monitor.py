"""Tells when something holds the event loop.

A request handler that does blocking work on the loop stalls every other request until it is
done. This sleeps for a short interval in a loop and measures how late it wakes: that lateness
is exactly how long the loop was held. Stalls above the threshold are logged, so a slow page can
be traced to a blocked loop instead of guessed at.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

INTERVAL_S = 0.05
STALL_LOG_S = 0.25

_task: Optional[asyncio.Task] = None


async def _watch(interval_s: float = INTERVAL_S, stall_s: float = STALL_LOG_S) -> None:
    while True:
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
    global _task
    if _task is None or _task.done():
        _task = asyncio.get_running_loop().create_task(_watch(), name="loop-monitor")


def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
