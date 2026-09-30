"""Per-user live call fan-out."""

import asyncio

from app.services.live_calls.hub import LiveCallHub
from app.services.live_calls.state import LiveCallEvent, apply_event


def _call(kind="started", call_id="ext-1", at=100.0):
    return apply_event(
        None,
        LiveCallEvent(
            provider="hubspot",
            source="hubspot_calling_sdk",
            event=kind,
            external_call_id=call_id,
            occurred_at=at,
        ),
    )


class _Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def test_current_is_scoped_per_user():
    hub = LiveCallHub(clock=_Clock(100.0))
    hub.publish("rep-1", _call())
    assert hub.current("rep-1").external_call_id == "ext-1"
    assert hub.current("rep-2") is None


def test_ended_call_expires_sooner_than_open_call():
    clock = _Clock(100.0)
    hub = LiveCallHub(clock=clock, ended_ttl_s=60, open_ttl_s=3600)
    hub.publish("open", _call("started"))
    hub.publish("ended", _call("ended"))
    clock.now = 200.0
    assert hub.current("open") is not None
    assert hub.current("ended") is None


async def test_subscribers_receive_only_their_users_calls():
    hub = LiveCallHub(clock=_Clock(100.0))
    async with hub.subscribe("rep-1") as mine, hub.subscribe("rep-2") as theirs:
        hub.publish("rep-1", _call(call_id="x"))
        got = await asyncio.wait_for(mine.get(), timeout=1)
        assert got.external_call_id == "x"
        assert theirs.empty()
    assert hub.subscriber_count("rep-1") == 0


async def test_slow_subscriber_does_not_block_publish():
    hub = LiveCallHub(clock=_Clock(100.0))
    async with hub.subscribe("rep-1") as queue:
        for i in range(queue.maxsize + 5):
            hub.publish("rep-1", _call(call_id=f"c{i}"))
        assert queue.full()
        assert hub.current("rep-1").external_call_id == f"c{queue.maxsize + 4}"
