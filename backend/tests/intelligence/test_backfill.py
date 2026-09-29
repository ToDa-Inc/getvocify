"""Analysing every past conversation: only what is missing or stale, bounded, one run at a time."""

import asyncio
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-backfill-32b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-backfill-32b")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import intelligence as intelligence_api
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.intelligence import backfill
from app.services.intelligence.extract import PROMPT_VERSION, shape_intelligence
from tests.crm_copilot.fakes import FakeCompanyService, FakeSupabase


def _memo(mid, user="u1", transcript="Them: hola", intelligence=None, status="approved", company="co"):
    extraction = {"summary": "x"}
    memo = {"id": mid, "user_id": user, "company_id": company, "status": status, "transcript": transcript, "extraction": extraction}
    if intelligence == "current":
        memo["extraction"] = {**extraction, "intelligence": shape_intelligence(memo, {})}
    elif intelligence == "old":
        block = shape_intelligence(memo, {})
        memo["extraction"] = {**extraction, "intelligence": {**block, "prompt_version": "intelligence_v1"}}
    return memo


def _db(*memos):
    return FakeSupabase(memos=list(memos))


def setup_function():
    backfill._RUNS.clear()


def test_coverage_counts_current_stale_and_missing_and_ignores_what_cannot_be_read():
    db = _db(
        _memo("a", intelligence="current"),
        _memo("b", intelligence="old"),
        _memo("c"),
        _memo("d", transcript=""),  # nothing to read
        _memo("e", status="failed"),  # not a usable memo
        _memo("f", user="outsider"),  # not this company
    )
    cov = backfill.coverage(db, "co", ["u1", "u2"])
    assert cov["total"] == 3 and cov["analysed"] == 1 and cov["pending"] == 2


@pytest.mark.asyncio
async def test_backfill_analyses_only_pending_memos_newest_first_and_reports_failures(monkeypatch):
    seen = []

    async def fake_ensure(supabase, memo_id, *, llm=None):
        seen.append(memo_id)
        if memo_id == "boom":
            raise RuntimeError("model down")
        return {"status": "stored"}

    monkeypatch.setattr(backfill, "ensure_intelligence", fake_ensure)
    db = FakeSupabase(memos=[
        {**_memo("old1"), "created_at": "2026-01-01"},
        {**_memo("boom"), "created_at": "2026-03-01"},
        {**_memo("done", intelligence="current"), "created_at": "2026-05-01"},
        {**_memo("new1"), "created_at": "2026-06-01"},
    ])
    result = await backfill.run_backfill(db, "co", ["u1"], concurrency=1)
    assert seen == ["new1", "boom", "old1"]
    assert result == {"analysed": 2, "failed": 1, "skipped": 0, "remaining": 0}


@pytest.mark.asyncio
async def test_backfill_respects_the_limit_and_says_how_many_remain(monkeypatch):
    async def fake_ensure(supabase, memo_id, *, llm=None):
        return {"status": "stored"}

    monkeypatch.setattr(backfill, "ensure_intelligence", fake_ensure)
    db = _db(*[_memo(f"m{i}") for i in range(5)])
    result = await backfill.run_backfill(db, "co", ["u1"], limit=2)
    assert result["analysed"] == 2 and result["remaining"] == 3


@pytest.mark.asyncio
async def test_concurrency_is_bounded(monkeypatch):
    live = peak = 0

    async def fake_ensure(supabase, memo_id, *, llm=None):
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        await asyncio.sleep(0.01)
        live -= 1
        return {"status": "stored"}

    monkeypatch.setattr(backfill, "ensure_intelligence", fake_ensure)
    await backfill.run_backfill(_db(*[_memo(f"m{i}") for i in range(8)]), "co", ["u1"], concurrency=3)
    assert peak == 3


@pytest.mark.asyncio
async def test_a_second_start_while_running_does_not_start_a_second_run(monkeypatch):
    gate = asyncio.Event()

    async def slow_ensure(supabase, memo_id, *, llm=None):
        await gate.wait()
        return {"status": "stored"}

    monkeypatch.setattr(backfill, "ensure_intelligence", slow_ensure)
    db = _db(_memo("a"), _memo("b"))
    first = backfill.start_backfill(db, "co", ["u1"])
    second = backfill.start_backfill(db, "co", ["u1"])
    assert first["started"] is True and second["started"] is False
    assert backfill.progress("co")["running"] is True
    gate.set()
    await asyncio.sleep(0.05)
    assert backfill.progress("co")["running"] is False and backfill.progress("co")["run_analysed"] == 2


def _client(role, monkeypatch_members=("u1", "u2"), db=None):
    app = FastAPI()
    app.include_router(intelligence_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(id="m", company_id="co", user_id="u1", role=role, status="active")
    app.dependency_overrides[get_supabase] = lambda: db or _db(_memo("a"), _memo("b", intelligence="current"))
    intelligence_api._members = lambda supabase, company_id: list(monkeypatch_members)
    return TestClient(app)


def test_a_member_cannot_start_an_analysis():
    assert _client("member").post("/api/v1/intelligence/backfill").status_code == 403


def test_an_admin_starts_it_and_sees_coverage(monkeypatch):
    started = {}
    monkeypatch.setattr(intelligence_api.backfill, "start_backfill", lambda db, company, members, **kw: started.update(company=company, members=members) or {"started": True, "pending": 1})
    response = _client("admin").post("/api/v1/intelligence/backfill")
    assert response.status_code == 202 and response.json()["started"] is True
    assert started == {"company": "co", "members": ["u1", "u2"]}
    cov = _client("admin").get("/api/v1/intelligence/coverage").json()
    assert cov["total"] == 2 and cov["analysed"] == 1 and cov["pending"] == 1 and cov["running"] is False


def test_a_member_sees_only_their_own_coverage():
    db = _db(_memo("a", user="u1"), _memo("b", user="u2"))
    cov = _client("member", db=db).get("/api/v1/intelligence/coverage").json()
    assert cov["total"] == 1


def test_coverage_and_the_running_job_never_share_a_key():
    backfill._RUNS["co"] = {"running": True, "analysed": 3, "failed": 1, "skipped": 0, "queued": 9, "started_at": "t"}
    prog = backfill.progress("co")
    assert prog == {"running": True, "run_analysed": 3, "run_failed": 1, "run_skipped": 0, "run_done": 4, "queued": 9, "started_at": "t"}
    cov = {"total": 20, "analysed": 5, "pending": 15}
    assert not (set(cov) & (set(prog) - {"running"}))
