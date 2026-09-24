"""F03 brief: three facts at most. Never spoken is not the same as nothing left."""

import pathlib
from types import SimpleNamespace

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-briefs-32b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-briefs-32b")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import briefs as briefs_api
from app.deps import get_membership, get_supabase
from app.services.briefs.preparation import prepare_brief
from app.services.company import Membership


def test_never_spoken_is_one_sentence_and_can_add_a_real_crm_task():
    bare = prepare_brief(coverage="complete")
    assert bare["status"] == "no_conversation"
    assert bare["text"] == "Sin conversación todavía."
    assert bare["lines"] == []

    with_task = prepare_brief(
        coverage="complete",
        crm_task={"text": "Llamar el jueves", "source_ref": "task-1"},
    )
    assert with_task["lines"] == [{
        "type": "crm",
        "text": "Llamar el jueves",
        "source_ref": "task-1",
        "observed_at": None,
    }]
    assert "Última vez" not in with_task["text"]


def test_a_call_that_left_nothing_is_not_a_missing_contact():
    brief = prepare_brief(
        coverage="complete",
        last={"observed_at": "2026-09-02T10:00:00Z", "text": ""},
    )
    assert brief["status"] == "nothing_pending"
    assert brief["text"] == "Última vez: 2026-09-02. No quedó nada pendiente."
    assert brief["lines"] == []


def test_only_real_facts_are_shown_and_the_playbook_stays_on_the_objection():
    brief = prepare_brief(
        coverage="complete",
        last={"text": "El 2 sep hablasteis del almacén.", "observed_at": "2026-09-02", "source_ref": "memo-1"},
        pending={"text": "Quedó pendiente: enviar el caso de logística.", "source_ref": "memo-1"},
        objection={"text": "Objeción: el precio.", "playbook": "Comparar con el coste del retraso.", "source_ref": "memo-1"},
        pain_confirmed=True,
    )
    assert brief["status"] == "ready"
    assert [line["type"] for line in brief["lines"]] == ["last", "pending", "objection"]
    assert brief["lines"][2]["text"] == "Objeción: el precio. Comparar con el coste del retraso."


def test_a_failed_read_is_not_an_empty_history():
    brief = prepare_brief(coverage="partial", last={"text": "Hablasteis del plazo.", "source_ref": "memo-1"})
    assert brief["status"] == "partial"
    assert brief["text"] == "No se pudo cargar todo."
    assert brief["lines"][0]["text"] == "Hablasteis del plazo."

    down = prepare_brief(coverage="unavailable")
    assert down["status"] == "unavailable"
    assert down["lines"] == []


def test_a_crm_task_does_not_appear_once_there_is_a_conversation():
    brief = prepare_brief(
        coverage="complete",
        last={"observed_at": "2026-09-02", "text": ""},
        crm_task={"text": "Llamar el jueves", "source_ref": "task-1"},
    )
    assert brief["status"] == "nothing_pending"
    assert brief["lines"] == []


def test_every_fact_line_names_its_source():
    brief = prepare_brief(
        coverage="complete",
        last={"text": "El 2 sep hablasteis del almacén.", "observed_at": "2026-09-02", "source_ref": "memo-1"},
        pending={"text": "Quedó pendiente: enviar el caso.", "source_ref": "memo-2"},
        objection={"text": "Objeción: el precio.", "source_ref": "memo-3"},
        pain_confirmed=True,
    )
    for line in brief["lines"]:
        assert line.get("source_ref")


def test_preparation_stays_read_only_without_a_model():
    root = pathlib.Path(__file__).resolve().parents[2] / "app"
    for rel in ("services/briefs/preparation.py", "api/briefs.py"):
        text = (root / rel).read_text(encoding="utf-8").lower()
        assert "openai" not in text
        assert "anthropic" not in text
        assert "invoke_llm" not in text
        assert "llm_service" not in text


def test_get_brief_uses_the_loader_for_that_contact():
    def load(**kwargs):
        assert kwargs["contact_id"] == "42"
        return {"coverage": "complete"}

    briefs_api.set_brief_loader(load)
    try:
        app = FastAPI()
        app.include_router(briefs_api.router)
        app.dependency_overrides[get_membership] = lambda: Membership(
            id="m", company_id="co-1", user_id="user-a", role="member", status="active",
        )
        app.dependency_overrides[get_supabase] = lambda: object()
        body = TestClient(app).get("/api/v1/briefs", params={"connection_id": "crm-A", "contact_id": "42"}).json()
    finally:
        briefs_api.set_brief_loader(None)
    assert body["status"] == "no_conversation"
    assert body["text"] == "Sin conversación todavía."


class _MemoQuery:
    def __init__(self, rows):
        self.rows = rows
        self.eqs = []
        self.order_by = None
        self.limit_n = None

    def select(self, _cols):
        return self

    def eq(self, column, value):
        self.eqs.append((column, value))
        return self

    def order(self, column, desc=False):
        self.order_by = (column, desc)
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def execute(self):
        rows = list(self.rows)
        for column, value in self.eqs:
            rows = [row for row in rows if row.get(column) == value]
        if self.order_by is not None:
            column, desc = self.order_by
            rows = sorted(rows, key=lambda row: str(row.get(column) or ""), reverse=desc)
        if self.limit_n is not None:
            rows = rows[: self.limit_n]
        return SimpleNamespace(data=rows)


class _FakeMemos:
    def __init__(self, rows):
        self.query = None
        self._rows = rows

    def table(self, name):
        assert name == "memos"
        self.query = _MemoQuery(self._rows)
        return self.query


def _memo(*, memo_id, created_at, contact_id, summary, deal_id=None, matched_deal_id=None, connection_id=None, extra_extraction=None):
    extraction = {"summary": summary}
    if extra_extraction:
        extraction.update(extra_extraction)
    return {
        "id": memo_id,
        "company_id": "co-1",
        "created_at": created_at,
        "hubspot_contact_id": contact_id,
        "hubspot_deal_id": deal_id,
        "matched_deal_id": matched_deal_id,
        "crm_connection_id": connection_id,
        "extraction": extraction,
    }


def test_from_memos_matches_the_contact_column_not_extraction():
    matching = _memo(
        memo_id="memo-match",
        created_at="2026-09-02T10:00:00Z",
        contact_id="42",
        summary="El 2 sep hablasteis del almacén.",
    )
    other = _memo(
        memo_id="memo-other",
        created_at="2026-09-04T10:00:00Z",
        contact_id="99",
        summary="Esta no es la conversación.",
        extra_extraction={"contact_id": "42"},
    )
    older = _memo(
        memo_id="memo-old",
        created_at="2026-09-01T10:00:00Z",
        contact_id="42",
        summary="Versión vieja.",
    )
    fake = _FakeMemos([other, older, matching])
    facts = briefs_api._from_memos(fake, "co-1", "42")
    assert facts["coverage"] == "complete"
    assert facts["last"]["text"] == "El 2 sep hablasteis del almacén."
    assert facts["last"]["source_ref"] == "memo-match"
    assert ("hubspot_contact_id", "42") in fake.query.eqs
    assert ("company_id", "co-1") in fake.query.eqs
    assert fake.query.order_by == ("created_at", True)
    assert fake.query.limit_n == 100


def test_from_memos_deal_id_filters_on_the_contact_column():
    wrong_deal = _memo(
        memo_id="memo-wrong-deal",
        created_at="2026-09-04T10:00:00Z",
        contact_id="42",
        summary="Otro deal.",
        deal_id="D9",
    )
    matched = _memo(
        memo_id="memo-matched",
        created_at="2026-09-03T10:00:00Z",
        contact_id="42",
        summary="Match por matched_deal_id.",
        matched_deal_id="D1",
    )
    hubspot_deal = _memo(
        memo_id="memo-hubspot",
        created_at="2026-09-02T10:00:00Z",
        contact_id="42",
        summary="Match por hubspot_deal_id.",
        deal_id="D1",
    )
    fake = _FakeMemos([wrong_deal, matched, hubspot_deal])
    facts = briefs_api._from_memos(fake, "co-1", "42", connection_id=None, deal_id="D1")
    assert facts["last"]["text"] == "Match por matched_deal_id."
    assert facts["last"]["source_ref"] == "memo-matched"


def test_get_brief_filters_connection_on_the_contact_column():
    other_connection = _memo(
        memo_id="memo-other-crm",
        created_at="2026-09-04T10:00:00Z",
        contact_id="42",
        summary="Otra conexión.",
        connection_id="crm-B",
    )
    matching = _memo(
        memo_id="memo-crm-a",
        created_at="2026-09-02T10:00:00Z",
        contact_id="42",
        summary="El 2 sep hablasteis del almacén.",
        connection_id="crm-A",
        extra_extraction={"pain_confirmed": True},
    )
    fake = _FakeMemos([other_connection, matching])
    app = FastAPI()
    app.include_router(briefs_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co-1", user_id="user-a", role="member", status="active",
    )
    app.dependency_overrides[get_supabase] = lambda: fake
    body = TestClient(app).get(
        "/api/v1/briefs",
        params={"connection_id": "crm-A", "contact_id": "42"},
    ).json()
    assert body["status"] == "ready"
    assert body["lines"][0]["text"] == "El 2 sep hablasteis del almacén."
    assert body["lines"][0]["source_ref"] == "memo-crm-a"
    assert ("crm_connection_id", "crm-A") in fake.query.eqs
    assert ("hubspot_contact_id", "42") in fake.query.eqs
