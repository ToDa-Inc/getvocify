"""Per-user store and fan-out of live calls."""

import asyncio

from app.services.live_calls import hub as hub_mod
from app.services.live_calls.hub import LiveCallHub
from app.services.live_calls.state import end_call, start_call


class _Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def test_current_is_per_user_and_ended_calls_expire():
    clock = _Clock(100.0)
    hub = LiveCallHub(clock=clock)
    hub.publish("rep-1", end_call(start_call("c1", None, 100.0), 100.0))
    assert hub.current("rep-1").id == "c1"
    assert hub.current("rep-2") is None
    clock.now = 100.0 + hub_mod.ENDED_CALL_TTL_SECONDS + 1
    assert hub.current("rep-1") is None


def test_live_calls_last_longer():
    clock = _Clock(100.0)
    hub = LiveCallHub(clock=clock)
    hub.publish("rep-1", start_call("c1", None, 100.0))
    clock.now = 100.0 + hub_mod.ENDED_CALL_TTL_SECONDS + 1
    assert hub.current("rep-1") is not None
    clock.now = 100.0 + hub_mod.LIVE_CALL_TTL_SECONDS + 1
    assert hub.current("rep-1") is None


async def test_subscribers_get_their_users_calls_only():
    hub = LiveCallHub(clock=_Clock(100.0))
    async with hub.subscribe("rep-1") as mine, hub.subscribe("rep-2") as theirs:
        hub.publish("rep-1", start_call("c1", None, 100.0))
        assert (await asyncio.wait_for(mine.get(), timeout=1)).id == "c1"
        assert theirs.empty()
    assert hub.subscriber_count("rep-1") == 0


async def test_slow_subscriber_does_not_block_publish():
    hub = LiveCallHub(clock=_Clock(100.0))
    async with hub.subscribe("rep-1") as queue:
        for i in range(queue.maxsize + 5):
            hub.publish("rep-1", start_call(f"c{i}", None, 100.0))
        assert queue.full()
        assert hub.current("rep-1").id == f"c{queue.maxsize + 4}"
