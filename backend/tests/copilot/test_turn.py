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
from app.services.copilot import playbook_objections, turn
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


def test_a_fixed_kind_on_screen_follows_that_categorys_approved_answer():
    # 2026-10-14 simulated call: a Timing card answered from another entry the transcript touched.
    assert "follow that one and set source_id to its id" in _prompt(objection_type="timing")
    assert "The label on screen is" not in _prompt(objection_type="question")
    assert "The label on screen is" not in _prompt(entry=SNAPSHOT["entries"][1])


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


def test_the_turn_check_needs_a_signed_in_rep_and_no_company_lookup_without_a_type(monkeypatch):
    # Every pause runs it: with no call type there is no playbook to read, so no database round trip.
    def no_lookup():
        raise AssertionError("the turn check must not look up the company")

    _answers(monkeypatch, {"turn": {"choice": "finished", "confidence": 0.9}, "objection": {"choice": "price", "confidence": 1}})
    app = FastAPI()
    app.include_router(copilot_api.router)
    app.dependency_overrides[get_user_id] = lambda: "user-1"
    app.dependency_overrides[get_membership] = no_lookup
    app.dependency_overrides[get_supabase] = lambda: object()
    response = TestClient(app).post("/api/v1/copilot/turn", json={"transcript_window": "Them: caro", "latest_turn": "me parece caro"})
    assert response.json() == {"finished": True, "objection": "price"}


# --- The playbook's own objections ----------------------------------------------------------------------

DIFFERENT_SALE = "objection:custom:venta_diferente"
EMAIL = "objection:custom:mandame_un_email"
SNAPSHOT = {
    "entries": [
        {"entry_id": "objection:price", "category": "price", "guidance": "Habla de cifras."},
        {"entry_id": DIFFERENT_SALE, "category": "custom", "label": "Venta muy diferente",
         "trigger": "Damos pocas visitas, son proyectos grandes.", "guidance": "Comprueba con números."},
        {"entry_id": EMAIL, "category": "custom", "label": "Mándame un email", "trigger": "", "guidance": "Acepta pero hazlo útil."},
        {"entry_id": "objection:custom:no_answer", "category": "custom", "label": "Sin respuesta", "trigger": "x", "guidance": ""},
    ]
}


def test_only_custom_entries_with_an_answer_reach_the_classifier():
    assert playbook_objections.custom_entries(SNAPSHOT) == {
        DIFFERENT_SALE: {"label": "Venta muy diferente", "trigger": "Damos pocas visitas, son proyectos grandes."},
        EMAIL: {"label": "Mándame un email", "trigger": ""},
    }
    assert playbook_objections.custom_entries(None) == {}


def test_a_turn_that_means_a_custom_objection_is_named_not_filed_under_none(monkeypatch):
    custom = playbook_objections.custom_entries(SNAPSHOT)
    seen = _answers(monkeypatch, {
        "turn": {"choice": "finished", "confidence": 0.9},
        "objection": {"choice": DIFFERENT_SALE, "confidence": 0.9},
    })
    reading = asyncio.run(turn.read_turn("Them: nuestra venta es diferente", "nuestra venta es diferente", custom))
    assert reading == {"finished": True, "objection": "custom", "entry_id": DIFFERENT_SALE, "label": "Venta muy diferente"}
    criteria = seen["questions"]["objection"]["criteria"]
    assert set(criteria) == set(turn.OBJECTIONS) | set(custom)
    assert "Damos pocas visitas" in criteria[DIFFERENT_SALE] and "Venta muy diferente" in criteria[DIFFERENT_SALE]


def test_without_custom_entries_the_classifier_is_asked_exactly_as_before(monkeypatch):
    seen = _answers(monkeypatch, {"turn": {"choice": "finished", "confidence": 0.9}, "objection": {"choice": "price", "confidence": 1}})
    assert _read() == {"finished": True, "objection": "price"}
    assert seen["questions"] is turn.QUESTIONS


def test_an_unsure_custom_match_is_no_objection(monkeypatch):
    _answers(monkeypatch, {
        "turn": {"choice": "finished", "confidence": 0.9},
        "objection": {"choice": EMAIL, "confidence": 0.3},
    })
    assert asyncio.run(turn.read_turn("w", "l", playbook_objections.custom_entries(SNAPSHOT)))["objection"] == "none"


def test_the_endpoint_reads_the_types_own_objections_and_returns_the_match(monkeypatch):
    asked = {}

    def fake_custom(_supabase, user_id, motion):
        asked["who"] = (user_id, motion)
        return playbook_objections.custom_entries(SNAPSHOT)

    monkeypatch.setattr(playbook_objections, "custom_for", fake_custom)
    _answers(monkeypatch, {"turn": {"choice": "finished", "confidence": 0.9}, "objection": {"choice": EMAIL, "confidence": 0.9}})
    response = _client().post("/api/v1/copilot/turn", json={
        "transcript_window": "Them: mándame un email", "latest_turn": "mándame un email", "sales_motion_key": "discovery",
    })
    assert response.json() == {"finished": True, "objection": "custom", "entry_id": EMAIL, "label": "Mándame un email"}
    assert asked["who"] == ("user-1", "discovery")


def test_the_lookup_is_kept_for_a_minute_and_a_failed_one_is_not(monkeypatch):
    playbook_objections._cache.clear()
    reads = []

    def live_snapshot(_supabase, company_id, motion):
        reads.append((company_id, motion))
        return SNAPSHOT

    from app.services import company as company_service
    from app.services.playbooks import live

    monkeypatch.setattr(live, "live_snapshot", live_snapshot)
    monkeypatch.setattr(
        company_service.CompanyService, "require_membership",
        lambda self, user_id: Membership(id="m", company_id="co-1", user_id=user_id, role="member", status="active"),
    )
    first = playbook_objections.custom_for(object(), "user-1", "discovery")
    assert playbook_objections.custom_for(object(), "user-1", "discovery") is first
    assert reads == [("co-1", "discovery")]

    playbook_objections._cache.clear()

    def boom(*_a):
        raise RuntimeError("database down")

    monkeypatch.setattr(live, "live_snapshot", boom)
    assert playbook_objections.custom_for(object(), "user-2", "discovery") == {}
    assert ("user-2", "discovery") not in playbook_objections._cache


def test_the_answer_follows_the_matched_playbook_entry(monkeypatch):
    entry = SNAPSHOT["entries"][1]
    prompt = _prompt(entry=entry, filler="Te entiendo…")
    assert f'OWN OBJECTION "Venta muy diferente" (id {DIFFERENT_SALE})' in prompt
    assert f'source_id to "{DIFFERENT_SALE}"' in prompt
    assert "ALREADY SHOWN TO THE REP: other" in prompt and "THE REP HAS JUST SAID" in prompt
    assert "OWN OBJECTION" not in _prompt()

    seen = {}

    async def fake_stream(**kwargs):
        seen.update(kwargs)
        yield {"type": "result", "suggestion": {"is_objection": False}}

    from app.services import extraction_context
    from app.services.copilot.grounding import SuggestGrounding

    grounding = SuggestGrounding("call", "v1", frozenset(), SNAPSHOT)
    monkeypatch.setattr(extraction_context, "load_product_context", lambda *_a, **_k: "")
    monkeypatch.setattr(copilot_api, "load_company_knowledge", lambda *_a, **_k: None)
    monkeypatch.setattr(copilot_api.call_type, "grounding_for_type", lambda *_a, **_k: grounding)
    monkeypatch.setattr(copilot_api, "stream_objection_suggestion", fake_stream)
    body = {
        "transcript_window": "Them: x", "latest_turn": "nuestra venta es diferente", "call_mode": "softphone",
        "speaker_role": "prospect", "sales_motion_key": "discovery", "objection_type": "custom",
    }
    _client().post("/api/v1/copilot/suggest", json={**body, "entry_id": DIFFERENT_SALE})
    assert seen["entry"]["entry_id"] == DIFFERENT_SALE and seen["objection_type"] is None
    # An id that is not one of this call's answers is ignored: the model is never told to follow it.
    _client().post("/api/v1/copilot/suggest", json={**body, "entry_id": "objection:custom:made_up"})
    assert seen["entry"] is None


# --- Resolving the approved answer's branch; the id the model names; the classifier's reach ----------------


def test_the_model_is_told_to_resolve_branches_from_the_call_or_ask_the_question_that_tells_them_apart():
    from app.services.copilot.prompts import MEETING_SYSTEM_PROMPT, PLAYBOOK_USER_SUFFIX

    # 2026-10-14 simulated call: «no estamos para contratar» was answered from the CRM-migration branch.
    assert "never assume a branch" in PLAYBOOK_USER_SUFFIX
    assert "prefer its wording" in PLAYBOOK_USER_SUFFIX
    assert '"branch"' in MEETING_SYSTEM_PROMPT and "Only these five keys" in MEETING_SYSTEM_PROMPT


def test_a_repeated_objection_isolates_the_cause_before_anything_else():
    prompt = _prompt(previous_answers=["Antes de hablar de números, ¿cuánto os cuesta hoy?"])
    assert "second time" in prompt and "separates the possibilities" in prompt and "dated next step" in prompt


def test_the_bare_category_the_model_writes_is_the_same_approved_answer():
    from app.services.copilot.grounding import canonical_source_id

    # Seen in the live path: "competitor" for "objection:competitor", the right answer with a loose id.
    assert canonical_source_id("competitor", SNAPSHOT | {"entries": SNAPSHOT["entries"] + [
        {"entry_id": "objection:competitor", "category": "competitor", "guidance": "x"}]}) == "objection:competitor"
    assert canonical_source_id("objection:price", SNAPSHOT) == "objection:price"
    assert canonical_source_id("price", SNAPSHOT) == "objection:price"
    assert canonical_source_id("made_up", SNAPSHOT) == "made_up"
    assert canonical_source_id(None, SNAPSHOT) is None
    assert canonical_source_id("price", None) == "price"


def test_a_busy_opener_is_no_objection_and_being_away_for_a_period_is_timing():
    # 2026-10-14: «dime, pero rápido que estoy liado» raised a Timing card; «viajando todo octubre» raised none.
    assert "dime, pero rápido" in turn.OBJECTIONS["none"]
    assert "travelling" in turn.OBJECTIONS["timing"] and "not buying anything" in turn.OBJECTIONS["timing"]


# --- The date the model is told -----------------------------------------------------------------------------


def test_the_model_is_told_todays_date_in_the_reps_timezone_and_may_not_invent_one():
    from datetime import datetime, timezone

    from app.services.copilot.prompts import MEETING_SYSTEM_PROMPT, today_line

    # 2026-10-14 simulated call: «llámame dentro de tres meses» got «te llamo el 12 de mayo».
    late = datetime(2026, 10, 14, 23, 30, tzinfo=timezone.utc)
    assert today_line("Europe/Madrid", late) == "TODAY: Thursday 2026-10-15 (Europe/Madrid)"
    assert today_line("America/Mexico_City", late) == "TODAY: Wednesday 2026-10-14 (America/Mexico_City)"
    assert today_line("Not/AZone", late) == "TODAY: Wednesday 2026-10-14 (UTC)"
    assert "Never write a day of the month" in MEETING_SYSTEM_PROMPT and "Give an hour only when" in MEETING_SYSTEM_PROMPT
    assert "TODAY: Thursday 2026-10-15 (Europe/Madrid)" in _prompt(today=today_line("Europe/Madrid", late))
    assert "TODAY: " in _prompt()
