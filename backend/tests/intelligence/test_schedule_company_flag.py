"""schedule_intelligence decides per memo company: the override if set, else the global switch."""

import asyncio
import os

os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")

import pytest  # noqa: E402

from app.config import settings  # noqa: E402
from app.services import feature_flags  # noqa: E402
from app.services.intelligence import extract  # noqa: E402

FLAG = "INTELLIGENCE_EXTRACT_ENABLED"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, db, table):
        self.db, self.table, self.filters = db, table, {}

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def limit(self, _n):
        return self

    def execute(self):
        self.db.calls.append(self.table)
        if self.table in self.db.broken:
            raise RuntimeError(f"{self.table} down")
        return _Result([
            row for row in self.db.tables.get(self.table, [])
            if all(row.get(column) == value for column, value in self.filters.items())
        ])


class FakeSupabase:
    def __init__(self, tables, broken=()):
        self.tables = tables
        self.broken = set(broken)
        self.calls = []

    def table(self, name):
        return _Query(self, name)


def _db(override=None, broken=()):
    flags = [] if override is None else [{"company_id": "co-beta", "flag": FLAG, "enabled": override}]
    return FakeSupabase(
        {"memos": [{"id": "memo-1", "company_id": "co-beta"}], "company_feature_flags": flags},
        broken=broken,
    )


@pytest.fixture(autouse=True)
def recorded(monkeypatch):
    feature_flags.clear_cache()
    ran = []

    async def fake_ensure(_supabase, memo_id, **_kwargs):
        ran.append(memo_id)
        return {"status": "stored"}

    monkeypatch.setattr(extract, "ensure_intelligence", fake_ensure)
    yield ran
    feature_flags.clear_cache()


def _schedule(db, **kwargs):
    async def go():
        started = extract.schedule_intelligence(db, "memo-1", **kwargs)
        await asyncio.sleep(0)
        await asyncio.gather(*list(extract._tasks))
        return started

    return asyncio.run(go())


def test_beta_company_on_while_global_off(monkeypatch, recorded):
    monkeypatch.setattr(settings, FLAG, False)
    assert _schedule(_db(override=True)) is True
    assert recorded == ["memo-1"]


def test_company_off_while_global_on(monkeypatch, recorded):
    monkeypatch.setattr(settings, FLAG, True)
    assert _schedule(_db(override=False)) is False
    assert recorded == []


@pytest.mark.parametrize("global_value", [True, False])
def test_no_override_follows_global(monkeypatch, recorded, global_value):
    monkeypatch.setattr(settings, FLAG, global_value)
    assert _schedule(_db()) is global_value
    assert recorded == (["memo-1"] if global_value else [])


def test_a_known_company_skips_the_memo_lookup(monkeypatch, recorded):
    monkeypatch.setattr(settings, FLAG, False)
    db = _db(override=True)
    assert _schedule(db, company_id="co-beta") is True
    assert "memos" not in db.calls
    assert recorded == ["memo-1"]


@pytest.mark.parametrize("broken", [("memos",), ("company_feature_flags",)])
@pytest.mark.parametrize("global_value", [True, False])
def test_lookup_failure_falls_back_to_global_and_never_raises(monkeypatch, recorded, broken, global_value):
    monkeypatch.setattr(settings, FLAG, global_value)
    assert _schedule(_db(override=not global_value, broken=broken)) is global_value
    assert recorded == (["memo-1"] if global_value else [])


def test_the_post_extraction_hook_passes_the_memo_company(monkeypatch):
    from app.services import memo_extraction_hooks

    seen = []
    monkeypatch.setattr(extract, "schedule_intelligence", lambda _db, memo_id, **kw: seen.append((memo_id, kw)))
    memo_extraction_hooks.run_post_extraction_hooks(
        _db(), memo_id="memo-1", extraction={}, memo={"id": "memo-1", "company_id": "co-beta"},
    )
    assert seen == [("memo-1", {"company_id": "co-beta"})]


def test_outside_an_event_loop_nothing_is_scheduled(monkeypatch, recorded):
    monkeypatch.setattr(settings, FLAG, True)
    assert extract.schedule_intelligence(_db(), "memo-1") is False
    assert recorded == []
