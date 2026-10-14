"""The live help event log: small, written after the response, and never in the way of a call."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import copilot as copilot_api
from app.config import settings
from app.deps import get_membership, get_supabase, get_user_id
from app.services.company import Membership
from app.services.copilot import events, playbook_objections
from app.services.llm.jev import JevClient


@pytest.fixture(autouse=True)
def fresh_log(monkeypatch):
    monkeypatch.setattr(events, "_paused_until", 0.0)
    monkeypatch.setattr(events, "_last_purge", 0.0)
    events._last_turn.clear()
    playbook_objections._cache.clear()


class FakeTable:
    def __init__(self, db, fail=False):
        self.db, self.fail = db, fail

    def insert(self, row):
        self.db.inserted.append(row)
        return self

    def delete(self):
        self.db.deleted += 1
        return self

    def lt(self, *_a):
        return self

    def execute(self):
        if self.fail:
            raise RuntimeError('relation "live_assist_events" does not exist')
        return self


class Other:
    """Any other table: reads come back empty."""

    data: list = []

    def __getattr__(self, _name):
        return lambda *_a, **_k: self

    def execute(self):
        return self


class FakeDb:
    def __init__(self, fail=False):
        self.inserted, self.deleted, self.fail = [], 0, fail

    def table(self, name):
        return FakeTable(self, self.fail) if name == events.TABLE else Other()


def _client(db):
    app = FastAPI()
    app.include_router(copilot_api.router)
    app.dependency_overrides[get_supabase] = lambda: db
    app.dependency_overrides[get_user_id] = lambda: "user-1"
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m-1", company_id="co-1", user_id="user-1", role="member", status="active",
    )
    return TestClient(app)


def _classifier(monkeypatch, objection="price", turn="finished"):
    async def fake_post(self, state, questions):
        return {"turn": {"choice": turn, "confidence": 0.9}, "objection": {"choice": objection, "confidence": 1}}

    monkeypatch.setattr(JevClient, "_post_systemone", fake_post)
    monkeypatch.setattr(JevClient, "is_available", property(lambda self: True))


def _turn(client, text="me parece caro"):
    return client.post("/api/v1/copilot/turn", json={
        "transcript_window": f"Them: {text}", "latest_turn": text, "sales_motion_key": "discovery",
    })


def test_a_finished_turn_is_logged_with_what_the_check_said(monkeypatch):
    _classifier(monkeypatch)
    monkeypatch.setattr(playbook_objections, "custom_for", lambda *_a: {})
    db = FakeDb()
    response = _turn(_client(db))
    assert response.json() == {"finished": True, "objection": "price"}
    (row,) = db.inserted
    assert row["kind"] == "turn" and row["user_id"] == "user-1" and row["sales_motion_key"] == "discovery"
    assert row["latest_turn"] == "me parece caro" and row["objection"] == "price" and row["finished"] is True
    assert isinstance(row["check_ms"], int) and row["prompt_version"] == events.PROMPT_VERSION


def test_a_thought_still_going_and_the_same_words_twice_are_not_logged(monkeypatch):
    monkeypatch.setattr(playbook_objections, "custom_for", lambda *_a: {})
    db = FakeDb()
    client = _client(db)
    _classifier(monkeypatch, objection="none", turn="continuing")
    # Not final: finished comes back true only when the check is unsure, so ask for a confident "continuing".
    assert _turn(client, "Ya, pero la verdad es que me parece").json()["finished"] is False
    assert db.inserted == []
    _classifier(monkeypatch)
    _turn(client)
    _turn(client)
    assert len(db.inserted) == 1


def test_a_custom_match_logs_its_playbook_entry(monkeypatch):
    custom = {"objection:custom:x": {"label": "Equis", "trigger": ""}}
    monkeypatch.setattr(playbook_objections, "custom_for", lambda *_a: custom)
    _classifier(monkeypatch, objection="objection:custom:x")
    db = FakeDb()
    _turn(_client(db), "algo propio")
    assert db.inserted[0]["objection"] == "custom" and db.inserted[0]["entry_id"] == "objection:custom:x"


def _stub_suggest(monkeypatch, events_out):
    async def fake_stream(**kwargs):
        for event in events_out:
            yield event

    from app.services import extraction_context

    monkeypatch.setattr(extraction_context, "load_product_context", lambda *_a, **_k: "")
    monkeypatch.setattr(copilot_api, "load_company_knowledge", lambda *_a, **_k: None)
    monkeypatch.setattr(copilot_api.call_type, "grounding_for_type", lambda *_a, **_k: None)
    monkeypatch.setattr(copilot_api, "load_suggest_grounding", lambda *_a, **_k: None)
    monkeypatch.setattr(copilot_api, "stream_objection_suggestion", fake_stream)


SUGGEST = {
    "transcript_window": "Them: " + "x" * 5000, "latest_turn": "me parece caro " * 60, "call_mode": "softphone",
    "speaker_role": "prospect", "sales_motion_key": "discovery", "objection_type": "price", "capture_id": "cap-1",
}


def test_a_card_is_logged_with_its_line_provider_and_answer_but_not_the_transcript(monkeypatch):
    result = {"type": "result", "model": "direct:deepseek-ai/DeepSeek-V4.1-Flash", "latency_ms": 912,
              "suggestion": {"is_objection": True, "objection_type": "price", "source_id": "objection:price",
                             "say_this": "Antes de números, ¿cuánto tiempo os cuesta hoy?"}}
    _stub_suggest(monkeypatch, [{"type": "token", "text": "{"}, result])
    db = FakeDb()
    assert _client(db).post("/api/v1/copilot/suggest", json=SUGGEST).status_code == 200
    (row,) = db.inserted
    assert row["kind"] == "suggest" and row["company_id"] == "co-1" and row["capture_id"] == "cap-1"
    assert row["source_id"] == "objection:price" and row["objection_type"] == "price"
    assert row["provider"] == "direct:deepseek-ai/DeepSeek-V4.1-Flash" and row["latency_ms"] == 912
    assert row["say_this"].startswith("Antes de números")
    assert len(row["latest_turn"]) <= events.TEXT_MAX
    assert not {"transcript_window", "rolling_transcript"} & set(row)


def test_an_error_is_logged_too(monkeypatch):
    _stub_suggest(monkeypatch, [{"type": "error", "message": "HTTP 503: provider busy"}])
    db = FakeDb()
    _client(db).post("/api/v1/copilot/suggest", json=SUGGEST)
    assert db.inserted[0]["error"] == "HTTP 503: provider busy" and "say_this" not in db.inserted[0]


def test_a_missing_table_never_breaks_a_call_and_pauses_the_log(monkeypatch):
    result = {"type": "result", "model": "m", "latency_ms": 1, "suggestion": {"is_objection": False, "say_this": ""}}
    _stub_suggest(monkeypatch, [result])
    db = FakeDb(fail=True)
    client = _client(db)
    assert client.post("/api/v1/copilot/suggest", json=SUGGEST).status_code == 200
    assert client.post("/api/v1/copilot/suggest", json=SUGGEST).status_code == 200
    # The second card did not even try: ten minutes of silence after a failure, not a warning per card.
    assert len(db.inserted) == 1


def test_the_log_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(settings, "COPILOT_LOG_EVENTS", False)
    db = FakeDb()
    events.record(db, {"kind": "turn", "user_id": "u"})
    assert db.inserted == []


def test_old_rows_are_deleted_at_most_once_an_hour():
    db = FakeDb()
    events.record(db, {"kind": "turn", "user_id": "u"})
    events.record(db, {"kind": "turn", "user_id": "u"})
    assert len(db.inserted) == 2 and db.deleted == 1


# --- The client's timing stamps ---------------------------------------------------------------------------


STAMPS = {"path": "pause", "quiet_ms": 812, "words_age_ms": 240, "tail_ms": -30, "wait_ms": 0, "deferred": False, "final": False}


def test_a_turn_check_stores_the_clients_timing(monkeypatch):
    _classifier(monkeypatch)
    monkeypatch.setattr(playbook_objections, "custom_for", lambda *_a: {})
    db = FakeDb()
    _client(db).post("/api/v1/copilot/turn", json={
        "transcript_window": "Them: caro", "latest_turn": "me parece caro", "sales_motion_key": "discovery", "timing": STAMPS,
    })
    assert db.inserted[0]["client"] == STAMPS


def test_only_the_known_timing_keys_with_sane_values_are_stored():
    cleaned = events.clean_timing({
        **STAMPS, "path": "somewhere", "quiet_ms": 10**12, "tail_ms": "700", "deferred": "yes",
        "transcript": "everything they said", "extra": {"nested": 1},
    })
    assert cleaned == {"words_age_ms": 240, "wait_ms": 0, "final": False}
    assert events.clean_timing(None) is None and events.clean_timing("x") is None and events.clean_timing({"a": 1}) is None
    assert events.clean_timing({"quiet_ms": True}) is None  # a boolean is not a number of milliseconds


def test_a_check_without_timing_logs_as_before(monkeypatch):
    _classifier(monkeypatch)
    monkeypatch.setattr(playbook_objections, "custom_for", lambda *_a: {})
    db = FakeDb()
    _turn(_client(db))
    assert "client" not in db.inserted[0]


class NoClientColumn(FakeDb):
    """The table exists but migration 080 (the client column) has not been applied."""

    def table(self, name):
        db = self

        class Table(FakeTable):
            def insert(self, row):
                if "client" in row:
                    db.refused += 1
                    raise RuntimeError("column live_assist_events.client does not exist")
                return super().insert(row)

        return Table(self) if name == events.TABLE else Other()

    refused = 0


def test_without_the_client_column_the_row_is_kept_and_later_ones_do_not_try_again(monkeypatch):
    monkeypatch.setattr(events, "_no_client_until", 0.0)
    db = NoClientColumn()
    row = {"kind": "turn", "user_id": "u", "client": STAMPS}
    events.record(db, dict(row))
    events.record(db, dict(row))
    assert len(db.inserted) == 2 and all("client" not in r for r in db.inserted)
    assert db.refused == 1
