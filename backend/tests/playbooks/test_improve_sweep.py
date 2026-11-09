"""The playbook's improvement step run by itself: every company with recent cards, no switch, each one on its own."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.services.playbooks import improve_sweep
from app.services.playbooks.assistant_store import InMemoryAssistantStore
from tests.reporting.fake_db import FakeDB


def run_sweep(monkeypatch, events, *, broken=()):
    store = InMemoryAssistantStore()
    judged: list[str] = []

    async def fake_refresh(_store, _db, company_id, **_kw):
        if company_id in broken:
            raise RuntimeError("boom")
        judged.append(company_id)
        return 2

    monkeypatch.setattr(improve_sweep, "get_assistant_store", lambda _db: store)
    monkeypatch.setattr(improve_sweep, "refresh_outcomes", fake_refresh)
    done = asyncio.run(improve_sweep.sweep(FakeDB({"live_assist_events": events})))
    return done, judged


def card(company, days_ago=0, is_objection=True):
    at = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return {"company_id": company, "is_objection": is_objection, "created_at": at}


def test_every_company_with_recent_cards_is_judged_without_a_switch(monkeypatch):
    done, judged = run_sweep(monkeypatch, [card("co-a"), card("co-a"), card("co-b"), card("co-old", days_ago=5), card("co-none", is_objection=None)])
    assert judged == ["co-a", "co-b"] and done == {"co-a": {"judged": 2, "queued": 0}, "co-b": {"judged": 2, "queued": 0}}


def test_one_company_failing_does_not_stop_the_others(monkeypatch):
    done, judged = run_sweep(monkeypatch, [card("co-a"), card("co-b")], broken=("co-a",))
    assert judged == ["co-b"] and list(done) == ["co-b"]
