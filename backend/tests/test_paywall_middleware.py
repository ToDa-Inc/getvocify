"""The paywall check never holds the event loop, and still locks paywalled companies."""

import asyncio
import time

import httpx
import pytest
from fastapi import FastAPI

from app import paywall


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(paywall.PaywallMiddleware)

    @app.get("/api/v1/thing")
    async def thing():
        return {"ok": True}

    return app


@pytest.fixture(autouse=True)
def _token_is_the_user_id(monkeypatch):
    monkeypatch.setattr(paywall, "user_id_from_access_token", lambda token, secret: token)
    paywall._open_users.clear()
    yield
    paywall._open_users.clear()


async def _get(app: FastAPI, user: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/v1/thing", headers={"Authorization": f"Bearer {user}"})


async def test_a_paywalled_company_is_locked(monkeypatch):
    monkeypatch.setattr(paywall, "_paywalled", lambda user_id: True)
    response = await _get(_app(), "u1")
    assert response.status_code == 403
    assert response.json()["code"] == "PAYWALL"


async def test_an_open_user_is_looked_up_once_a_minute(monkeypatch):
    lookups = []
    monkeypatch.setattr(paywall, "_paywalled", lambda user_id: lookups.append(user_id) or False)
    app = _app()
    for _ in range(3):
        assert (await _get(app, "u1")).status_code == 200
    assert lookups == ["u1"]


async def test_a_slow_lookup_does_not_hold_the_loop(monkeypatch):
    def slow(user_id):
        time.sleep(0.4)  # a Supabase call that hangs
        return False

    monkeypatch.setattr(paywall, "_paywalled", slow)
    ticks = 0

    async def other_work():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    ticker = asyncio.create_task(other_work())
    response = await _get(_app(), "u1")
    ticker.cancel()

    assert response.status_code == 200
    assert ticks >= 10  # the loop kept serving while the lookup waited


async def test_a_lookup_over_budget_lets_the_request_through(monkeypatch):
    monkeypatch.setattr(paywall, "LOOKUP_BUDGET_S", 0.1)
    monkeypatch.setattr(paywall, "_paywalled", lambda user_id: time.sleep(0.5) or True)
    started = time.perf_counter()
    response = await _get(_app(), "u1")
    assert response.status_code == 200
    assert time.perf_counter() - started < 0.4


async def test_a_failed_lookup_lets_the_request_through(monkeypatch):
    def broken(user_id):
        raise RuntimeError("supabase down")

    monkeypatch.setattr(paywall, "_paywalled", broken)
    assert (await _get(_app(), "u1")).status_code == 200
