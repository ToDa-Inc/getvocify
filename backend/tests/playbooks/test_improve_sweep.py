"""The playbook's improvement step run by itself: only companies that have it on, each one on its own."""

from __future__ import annotations

import asyncio

from app.services.playbooks import improve_sweep
from app.services.playbooks.assistant_store import InMemoryAssistantStore
from tests.reporting.fake_db import FakeDB


def run_sweep(monkeypatch, flags, *, broken=()):
    store = InMemoryAssistantStore()
    judged: list[str] = []

    async def fake_refresh(_store, _db, company_id, **_kw):
        if company_id in broken:
            raise RuntimeError("boom")
        judged.append(company_id)
        return 2

    monkeypatch.setattr(improve_sweep, "get_assistant_store", lambda _db: store)
    monkeypatch.setattr(improve_sweep, "refresh_outcomes", fake_refresh)
    monkeypatch.setattr(improve_sweep, "is_enabled", lambda _db, company, flag: flag in flags.get(company, ()))
    rows = [{"company_id": c, "flag": f, "enabled": True} for c, fs in flags.items() for f in fs]
    done = asyncio.run(improve_sweep.sweep(FakeDB({"company_feature_flags": rows, "live_assist_events": []})))
    return done, judged


BOTH = (improve_sweep.ASSISTANT_FLAG, improve_sweep.SUCCESS_FLAG)


def test_only_companies_with_both_flags_are_judged(monkeypatch):
    done, judged = run_sweep(monkeypatch, {"co-on": BOTH, "co-half": (improve_sweep.ASSISTANT_FLAG,)})
    assert judged == ["co-on"] and done == {"co-on": {"judged": 2, "queued": 0}}


def test_one_company_failing_does_not_stop_the_others(monkeypatch):
    done, judged = run_sweep(monkeypatch, {"co-a": BOTH, "co-b": BOTH}, broken=("co-a",))
    assert judged == ["co-b"] and list(done) == ["co-b"]
