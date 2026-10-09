"""Review fix: memos_source_check (last redefined in 037_memo_capture_context.sql)
doesn't allow 'recall' until migration 061_memos_source_recall.sql runs. Until then,
reserve_capture must retry with source='web' instead of 500ing - and never for any
other, unrelated check violation."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-recall-3232b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-recall-3232b")

from types import SimpleNamespace

import pytest
from postgrest.exceptions import APIError

from app.services.captures import _is_memos_source_check_violation, reserve_capture

SOURCE_CHECK_ERROR = APIError({
    "message": 'new row for relation "memos" violates check constraint "memos_source_check"',
    "code": "23514",
    "details": None,
    "hint": None,
})

OTHER_CHECK_ERROR = APIError({
    "message": 'new row for relation "memos" violates check constraint "memos_status_check"',
    "code": "23514",
    "details": None,
    "hint": None,
})


def test_is_memos_source_check_violation_matches_only_that_constraint():
    assert _is_memos_source_check_violation(SOURCE_CHECK_ERROR) is True
    assert _is_memos_source_check_violation(OTHER_CHECK_ERROR) is False
    assert _is_memos_source_check_violation(ValueError("boom")) is False


class _MemosTable:
    """First insert (source='recall') raises the pre-migration check violation;
    the retry (source='web') succeeds. Everything else behaves like a normal fake."""

    def __init__(self, store):
        self._store = store
        self._payload = None
        self._filters = []
        self._mode = "select"

    def select(self, *_a, **_k):
        self._mode = "select"
        return self

    def insert(self, row):
        self._mode, self._payload = "insert", dict(row)
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def limit(self, _n):
        return self

    def execute(self):
        if self._mode == "insert":
            if self._payload.get("source") == "recall":
                raise SOURCE_CHECK_ERROR
            row = {"id": "memo-1", **self._payload}
            self._store.append(row)
            return SimpleNamespace(data=[dict(row)])
        rows = [r for r in self._store if all(r.get(c) == v for c, v in self._filters)]
        return SimpleNamespace(data=rows)


class _Supabase:
    def __init__(self):
        self.memos: list[dict] = []
        self.playbooks: list[dict] = []

    def table(self, name):
        if name == "memos":
            return _MemosTable(self.memos)
        return _MemosTable([])  # playbooks lookup: empty, tolerated by playbook_fields_for_capture


def test_reserve_capture_falls_back_to_web_source_before_the_migration_runs():
    supabase = _Supabase()
    identity = reserve_capture(
        supabase,
        user_id="rep-1",
        company_id="co-1",
        client_capture_id="recall:bot-1",
        started_at="2026-09-28T10:00:00Z",
        interaction_kind="meeting",
        source="recall",
        source_type="recall_bot",
    )
    assert identity.memo_id == "memo-1"
    assert supabase.memos[0]["source"] == "web"
    assert supabase.memos[0]["source_type"] == "recall_bot"


def test_an_unrelated_check_violation_is_not_swallowed():
    class _FailingTable(_MemosTable):
        def execute(self):
            if self._mode == "insert":
                raise OTHER_CHECK_ERROR
            return super().execute()

    class _FailingSupabase(_Supabase):
        def table(self, name):
            if name == "memos":
                return _FailingTable(self.memos)
            return _MemosTable([])

    supabase = _FailingSupabase()
    with pytest.raises(APIError):
        reserve_capture(
            supabase,
            user_id="rep-1",
            company_id="co-1",
            client_capture_id="cap-1",
            started_at="2026-09-28T10:00:00Z",
            interaction_kind="call",
        )
