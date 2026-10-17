"""The playbook assistant's storage (sessions, improvement queue, suggestion verdicts): one contract, two implementations (memory for tests, SQL for production),
and a store that says "not activated" instead of failing when the migration 083 tables are not there yet."""

from __future__ import annotations

import pytest

from app.services.playbooks.assistant_store import (
    AssistantUnavailable,
    InMemoryAssistantStore,
    SqlAssistantStore,
    get_assistant_store,
    set_assistant_store,
)
from tests.reporting.fake_db import FakeDB

COMPANY = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"
USER = "33333333-3333-3333-3333-333333333333"


@pytest.fixture(params=["memory", "sql"])
def store(request):
    return InMemoryAssistantStore() if request.param == "memory" else SqlAssistantStore(FakeDB())


def test_a_session_is_created_and_read_back(store):
    session = store.create_session(COMPANY, USER, "gaps", {"gaps": [1, 2]})
    assert session["status"] == "open" and session["kind"] == "gaps" and session["state"] == {"gaps": [1, 2]}
    assert store.get_session(COMPANY, session["id"])["state"] == {"gaps": [1, 2]}
    assert store.get_session(OTHER, session["id"]) is None


def test_the_latest_open_session_skips_done_ones_and_other_kinds(store):
    first = store.create_session(COMPANY, USER, "gaps", {})
    store.save_session(COMPANY, first["id"], state={"n": 1}, status="done")
    second = store.create_session(COMPANY, USER, "gaps", {})
    store.create_session(COMPANY, USER, "trial", {})
    store.create_session(OTHER, USER, "gaps", {})
    assert store.latest_open_session(COMPANY, "gaps")["id"] == second["id"]
    assert store.latest_open_session(COMPANY, "trial")["kind"] == "trial"
    store.save_session(COMPANY, second["id"], state={}, status="done")
    assert store.latest_open_session(COMPANY, "gaps") is None


def test_saving_a_session_replaces_its_state_and_keeps_its_status_when_none_is_given(store):
    session = store.create_session(COMPANY, USER, "trial", {"a": 1})
    saved = store.save_session(COMPANY, session["id"], state={"a": 2})
    assert saved["state"] == {"a": 2} and saved["status"] == "open"


def test_moments_are_listed_by_status_and_updated(store):
    a = store.add_moment(COMPANY, {"source": "real", "client_text": "Es caro", "sales_motion_key": "discovery"})
    store.add_moment(COMPANY, {"source": "trial", "client_text": "No tenemos tiempo", "sales_motion_key": "discovery"})
    store.add_moment(OTHER, {"source": "real", "client_text": "Otro", "sales_motion_key": "discovery"})
    assert len(store.list_moments(COMPANY)) == 2
    store.update_moment(COMPANY, a["id"], status="corrected")
    assert [m["client_text"] for m in store.list_moments(COMPANY, status="open")] == ["No tenemos tiempo"]
    assert store.get_moment(COMPANY, a["id"])["status"] == "corrected"
    assert store.get_moment(OTHER, a["id"]) is None


def test_an_outcome_is_idempotent_per_event(store):
    store.upsert_outcome(COMPANY, {"event_id": "e1", "used": "unknown", "resolved": "unknown", "observed_at": "2026-10-10T10:00:00+00:00"})
    store.upsert_outcome(COMPANY, {"event_id": "e1", "used": "used", "resolved": "resolved", "observed_at": "2026-10-10T10:00:00+00:00"})
    rows = store.list_outcomes(COMPANY, since="2026-10-01T00:00:00+00:00")
    assert len(rows) == 1 and rows[0]["used"] == "used"
    assert store.get_outcome(COMPANY, "e1")["resolved"] == "resolved"
    assert store.get_outcome(OTHER, "e1") is None


def test_outcomes_are_filtered_by_date_and_company(store):
    store.upsert_outcome(COMPANY, {"event_id": "old", "observed_at": "2026-08-01T10:00:00+00:00"})
    store.upsert_outcome(COMPANY, {"event_id": "new", "observed_at": "2026-10-10T10:00:00+00:00"})
    store.upsert_outcome(OTHER, {"event_id": "foreign", "observed_at": "2026-10-10T10:00:00+00:00"})
    assert [r["event_id"] for r in store.list_outcomes(COMPANY, since="2026-09-01T00:00:00+00:00")] == ["new"]
    assert store.judged_event_ids(COMPANY, ["old", "new", "foreign", "never"]) == {"old", "new"}
    assert store.judged_event_ids(COMPANY, []) == set()


# --- the tables are not there yet ------------------------------------------------------------------


class _MissingTable(FakeDB):
    def table(self, name):
        raise RuntimeError(f"Could not find the table 'public.{name}' in the schema cache")


class _Broken(FakeDB):
    def table(self, name):
        raise RuntimeError("boom")


def test_missing_tables_mean_not_activated():
    store = SqlAssistantStore(_MissingTable())
    with pytest.raises(AssistantUnavailable) as caught:
        store.latest_open_session(COMPANY, "gaps")
    assert caught.value.code == "not_activated"
    with pytest.raises(AssistantUnavailable):
        store.upsert_outcome(COMPANY, {"event_id": "e1"})


def test_any_other_database_error_is_not_hidden():
    with pytest.raises(RuntimeError, match="boom"):
        SqlAssistantStore(_Broken()).list_moments(COMPANY)


def test_the_installed_store_is_used_and_none_goes_back_to_sql():
    memory = InMemoryAssistantStore()
    set_assistant_store(memory)
    try:
        assert get_assistant_store(FakeDB()) is memory
    finally:
        set_assistant_store(None)
    assert isinstance(get_assistant_store(FakeDB()), SqlAssistantStore)
