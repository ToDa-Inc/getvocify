import asyncio

import pytest

from app.services.request_coalesce import CoalesceCache


@pytest.mark.asyncio
async def test_concurrent_callers_share_one_factory():
    cache = CoalesceCache(ttl_seconds=30)
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return "ok"

    a, b = await asyncio.gather(
        cache.get_or_set("k", factory),
        cache.get_or_set("k", factory),
    )
    assert a == b == "ok"
    assert calls == 1


@pytest.mark.asyncio
async def test_ttl_hit_does_not_refetch():
    cache = CoalesceCache(ttl_seconds=30)
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        return calls

    assert await cache.get_or_set("k", factory) == 1
    assert await cache.get_or_set("k", factory) == 1
    assert calls == 1


@pytest.mark.asyncio
async def test_failed_factory_is_not_cached():
    cache = CoalesceCache(ttl_seconds=30)
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")
        return "ok"

    with pytest.raises(RuntimeError):
        await cache.get_or_set("k", factory)
    assert await cache.get_or_set("k", factory) == "ok"
    assert calls == 2
