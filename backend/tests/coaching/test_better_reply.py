"""Coaching → "Mejor": the line a rep could have said, written only from the playbook and the company."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-better-reply-tests-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-better-reply-tests-32")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import coaching as coaching_api
from app.deps import get_membership, get_supabase
from app.services.coaching import better_reply as better
from app.services.company import Membership
from tests.reporting.fake_db import FakeDB

COMPANY = "77777777-7777-7777-7777-777777777777"
REP = "88888888-8888-8888-8888-888888888888"
OTHER = "66666666-6666-6666-6666-666666666666"

ENTRIES = [
    {"category": "timing", "entry_id": "e1", "guidance": "Pregunta qué significa «ahora no» sin asumir; ofrece una agenda de 20 minutos."},
    {"category": "price", "entry_id": "e2", "guidance": ""},
]
STEPS = [{"step_id": "s1", "label": "Abrir con autoridad", "criterion": "Cita algo concreto del prospecto", "example": "Vi vuestra operación con Intra."}]


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    better._cache.clear()
    from app.services import feature_flags

    feature_flags.clear_cache()
    monkeypatch.setattr(coaching_api.reads, "load_published_playbook", lambda *_: {"published": True, "steps": STEPS, "entries": ENTRIES})
    monkeypatch.setattr("app.services.copilot.load_grounding.load_company_knowledge", lambda *_, **__: {"value_short": "CRM por voz"})
    yield


def _client(*, user=REP) -> TestClient:
    app = FastAPI()
    app.include_router(coaching_api.router)
    store = FakeDB({
        "memos": [{"id": "m1", "user_id": user, "company_id": COMPANY, "sales_motion_key": "discovery"}],
        "company_members": [{"company_id": COMPANY, "user_id": REP, "role": "member", "status": "active"}],
        "company_feature_flags": [],
    })
    app.dependency_overrides[get_membership] = lambda: Membership(id="m", company_id=COMPANY, user_id=REP, role="member", status="active")
    app.dependency_overrides[get_supabase] = lambda: store
    return TestClient(app)


def _body(**over):
    return {"type": "discovery", "kind": "objection", "key": "timing", "memo_id": "m1", "quote": "Ahora no es buen momento", **over}


def test_the_prompt_carries_the_playbook_and_the_moment():
    base = better.playbook_text_for_objection({"label": None, "how": ENTRIES[0]["guidance"]}, ENTRIES[0])
    messages = better.build_messages(kind="objection", playbook_text=base, said="Ahora no", reply=None, reason=None, knowledge="")
    text = messages[-1]["content"]
    assert "ahora no" in text.lower() and "did not reply" in text and "agenda de 20 minutos" in text


def test_an_objection_without_an_answer_in_the_playbook_has_no_base():
    assert better.playbook_text_for_objection({"label": None, "how": None}, ENTRIES[1]) is None


def test_the_model_line_is_cleaned_and_bounded():
    assert better._accept({"say": "  «Entiendo. ¿Qué cambiaría en un mes?» "}) == "Entiendo. ¿Qué cambiaría en un mes?"
    assert better._accept({"say": None}) is None
    assert len(better._accept({"say": "a" * 900})) == better.SAY_MAX_CHARS


def test_returns_the_line_and_asks_the_model_once(monkeypatch):
    calls = []

    async def ask(messages):
        calls.append(messages)
        return {"say": "Entiendo. ¿Ahora no por agenda o por prioridad?"}

    monkeypatch.setattr(better, "_ask", ask)
    client = _client()
    first = client.post("/api/v1/coaching/me/better-reply", json=_body())
    second = client.post("/api/v1/coaching/me/better-reply", json=_body())
    assert first.json() == {"say": "Entiendo. ¿Ahora no por agenda o por prioridad?", "reason": None} == second.json()
    assert len(calls) == 1


def test_no_playbook_answer_never_calls_the_model(monkeypatch):
    async def ask(messages):  # pragma: no cover
        raise AssertionError("must not be called")

    monkeypatch.setattr(better, "_ask", ask)
    out = _client().post("/api/v1/coaching/me/better-reply", json=_body(key="price")).json()
    assert out == {"say": None, "reason": "no_playbook_answer"}


def test_a_step_is_written_from_its_example(monkeypatch):
    async def ask(messages):
        assert "Vi vuestra operación con Intra." in messages[-1]["content"]
        return {"say": "Vi vuestra operación con Intra y me llamó la atención."}

    monkeypatch.setattr(better, "_ask", ask)
    out = _client().post("/api/v1/coaching/me/better-reply", json=_body(kind="step", key="s1", reason="No citó nada")).json()
    assert out["say"].startswith("Vi vuestra operación")


def test_a_model_failure_is_a_502_and_is_not_cached(monkeypatch):
    async def ask(messages):
        raise RuntimeError("down")

    monkeypatch.setattr(better, "_ask", ask)
    assert _client().post("/api/v1/coaching/me/better-reply", json=_body()).status_code == 502
    assert better._cache == {}


def test_someone_elses_memo_is_not_found(monkeypatch):
    assert _client(user=OTHER).post("/api/v1/coaching/me/better-reply", json=_body()).status_code == 404


def test_the_excerpt_is_what_was_said_around_the_quote():
    transcript = "Hola, soy Ana.   Prospecto: nosotros ya tenemos un CRM que funciona bien. Rep: entiendo, ¿qué CRM usáis? Prospecto: HubSpot."
    out = better.excerpt(transcript, "entiendo, ¿qué CRM usáis?")
    assert "ya tenemos un CRM" in out and "HubSpot" in out
    assert better.excerpt(transcript, "algo que nadie dijo en la llamada") is None
    assert better.excerpt(transcript, "corto") is None


def test_a_reply_with_no_answer_field_is_asked_once_more(monkeypatch):
    answers = iter([{}, {"say": "Vale. ¿Qué cambiaría en un mes?"}])
    calls = []

    async def ask(messages):
        calls.append(1)
        return next(answers)

    monkeypatch.setattr(better, "_ask", ask)
    out = _client().post("/api/v1/coaching/me/better-reply", json=_body()).json()
    assert out["say"] == "Vale. ¿Qué cambiaría en un mes?" and len(calls) == 2
