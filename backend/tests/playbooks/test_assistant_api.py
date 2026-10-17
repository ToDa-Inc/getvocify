"""The playbook assistant API (/api/v1/playbook-assistant): owner/admin only, dark behind PLAYBOOK_ASSISTANT_ENABLED,
and a calm 503 `not_activated` until the migration 083 tables exist."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.playbook_assistant import router
from app.config import settings
from app.deps import get_membership, get_supabase
from app.services import feature_flags
from app.services.company import Membership
from app.services.playbooks.api_support import set_playbook_transcriber
from app.services.playbooks.assistant_store import InMemoryAssistantStore, SqlAssistantStore, set_assistant_store
from app.services.playbooks.repository import InMemoryPlaybookRepository, set_playbook_repository
from app.services.playbooks.structure import set_playbook_structure_llm
from tests.playbooks.test_structure import FakeLLM
from tests.reporting.fake_db import FakeDB

BASE = "/api/v1/playbook-assistant"
STEP = {"step_id": "apertura", "label": "Apertura", "criterion": "Se presenta y pide un minuto."}
ADDED = {
    "summary": "Añadida la respuesta a «Integración con Salesforce».",
    "objections": [{
        "category": "custom", "label": "Integración con Salesforce", "trigger": "¿Se integra con Salesforce?",
        "guidance": "Sí, con Salesforce y HubSpot.",
    }],
}
TRANSCRIPT = (
    "Rep: Hola Marcos, soy Dani de Vocify, ¿tienes un minuto?\nCliente: Sí, dime.\n"
    "Rep: Te llamo por cómo apuntáis lo que pasa en cada visita.\nCliente: En un Excel.\n"
)
OPENING = "Hola Marcos, soy Dani de Vocify, ¿tienes un minuto?"
MODEL = {"step_examples": [{"step_index": 1, "example": OPENING, "excerpt": [{"speaker": "rep", "text": OPENING}]}], "objection_branches": []}


class _MissingTables(FakeDB):
    def table(self, name):
        if name.startswith("playbook_"):
            raise RuntimeError(f"Could not find the table 'public.{name}' in the schema cache")
        return super().table(name)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(settings, "PLAYBOOK_ASSISTANT_ENABLED", True)
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()
    for reset in (set_assistant_store, set_playbook_repository, set_playbook_structure_llm, set_playbook_transcriber):
        reset(None)


def make_client(*, role="owner", db=None, store="memory", seed=True):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co-1", user_id="u-1", role=role, status="active", sales_role=None,
    )
    database = db if db is not None else FakeDB()
    app.dependency_overrides[get_supabase] = lambda: database
    repo = InMemoryPlaybookRepository()
    if seed:
        repo.save_draft("co-1", "discovery", [STEP], [])
    set_playbook_repository(repo)
    set_assistant_store(InMemoryAssistantStore() if store == "memory" else None)
    client = TestClient(app)
    client.repo = repo
    return client


def start(client, **body):
    return client.post(f"{BASE}/gaps/session", json={"motion_key": "discovery", "lang": "es", **body})


# --- who may, and when ---------------------------------------------------------------------------


def test_it_is_dark_unless_the_company_is_switched_on(monkeypatch):
    monkeypatch.setattr(settings, "PLAYBOOK_ASSISTANT_ENABLED", False)
    feature_flags.clear_cache()
    assert start(make_client()).status_code == 404


def test_only_an_owner_or_admin_may_use_it():
    assert start(make_client(role="member")).status_code == 403


def test_without_the_tables_it_says_not_activated_instead_of_failing():
    client = make_client(db=_MissingTables(), store="sql")
    response = start(client)
    assert response.status_code == 503 and response.json()["detail"] == {"code": "not_activated"}


# --- the guided questions ------------------------------------------------------------------------


def test_a_session_answer_skip_and_undo_round_trip():
    set_playbook_structure_llm(FakeLLM(ADDED))
    client = make_client()
    session = start(client).json()
    assert 1 <= session["total"] <= 10 and session["answered"] == 0 and session["current"]["question"]
    assert "request" not in session["current"]
    again = client.get(f"{BASE}/gaps/session/current").json()["session"]
    assert again["id"] == session["id"]

    key = session["current"]["key"]
    answered = client.post(f"{BASE}/gaps/session/{session['id']}/answer", json={"gap_key": key, "kind": "text", "payload": "Sí, con Salesforce y HubSpot."})
    assert answered.status_code == 200
    body = answered.json()
    assert body["saved_line"] == ADDED["summary"] and body["session"]["answered"] == 1
    assert [o["label"] for o in body["editor"]["objections"]] == ["Integración con Salesforce"]

    undone = client.post(f"{BASE}/gaps/session/{session['id']}/undo", json={"gap_key": key})
    assert undone.status_code == 200 and undone.json()["answered"] == 0

    skipped = client.post(f"{BASE}/gaps/session/{session['id']}/skip", json={"gap_key": key}).json()
    assert skipped["skipped"] == 1 and skipped["current"]["key"] != key


def test_nothing_open_means_no_session():
    assert make_client().get(f"{BASE}/gaps/session/current").json() == {"session": None}


def test_unknown_session_and_nothing_to_undo_have_clear_codes():
    client = make_client()
    assert client.post(f"{BASE}/gaps/session/nope/skip", json={"gap_key": "x"}).json()["detail"] == {"code": "session_not_found"}
    session = start(client).json()
    undo = client.post(f"{BASE}/gaps/session/{session['id']}/undo", json={"gap_key": session["current"]["key"]})
    assert undo.status_code == 409 and undo.json()["detail"] == {"code": "nothing_to_undo"}


def test_a_model_that_changes_nothing_is_a_422_and_audio_without_speech_too():
    set_playbook_structure_llm(FakeLLM({"summary": "Nada."}))
    set_playbook_transcriber(lambda _p: "")
    client = make_client()
    session = start(client).json()
    key = session["current"]["key"]
    url = f"{BASE}/gaps/session/{session['id']}/answer"
    assert client.post(url, json={"gap_key": key, "kind": "text", "payload": "ok"}).json()["detail"] == {"code": "fill_failed"}
    assert client.post(url, json={"gap_key": key, "kind": "audio", "payload": "AAAA"}).json()["detail"] == {"code": "audio_has_no_speech"}


# --- model calls (read once, never stored) -----------------------------------------------------------


def propose(client, **body):
    return client.post(f"{BASE}/model-calls/propose", json={"motion_key": "discovery", **body})


def test_a_model_call_is_read_and_its_proposals_applied_without_storing_the_call():
    set_playbook_structure_llm(FakeLLM(MODEL))
    client = make_client()
    read = propose(client, transcript=TRANSCRIPT)
    assert read.status_code == 200
    body = read.json()
    assert body["speaker_warning"] is False and [p["id"] for p in body["proposals"]] == ["p1"]
    assert "id" not in body

    applied = client.post(f"{BASE}/model-calls/apply", json={"motion_key": "discovery", "proposals": body["proposals"]})
    assert applied.status_code == 200
    result = applied.json()
    assert result["applied"] == ["p1"] and result["skipped"] == []
    assert result["editor"]["steps"][0]["example"] == OPENING


def test_a_proposal_the_boss_rewrote_is_what_gets_applied():
    set_playbook_structure_llm(FakeLLM(MODEL))
    client = make_client()
    [proposal] = propose(client, transcript=TRANSCRIPT).json()["proposals"]
    proposal["text"] = "Hola, soy Dani, ¿tienes un minuto?"
    result = client.post(f"{BASE}/model-calls/apply", json={"motion_key": "discovery", "proposals": [proposal]}).json()
    assert result["editor"]["steps"][0]["example"] == "Hola, soy Dani, ¿tienes un minuto?"


def test_it_works_before_the_tables_exist_because_nothing_is_stored():
    set_playbook_structure_llm(FakeLLM(MODEL))
    client = make_client(db=_MissingTables(), store="sql")
    assert propose(client, transcript=TRANSCRIPT).status_code == 200


def test_a_call_needs_exactly_one_transcript_and_a_readable_one():
    client = make_client()
    both = propose(client, transcript="Rep: hola", memo_id="m1")
    neither = propose(client)
    blank = propose(client, transcript="   ")
    assert both.status_code == neither.status_code == 422
    assert both.json()["detail"] == {"code": "one_transcript_needed"}
    assert blank.status_code == 422 and blank.json()["detail"] == {"code": "empty_transcript"}
    long = propose(client, transcript="Rep: hola\n" * 10_000)
    assert long.status_code == 422 and long.json()["detail"] == {"code": "transcript_too_long"}


def test_a_call_of_the_company_can_be_chosen_and_one_of_another_company_cannot():
    set_playbook_structure_llm(FakeLLM(MODEL))
    memos = [
        {"id": "mine", "company_id": "co-1", "transcript": TRANSCRIPT, "created_at": "2026-10-10T10:00:00+00:00", "sales_motion_key": "discovery", "extraction": {"summary": "Llamada de apertura con Marcos."}},
        {"id": "theirs", "company_id": "co-2", "transcript": TRANSCRIPT, "created_at": "2026-10-11T10:00:00+00:00", "sales_motion_key": "discovery", "extraction": {}},
    ]
    client = make_client(db=FakeDB({"memos": memos}))
    assert propose(client, memo_id="theirs").status_code == 404
    assert propose(client, memo_id="mine").status_code == 200
    recent = client.get(f"{BASE}/model-calls/recent").json()["calls"]
    assert [c["id"] for c in recent] == ["mine"] and recent[0]["summary"] == "Llamada de apertura con Marcos."


def test_a_branch_that_does_not_fit_is_reported_and_can_become_an_own_objection():
    branch = {"step_examples": [], "objection_branches": [{
        "category": "price", "label": None, "when": "lo comparan con algo gratis", "answer": "Pregunta cuánto tiempo pierden.",
        "excerpt": [{"speaker": "client", "text": "Sí, dime."}, {"speaker": "rep", "text": "En un Excel."}],
    }]}
    set_playbook_structure_llm(FakeLLM(branch))
    client = make_client()
    client.repo.save_draft("co-1", "discovery", [STEP], [{"category": "price", "guidance": "x" * 1195, "entry_id": "objection:price", "source_ref": "editor"}])
    [proposal] = propose(client, transcript=TRANSCRIPT).json()["proposals"]
    first = client.post(f"{BASE}/model-calls/apply", json={"motion_key": "discovery", "proposals": [proposal]}).json()
    assert first["applied"] == [] and first["skipped"] == [{"id": "p1", "code": "guidance_too_long"}]
    own = {**proposal, "as_custom": "Es caro, usamos algo gratis"}
    second = client.post(f"{BASE}/model-calls/apply", json={"motion_key": "discovery", "proposals": [own]}).json()
    assert second["applied"] == ["p1"]
    assert second["editor"]["objections"][-1]["label"] == "Es caro, usamos algo gratis"


# --- several documents at once -------------------------------------------------------------------

SDR = {
    "key": "discovery", "reason": None,
    "steps": [
        {"label": "Apertura con permiso", "criterion": "Se presenta y pregunta si tiene un minuto antes de contar nada."},
        {"label": "Motivo y leads", "criterion": "Dice por qué llama y pregunta cómo llevan hoy el seguimiento de leads."},
    ],
    "objections": [{"category": "price", "guidance": "Lo comparamos con lo que pierden al mes."}],
}
SECOND = {
    "key": "discovery", "reason": None,
    "steps": [{"label": "Cierre con fecha", "criterion": "Acuerdan una fecha concreta para la reunión."}],
    "objections": [{"category": "timing", "guidance": "Lo vemos en dos semanas."}],
}
DOC_A = "Guion SDR de llamada en frío: me presento y pregunto si tiene un minuto, digo por qué llamo y cómo llevan el seguimiento de leads."
DOC_B = "Cierre: acordamos una fecha para la reunión. Precio: desde 49 € al mes por usuario. Si dicen que ahora no, lo vemos en dos semanas."


def test_several_documents_become_one_draft_and_an_unreadable_one_is_named():
    llm = FakeLLM({"types": [SDR], "company": {}}, {"questions": []}, {"types": [SECOND], "company": {"pricing": "Desde 49 € al mes por usuario."}}, {"questions": []})
    set_playbook_structure_llm(llm)
    set_playbook_transcriber(lambda _p: "")
    client = make_client(seed=False)
    client.repo.save_knowledge("co-1", {"pricing": "Desde 39 € al mes por usuario."})
    response = client.post(f"{BASE}/intake", json={"sources": [
        {"kind": "text", "payload": DOC_A, "name": "guion.txt"},
        {"kind": "audio", "payload": "AAAA", "name": "nota.m4a"},
        {"kind": "text", "payload": DOC_B, "name": "cierre.txt"},
    ]})
    assert response.status_code == 200
    body = response.json()
    assert body["failed"] == [{"name": "nota.m4a", "code": "audio_has_no_speech"}]
    assert [t["sales_motion_key"] for t in body["types"]] == ["discovery"]
    editor = body["types"][0]["editor"]
    assert [s["label"] for s in editor["steps"]] == ["Apertura con permiso", "Motivo y leads", "Cierre con fecha"]
    assert [o["category"] for o in editor["objections"]] == ["price", "timing"]
    assert [c["key"] for c in body["conflicts"]] == ["conflict:pricing"] and "request" not in body["conflicts"][0]
    # What the documents disagree about is the first thing the guided questions ask.
    assert client.get(f"{BASE}/gaps/session/current").json()["session"]["current"]["key"] == "conflict:pricing"
    assert len(llm.calls) == 4
    assert client.repo.get_knowledge("co-1")["data"]["pricing"] == "Desde 39 € al mes por usuario."


def test_when_nothing_can_be_read_nothing_is_saved():
    set_playbook_transcriber(lambda _p: "")
    client = make_client(seed=False)
    body = client.post(f"{BASE}/intake", json={"sources": [{"kind": "audio", "payload": "AAAA", "name": "nota.m4a"}]}).json()
    assert body["types"] == [] and body["failed"] == [{"name": "nota.m4a", "code": "audio_has_no_speech"}]


def test_between_one_and_eight_documents_are_accepted():
    client = make_client()
    assert client.post(f"{BASE}/intake", json={"sources": []}).status_code == 422
    assert client.post(f"{BASE}/intake", json={"sources": [{"kind": "text", "payload": "x"}] * 9}).status_code == 422
