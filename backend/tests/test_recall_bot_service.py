"""T14: reserving/finding/completing a Recall.ai bot capture. complete_recall_capture
must go through the exact same `captures.complete_capture` a desktop capture
completes with (no second completion path for a bot-recorded meeting)."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-recall-3232b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-recall-3232b")

from types import SimpleNamespace

from app.services.meetings.recall_bot import (
    client_capture_id_for_bot,
    complete_recall_capture,
    find_capture_by_bot_id,
    reserve_recall_capture,
    rep_full_name,
)

COMPANY = "co-recall"
USER = "user-rep-1"


class _Query:
    def __init__(self, store, table):
        self._store, self._table = store, table
        self._filters = []
        self._mode = "select"
        self._payload = None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def limit(self, _n):
        return self

    def insert(self, payload):
        self._mode, self._payload = "insert", payload
        return self

    def update(self, payload):
        self._mode, self._payload = "update", payload
        return self

    def execute(self):
        rows = self._store.setdefault(self._table, [])
        if self._mode == "insert":
            row = {"id": f"row-{len(rows) + 1}", **self._payload}
            rows.append(row)
            return SimpleNamespace(data=[dict(row)])
        if self._mode == "update":
            updated = []
            for row in rows:
                if all(row.get(c) == v for c, v in self._filters):
                    row.update(self._payload)
                    updated.append(dict(row))
            return SimpleNamespace(data=updated)
        filtered = list(rows)
        for c, v in self._filters:
            filtered = [row for row in filtered if row.get(c) == v]
        return SimpleNamespace(data=filtered)


class _Supabase:
    def __init__(self, tables=None):
        self.tables = tables or {}

    def table(self, name):
        return _Query(self.tables, name)


def test_client_capture_id_for_bot_is_namespaced():
    assert client_capture_id_for_bot("bot-123") == "recall:bot-123"


def test_reserve_recall_capture_marks_source_and_kind():
    supabase = _Supabase()
    identity = reserve_recall_capture(
        supabase,
        user_id=USER,
        company_id=COMPANY,
        started_at="2026-09-28T10:00:00Z",
        bot_id="bot-1",
        contact_id="contact-9",
    )
    row = supabase.tables["memos"][0]
    assert row["source"] == "recall"
    assert row["source_type"] == "recall_bot"
    assert row["interaction_kind"] == "meeting"
    assert row["client_capture_id"] == "recall:bot-1"
    assert row["hubspot_contact_id"] == "contact-9"
    assert identity.memo_id == row["id"]


def test_reserve_recall_capture_is_idempotent_by_bot_id():
    supabase = _Supabase()
    first = reserve_recall_capture(
        supabase, user_id=USER, company_id=COMPANY, started_at="2026-09-28T10:00:00Z", bot_id="bot-1"
    )
    second = reserve_recall_capture(
        supabase, user_id=USER, company_id=COMPANY, started_at="2026-09-28T10:05:00Z", bot_id="bot-1"
    )
    assert first.memo_id == second.memo_id
    assert len(supabase.tables["memos"]) == 1


def test_find_capture_by_bot_id():
    supabase = _Supabase()
    reserve_recall_capture(
        supabase, user_id=USER, company_id=COMPANY, started_at="2026-09-28T10:00:00Z", bot_id="bot-2"
    )
    found = find_capture_by_bot_id(supabase, "bot-2")
    assert found is not None
    assert found["client_capture_id"] == "recall:bot-2"


def test_find_capture_by_bot_id_returns_none_when_unknown():
    supabase = _Supabase()
    assert find_capture_by_bot_id(supabase, "bot-missing") is None


def test_rep_full_name_reads_user_profiles():
    supabase = _Supabase({"user_profiles": [{"id": USER, "full_name": "Marta Vendedora"}]})
    assert rep_full_name(supabase, USER) == "Marta Vendedora"


def test_rep_full_name_is_none_when_missing_not_an_error():
    supabase = _Supabase({"user_profiles": []})
    assert rep_full_name(supabase, USER) is None


def test_complete_recall_capture_reuses_complete_capture_and_starts_the_pipeline():
    supabase = _Supabase()
    reserve_recall_capture(
        supabase, user_id=USER, company_id=COMPANY, started_at="2026-09-28T10:00:00Z", bot_id="bot-3"
    )
    memo_row = find_capture_by_bot_id(supabase, "bot-3")

    turns = [{"id": "recall-0", "speaker_role": "rep", "start_ms": 0, "end_ms": 1200, "text": "Hola", "is_final": True}]
    identity = complete_recall_capture(supabase, memo_row, transcript="Hola", turns=turns)

    assert identity.should_start_pipeline is True
    stored = supabase.tables["memos"][0]
    assert stored["transcript"] == "Hola"
    assert stored["capture_turns"] == turns
    assert stored["transcript_complete"] is True
