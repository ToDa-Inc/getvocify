"""F03 brief: three facts at most. Never spoken is not the same as nothing left."""

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
