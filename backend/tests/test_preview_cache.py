import asyncio

import pytest

from app.services.preview_cache import PreviewCache, memo_fingerprint


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_a_built_value_is_served_until_it_expires():
    clock, builds = Clock(), []

    async def build():
        builds.append(1)
        return f"v{len(builds)}"

    cache = PreviewCache(ttl_s=10, clock=clock)

    async def scenario():
        first = await cache.get_or_build("k", build)
        clock.now = 9
        again = await cache.get_or_build("k", build)
        clock.now = 11
        later = await cache.get_or_build("k", build)
        return first, again, later

    assert asyncio.run(scenario()) == ("v1", "v1", "v2")


def test_callers_who_arrive_during_a_build_share_it():
    builds = []

    async def build():
        builds.append(1)
        await asyncio.sleep(0.05)
        return "shared"

    cache = PreviewCache()

    async def scenario():
        return await asyncio.gather(*(cache.get_or_build("k", build) for _ in range(5)))

    assert asyncio.run(scenario()) == ["shared"] * 5
    assert len(builds) == 1


def test_a_failed_build_is_not_kept_and_fails_everyone_waiting():
    calls = []

    async def build():
        calls.append(1)
        await asyncio.sleep(0.02)
        if len(calls) == 1:
            raise RuntimeError("crm down")
        return "ok"

    cache = PreviewCache()

    async def scenario():
        results = await asyncio.gather(
            cache.get_or_build("k", build), cache.get_or_build("k", build), return_exceptions=True
        )
        retry = await cache.get_or_build("k", build)
        return results, retry

    results, retry = asyncio.run(scenario())
    assert all(isinstance(r, RuntimeError) for r in results)
    assert retry == "ok" and len(calls) == 2


def test_one_caller_giving_up_does_not_cancel_the_build_for_the_others():
    async def build():
        await asyncio.sleep(0.05)
        return "done"

    cache = PreviewCache()

    async def scenario():
        impatient = asyncio.create_task(cache.get_or_build("k", build))
        patient = asyncio.create_task(cache.get_or_build("k", build))
        await asyncio.sleep(0.01)
        impatient.cancel()
        return await patient

    assert asyncio.run(scenario()) == "done"


def test_the_least_recently_used_entry_goes_first():
    async def must_not_build():
        raise AssertionError("expected a cache hit")

    async def scenario():
        cache = PreviewCache(max_entries=2)
        for key in ("a", "b"):
            await cache.get_or_build(key, lambda key=key: _value(key))
        await cache.get_or_build("a", must_not_build)  # a is now the most recent
        await cache.get_or_build("c", lambda: _value("c"))  # evicts b, the least recent
        kept = [await cache.get_or_build(k, must_not_build) for k in ("a", "c")]
        rebuilt = await cache.get_or_build("b", lambda: _value("b-again"))
        return kept, rebuilt

    assert asyncio.run(scenario()) == (["a", "c"], "b-again")


async def _value(v):
    return v


def test_the_fingerprint_changes_with_the_memo_and_ignores_what_changes_constantly():
    memo = {"id": "m", "status": "pending_review", "extraction": {"summary": "x"}, "pipeline_meta": {"a": 1}, "followup": None}
    same = {**memo, "pipeline_meta": {"a": 2}, "followup": {"status": "ready"}, "recording_path": "p"}
    assert memo_fingerprint(memo) == memo_fingerprint(same)
    for changed in (
        {**memo, "status": "approved"},
        {**memo, "extraction": {"summary": "y"}},
        {**memo, "hubspot_contact_id": "c"},
        {**memo, "sales_motion_key": "closing"},
    ):
        assert memo_fingerprint(changed) != memo_fingerprint(memo)
