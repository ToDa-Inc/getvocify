"""The turn check: one fast classifier call says whether the prospect finished their thought and
which objection, if any, it is. The help card shows the moment both are known."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import copilot as copilot_api
from app.deps import get_membership, get_supabase, get_user_id
from app.services.company import Membership
from app.services.copilot import turn
from app.services.copilot.prompts import build_user_prompt
from app.services.llm.jev import JevClient


def _answers(monkeypatch, answers):
    seen = {}

    async def fake_post(self, state, questions):
        seen["state"], seen["questions"] = state, questions
        return answers

    monkeypatch.setattr(JevClient, "_post_systemone", fake_post)
    monkeypatch.setattr(JevClient, "is_available", property(lambda self: True))
    return seen


def _read(window="Them: Somos ocho comerciales.", latest="me parece bastante caro"):
    return asyncio.run(turn.read_turn(window, latest))


def test_a_finished_objection_names_its_type(monkeypatch):
    seen = _answers(monkeypatch, {
        "turn": {"choice": "finished", "confidence": 0.77},
        "objection": {"choice": "price", "confidence": 1},
    })
    assert _read() == {"finished": True, "objection": "price"}
    assert seen["state"] == {"conversation": "Them: Somos ocho comerciales.", "LATEST": "me parece bastante caro"}
    assert set(seen["questions"]) == {"turn", "objection"}
    assert set(seen["questions"]["objection"]["criteria"]) == set(turn.OBJECTIONS)


def test_a_thought_still_going_is_not_finished(monkeypatch):
    _answers(monkeypatch, {
        "turn": {"choice": "continuing", "confidence": 1},
        "objection": {"choice": "none", "confidence": 0.94},
    })
    assert _read(latest="Ya, pero la verdad es que me parece") == {"finished": False, "objection": "none"}


def test_an_unsure_answer_never_raises_a_card_or_holds_one_back(monkeypatch):
    _answers(monkeypatch, {
        "turn": {"choice": "continuing", "confidence": 0.4},
        "objection": {"choice": "trust", "confidence": 0.4},
    })
    assert _read() == {"finished": True, "objection": "none"}


def test_an_answer_outside_the_list_is_no_objection(monkeypatch):
    _answers(monkeypatch, {
        "turn": {"choice": "finished", "confidence": 0.9},
        "objection": {"choice": "weather", "confidence": 1},
    })
    assert _read()["objection"] == "none"


def test_no_classifier_says_so_and_the_caller_falls_back(monkeypatch):
    _answers(monkeypatch, None)
    assert _read() == {"finished": None, "objection": None}


# --- HTTP -------------------------------------------------------------------------------------------


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(copilot_api.router)
    app.dependency_overrides[get_supabase] = lambda: object()
    app.dependency_overrides[get_user_id] = lambda: "user-1"
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m-1", company_id="co-1", user_id="user-1", role="member", status="active",
    )
    return TestClient(app)


def test_turn_endpoint_returns_the_check(monkeypatch):
    _answers(monkeypatch, {
        "turn": {"choice": "finished", "confidence": 0.97},
        "objection": {"choice": "authority", "confidence": 1},
    })
    response = _client().post("/api/v1/copilot/turn", json={
        "transcript_window": "Them: esto no lo decido yo", "latest_turn": "esto no lo decido yo",
    })
    assert response.status_code == 200
    assert response.json() == {"finished": True, "objection": "authority"}


def test_an_internal_call_asks_no_classifier(monkeypatch):
    async def never(self, state, questions):
        raise AssertionError("no classifier on an internal call")

    monkeypatch.setattr(JevClient, "_post_systemone", never)
    response = _client().post("/api/v1/copilot/turn", json={
        "transcript_window": "Them: ¿cuánto cuesta?", "latest_turn": "¿cuánto cuesta?", "sales_motion_key": "internal",
    })
    assert response.json() == {"finished": True, "objection": "none"}


# --- The answer, once the type is known ---------------------------------------------------------------


def _prompt(**extra):
    return build_user_prompt(
        transcript_window="Them: me parece caro", latest_turn="me parece caro",
        product_context=None, language="auto", call_mode="meeting", speaker_role="prospect", **extra,
    )


def test_the_answer_is_written_for_the_type_already_on_screen():
    prompt = _prompt(objection_type="price")
    assert "ALREADY SHOWN TO THE REP: price" in prompt
    assert "ALREADY SHOWN" not in _prompt()


def test_the_line_continues_from_the_filler_the_rep_just_said():
    # 2026-10-05 live test: "Claro, que lo vea quien decide…" then "Perfecto, ¿me pasas su contacto?"
    # acknowledged twice, and "Sí, te cuento…" then "No tengo confirmado…" contradicted itself.
    prompt = _prompt(objection_type="authority", filler="Claro, que lo vea quien decide…")
    assert "THE REP HAS JUST SAID: \"Claro, que lo vea quien decide…\"" in prompt
    assert "next sentence" in prompt and "never repeats or contradicts" in prompt
    assert "THE REP HAS JUST SAID" not in _prompt(objection_type="authority")


def test_suggest_passes_the_type_on_screen_to_the_model(monkeypatch):
    seen = {}

    async def fake_stream(**kwargs):
        seen.update(kwargs)
        yield {"type": "result", "suggestion": {"is_objection": False}}

    from app.services import extraction_context

    monkeypatch.setattr(extraction_context, "load_product_context", lambda *_a, **_k: "")
    monkeypatch.setattr(copilot_api, "load_company_knowledge", lambda *_a, **_k: None)
    monkeypatch.setattr(copilot_api, "load_company_suggest_grounding", lambda *_a, **_k: None)
    monkeypatch.setattr(copilot_api, "stream_objection_suggestion", fake_stream)
    _client().post("/api/v1/copilot/suggest", json={
        "transcript_window": "Them: me parece caro", "latest_turn": "me parece caro",
        "call_mode": "meeting", "speaker_role": "prospect", "objection_type": "price",
        "filler": "Es normal mirarlo con lupa…",
    })
    assert seen["objection_type"] == "price"
    assert seen["filler"] == "Es normal mirarlo con lupa…"


def test_a_goodbye_or_an_agreed_next_step_is_no_objection():
    # 2026-10-05 live test: "Vale, pues lo hablamos la semana que viene. Un saludo" showed a Timing card.
    assert "goodbye" in turn.OBJECTIONS["none"] and "next step" in turn.OBJECTIONS["none"]
    assert "pushback" in turn.OBJECTIONS["timing"].lower()


def test_the_turn_check_needs_a_signed_in_rep_and_no_database_lookup(monkeypatch):
    # Every pause runs it: a company lookup per check only adds a database round trip.
    def no_lookup():
        raise AssertionError("the turn check must not look up the company")

    _answers(monkeypatch, {"turn": {"choice": "finished", "confidence": 0.9}, "objection": {"choice": "price", "confidence": 1}})
    app = FastAPI()
    app.include_router(copilot_api.router)
    app.dependency_overrides[get_user_id] = lambda: "user-1"
    app.dependency_overrides[get_membership] = no_lookup
    app.dependency_overrides[get_supabase] = no_lookup
    response = TestClient(app).post("/api/v1/copilot/turn", json={"transcript_window": "Them: caro", "latest_turn": "me parece caro"})
    assert response.json() == {"finished": True, "objection": "price"}
