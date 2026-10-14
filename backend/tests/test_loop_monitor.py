import asyncio
import logging
import time

from app.services import loop_monitor


def test_a_blocked_loop_is_logged_with_how_long_it_was_held(caplog):
    async def scenario():
        watcher = asyncio.create_task(loop_monitor._watch(interval_s=0.01, stall_s=0.1))
        await asyncio.sleep(0.05)
        time.sleep(0.3)  # blocking work on the loop
        await asyncio.sleep(0.05)
        watcher.cancel()

    with caplog.at_level(logging.WARNING, logger="app.services.loop_monitor"):
        asyncio.run(scenario())
    stalls = [r for r in caplog.records if "event loop held" in r.getMessage()]
    assert stalls and stalls[0].stall_ms >= 250


def test_a_free_loop_logs_nothing(caplog):
    async def scenario():
        watcher = asyncio.create_task(loop_monitor._watch(interval_s=0.01, stall_s=0.1))
        await asyncio.sleep(0.1)
        watcher.cancel()

    with caplog.at_level(logging.WARNING, logger="app.services.loop_monitor"):
        asyncio.run(scenario())
    assert not [r for r in caplog.records if "event loop held" in r.getMessage()]


def _hold_the_loop_in_a_named_function():
    time.sleep(0.6)


def test_a_long_stall_logs_the_line_holding_the_loop(caplog):
    async def scenario():
        import threading

        dog = loop_monitor._StackWatchdog(threading.get_ident(), dump_after_s=0.2)
        dog.start()
        watcher = asyncio.create_task(loop_monitor._watch(interval_s=0.01, stall_s=0.1, watchdog=dog))
        await asyncio.sleep(0.05)
        _hold_the_loop_in_a_named_function()
        await asyncio.sleep(0.05)
        watcher.cancel()
        dog.stop()

    with caplog.at_level(logging.WARNING, logger="app.services.loop_monitor"):
        asyncio.run(scenario())
    stacks = [r.getMessage() for r in caplog.records if getattr(r, "phase", None) == "stall_stack"]
    assert len(stacks) == 1
    assert "_hold_the_loop_in_a_named_function" in stacks[0]
