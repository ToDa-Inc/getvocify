"""Per-user store and fan-out of open record + live call."""

import asyncio

from app.services.live_calls import hub as hub_mod
from app.services.live_calls.hub import LiveCallHub
from app.services.live_calls.state import RecordPresence, end_call, start_call


class _Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def _presence(at):
    return RecordPresence(provider="hubspot", object_type="contact", record_id="901", account_id=None, seen_at=at)


def test_state_is_per_user():
    hub = LiveCallHub(clock=_Clock(100.0))
    hub.set_presence("rep-1", _presence(100.0))
    assert hub.state("rep-1").presence.record_id == "901"
    assert hub.state("rep-2").presence is None


def test_presence_and_calls_expire():
    clock = _Clock(100.0)
    hub = LiveCallHub(clock=clock)
    hub.set_presence("rep-1", _presence(100.0))
    hub.set_call("rep-1", end_call(start_call("c1", None, 100.0), 100.0))
    clock.now = 100.0 + hub_mod.ENDED_CALL_TTL_SECONDS + 1
    assert hub.state("rep-1").call is None
    assert hub.state("rep-1").presence is not None
    clock.now = 100.0 + hub_mod.PRESENCE_TTL_SECONDS + 1
    assert hub.state("rep-1").presence is None


async def test_subscribers_get_snapshots_of_their_user_only():
    hub = LiveCallHub(clock=_Clock(100.0))
    async with hub.subscribe("rep-1") as mine, hub.subscribe("rep-2") as theirs:
        hub.set_presence("rep-1", _presence(100.0))
        snap = await asyncio.wait_for(mine.get(), timeout=1)
        assert snap.presence.record_id == "901"
        assert theirs.empty()
    assert hub.subscriber_count("rep-1") == 0


async def test_slow_subscriber_does_not_block_updates():
    hub = LiveCallHub(clock=_Clock(100.0))
    async with hub.subscribe("rep-1") as queue:
        for i in range(queue.maxsize + 5):
            hub.set_presence("rep-1", RecordPresence("hubspot", "contact", str(i), None, 100.0))
        assert queue.full()
        assert hub.state("rep-1").presence.record_id == str(queue.maxsize + 4)
