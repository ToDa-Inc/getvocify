"""The strategic card (pilot, LIVE_CARD_ENABLED): when it reads, what the code refuses, the one card on screen, and the
endpoint behind its flag. The model is replaced; what it would write is given per prompt."""

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
from app.services.copilot import events, live_brain, live_card
from app.services.copilot.live_models import CardReading

SNAPSHOT = {
    "version_id": "pv-1", "sales_motion_key": "discovery",
    "steps": [{"step_id": "reunion", "label": "Cerrar reunión", "criterion": "Acuerda día y hora.", "example": None}],
    "entries": [{"entry_id": "objection:price", "category": "price", "guidance": "Plan desde 49 € al mes por usuario; ofrecer 15 minutos."}],
    "qualification": [],
}
CTX = live_brain.BrainContext(snapshot=SNAPSHOT, knowledge={"value_short": "CRM por voz"}, product_context="Vocify", history=None,
                              today="TODAY: Monday 2026-10-26 (Europe/Madrid)", playbook_version_id="pv-1")


def turns(*items):
    """(who, text, start second)."""
    return [{"id": f"t{i}", "who": who, "text": text, "t": t} for i, (who, text, t) in enumerate(items)]


CALL = turns(
    ("you", "Hola Marta, soy Toni de Vocify, te llamo porque ayudamos a equipos comerciales con el CRM.", 0.0),
    ("them", "Ya, pero ahora mismo tenemos otras prioridades y además el precio nos preocupa bastante.", 6.0),
)


def reading(call=CALL, **kw):
    return CardReading(call_id="c1", sales_motion_key="discovery", turns=call, **kw)


def answer(line="Entiendo, ¿qué os preocupa más del precio: el coste por usuario o justificarlo ante dirección?", **kw):
    return {"what_is_happening": "Pone el precio como freno.", "understanding_confidence": "high", "their_latest": "precio",
            "last_move": "", "decision": "card", "line": line, "source": "context", "source_quote": "", **kw}


def fake_model(monkeypatch, reading_out, *, unsupported=False, closing=False, repeats=False, retry=None):
    calls = []

    async def ask(system, user, schema, *, max_tokens, temperature):
        calls.append(system)
        meta = {"model": "direct:test", "latency_ms": 10, "error": None}
        if system == live_card.SYSTEM:
            first = sum(c == live_card.SYSTEM for c in calls) == 1
            return (reading_out if first else retry), meta
        if system == live_card.FACT_SYSTEM:
            return {"unsupported": unsupported, "what": ""}, meta
        if system == live_card.CLOSING_SYSTEM:
            return {"closing": closing, "evidence": ""}, meta
        if system == live_card.REPEAT_SYSTEM:
            return {"repeats": repeats and sum(c == live_card.REPEAT_SYSTEM for c in calls) == 1, "same_as": "la anterior", "why": ""}, meta
        raise AssertionError("unknown prompt")

    monkeypatch.setattr(live_card, "ask", ask)
    return calls


def run(coro):
    return asyncio.run(coro)


# ---------- when it reads ----------


def test_the_end_of_their_intervention_is_read_and_a_question_or_objection_is_urgent():
    end = live_card.ends(CALL)
    assert live_card.due("turn_end", "none", CALL, end, end[-1], None) == "them_end"
    assert live_card.due("turn_end", "price", CALL, end, end[-1], None) == "them_urgent"
    # Nothing new of substance since the last reading: no second reading of the same words.
    assert live_card.due("turn_end", "none", CALL, end, end[-1], end[-1]) is None


def test_a_listening_sound_is_not_an_intervention():
    call = turns(("you", "Te cuento rápidamente cómo funciona la herramienta con vuestro equipo comercial.", 0.0), ("them", "Vale, sí.", 5.0))
    end = live_card.ends(call)
    assert live_card.due("turn_end", "none", call, end, end[-1], None) is None


def test_a_long_intervention_is_read_every_forty_seconds_and_a_long_rep_floor_once():
    long_them = turns(("you", "¿Cómo lo hacéis hoy?", 0.0),
                      ("them", " ".join(["el equipo registra las visitas en una hoja compartida y luego alguien lo pasa"] * 12), 2.0))
    end = live_card.ends(long_them)
    assert live_card.due("long_turn", None, long_them, end, 20.0, None) is None
    assert live_card.due("long_turn", None, long_them, end, end[-1], None) == "them_mid"
    rep = turns(("them", "Cuéntame qué hacéis exactamente.", 0.0),
                ("you", " ".join(["nosotros escuchamos la llamada y rellenamos el CRM con lo que se ha dicho"] * 12), 3.0))
    end = live_card.ends(rep)
    assert live_card.due("rep_turn", None, rep, end, end[-1], None) == "rep_long"
    assert live_card.due("rep_turn", None, rep, end, end[-1], end[-1]) is None


# ---------- what the code refuses ----------


def test_a_card_of_31_words_passes_and_one_over_35_is_refused():
    sources = live_card.sources_text(CTX, "discovery")
    ok = {"act": "move", "say": " ".join(["palabra"] * 31) + "?", "source": "context", "source_quote": ""}
    long = {"act": "move", "say": " ".join(["palabra"] * 36), "source": "context", "source_quote": ""}
    assert live_card.basic_checks(ok, CALL, [], sources) is None
    assert live_card.basic_checks(long, CALL, [], sources) == "too_long"


def test_the_same_text_as_a_card_shown_and_a_number_an_answer_invents_are_refused():
    sources = live_card.sources_text(CTX, "discovery")
    say = "Entiendo, ¿qué os preocupa más del precio: el coste por usuario o justificarlo?"
    shown = [{"id": "a", "say": say, "visible_t": 3.0, "open": True}]
    assert live_card.basic_checks({"act": "move", "say": say, "source": "context", "source_quote": ""}, CALL, shown, sources) == "same_text_as_shown"
    invented = {"act": "answer", "say": "El plan cuesta 29 € al mes por usuario.", "source": "objection:price", "source_quote": ""}
    approved = {"act": "answer", "say": "El plan cuesta 49 € al mes por usuario.", "source": "objection:price", "source_quote": ""}
    assert live_card.basic_checks(invented, CALL, [], sources) == "invented_number"
    assert live_card.basic_checks(approved, CALL, [], sources) is None


def test_the_sources_are_the_replays_and_the_calendar_names_the_days():
    sources = live_card.sources_text(CTX, "discovery")
    assert "USUAL GOAL FOR THIS TYPE OF CALL" in sources and "APPROVED ANSWERS" in sources and "STEPS (" in sources
    assert live_card.calendar(sources).startswith("CALENDAR: lunes 26 oct (hoy), martes 27 oct")


def test_the_companys_way_of_working_replaces_the_usual_goal_and_is_never_a_source():
    from dataclasses import replace

    conduct = {"goal": "", "also_good": "descalificar cuando no hay encaje", "stop_when": "un no claro",
               "criteria": ["No asumir dolor: si no reconoce la necesidad, no insistir en ella."]}
    sources = live_card.sources_text(replace(CTX, conduct=conduct), "discovery")
    assert "USUAL GOAL" not in sources
    assert "- Main goal: a meeting booked with the prospect" in sources  # none written: the usual one, as the company's
    assert "- Also good outcomes: descalificar cuando no hay encaje" in sources and "1. No asumir dolor" in sources
    assert sources.index("HOW THIS COMPANY CONDUCTS") < min(sources.index(h) for h in live_card.SOURCE_BLOCKS if h in sources)
    card = {"say": "No te voy a insistir: ¿te llamo si crecéis?", "source": "context", "source_quote": "No asumir dolor"}
    assert "No asumir dolor" not in live_card.authorized_text(sources, card)


# ---------- one card on screen ----------


def test_the_card_on_screen_holds_until_the_rep_could_use_it_or_closed_it():
    call = CALL
    floors = live_card.them_floors(call, live_card.ends(call))
    on = [{"id": "a", "say": "x", "visible_t": 9.0, "open": True}]
    assert not live_card.rep_could_use(on, call, floors, 12.0)
    assert live_card.rep_could_use([{**on[0], "open": False}], call, floors, 12.0)
    spoke = call + [{"id": "t9", "who": "you", "text": " ".join(["entiendo perfectamente lo que me comentas sobre el coste"] * 3), "t": 10.0}]
    assert live_card.rep_could_use(on, spoke, live_card.them_floors(spoke, live_card.ends(spoke)), 30.0)


def test_silence_when_the_reading_sees_nothing_to_add(monkeypatch):
    fake_model(monkeypatch, answer(decision="silence", line=""))
    result = run(live_card.read_card(reading(reason="turn_end"), CTX))
    assert result["event"] == "silence" and result["points"] == [] and result["moment"] == "them_end"


def test_a_card_is_a_point_and_the_card_still_open_fades(monkeypatch):
    fake_model(monkeypatch, answer())
    old = {"id": "card-old", "say": "¿Cómo gestionáis hoy el CRM?", "visible_t": 1.0, "open": True}
    # The rep spoke after the old card and they finished a new intervention: the screen is free.
    result = run(live_card.read_card(reading(reason="turn_end", cards=[old]), CTX))
    assert result["event"] == "shown"
    (card,) = result["points"]
    assert card["kind"] == "deepen" and card["answer"].startswith("Entiendo") and card["outcome"] == "open"
    assert card["turn_ids"] == ["t1"] and card["visible_t"] == result["read_t"] and card["title"].endswith("bastante.")
    assert result["closed"] == [{"id": "card-old", "outcome": "gone"}]


def test_a_card_before_they_have_spoken_still_has_words_on_its_first_line(monkeypatch):
    fake_model(monkeypatch, answer(line="¿Te pillo en buen momento para contarte en un minuto por qué te llamo?"))
    call = turns(("you", " ".join(["te llamo de Vocify porque trabajamos con equipos comerciales como el vuestro"] * 12), 0.0))
    (card,) = run(live_card.read_card(reading(call=call, reason="rep_turn"), CTX))["points"]
    assert card["title"] and card["turn_ids"] == ["t0"]


def test_the_card_appears_at_the_calls_clock_even_when_one_turn_kept_growing(monkeypatch):
    # Both voices on one side for minutes: one turn that started at 40 s. Its words say the call is at about 50 s; the
    # call's clock says 330 s. A card at "50 s" sorted above everything said since.
    fake_model(monkeypatch, answer())
    grown = turns(("you", "Hola, ¿qué tal?", 0.0),
                  ("them", " ".join(["nosotros priorizamos las cuentas grandes y el seguimiento lo lleva cada comercial"] * 3), 40.0))
    result = run(live_card.read_card(reading(call=grown, reason="turn_end", now_t=330.0), CTX))
    assert result["read_t"] == 330.0 and result["points"][0]["said_at"] == 330.0 and result["points"][0]["visible_t"] == 330.0
    # Without the clock, the turn's words decide, as before.
    assert run(live_card.read_card(reading(call=grown, reason="turn_end"), CTX))["read_t"] < 60


def test_an_approved_answer_is_a_respuesta_with_its_playbook_source(monkeypatch):
    fake_model(monkeypatch, answer(line="El plan es desde 49 € al mes por usuario; ¿lo vemos 15 minutos?", source="objection:price"))
    (card,) = run(live_card.read_card(reading(reason="turn_end", objection="price"), CTX))["points"]
    assert card["kind"] == "question" and card["tag_key"] == "objection:price" and card["source"]["id"] == "objection:price"


def test_a_repeat_gets_one_more_try_and_otherwise_silence(monkeypatch):
    calls = fake_model(monkeypatch, answer(), repeats=True, retry=answer(decision="silence", line=""))
    shown = [{"id": "a", "say": "¿Qué os frena hoy?", "visible_t": 1.0, "open": False}]
    result = run(live_card.read_card(reading(reason="turn_end", cards=shown), CTX))
    assert result["event"] == "drop:repeats→silence" and calls.count(live_card.SYSTEM) == 2


def test_an_unsupported_fact_or_a_closing_call_shows_nothing(monkeypatch):
    fake_model(monkeypatch, answer(), unsupported=True)
    assert run(live_card.read_card(reading(reason="turn_end"), CTX))["event"] == "drop:unsupported_fact"
    call = CALL + [{"id": "t5", "who": "them", "text": "Vale, gracias, hasta luego", "t": 12.0}]
    fake_model(monkeypatch, answer(), closing=True)
    assert run(live_card.read_card(reading(call=call, reason="turn_end"), CTX))["event"] in ("drop:call_closing", "drop:after_goodbye")


def test_a_new_card_waits_while_the_rep_has_not_had_the_chance_to_use_the_one_on_screen(monkeypatch):
    fake_model(monkeypatch, answer())
    end = live_card.ends(CALL)
    on = [{"id": "a", "say": "¿Qué prioridades tenéis ahora?", "visible_t": round(end[-1], 1), "open": True}]
    result = run(live_card.read_card(reading(reason="turn_end", cards=on), CTX))
    assert result["event"] == "drop:rep_has_last_card" and result["points"] == []


# ---------- the endpoint ----------


class FakeTable:
    def __init__(self, db):
        self.db = db

    def insert(self, row):
        self.row = row
        return self

    def execute(self):
        if getattr(self, "row", None) is not None:
            self.db.inserted.append(self.row)
            self.row = None
        return self

    def __getattr__(self, _name):
        return lambda *_a, **_k: self


class FakeDb:
    def __init__(self):
        self.inserted = []

    def table(self, name):
        return FakeTable(self)


def client_for(db, monkeypatch, card=True):
    monkeypatch.setattr(copilot_api, "is_enabled", lambda _db, _company, flag: flag == "LIVE_BRAIN_ENABLED" or (card and flag == "LIVE_CARD_ENABLED"))

    async def fake_context(_db, _membership, _body):
        return CTX

    monkeypatch.setattr(copilot_api, "_brain_context", fake_context)
    monkeypatch.setattr(events, "_brain_paused_until", 0.0)
    app = FastAPI()
    app.include_router(copilot_api.router)
    app.dependency_overrides[get_supabase] = lambda: db
    app.dependency_overrides[get_user_id] = lambda: "user-1"
    app.dependency_overrides[get_membership] = lambda: Membership(id="m-1", company_id="co-1", user_id="user-1", role="member", status="active")
    return TestClient(app)


BODY = {"call_id": "draft-1", "sales_motion_key": "discovery", "call_mode": "meeting", "turns": CALL, "state_version": 3,
        "reason": "turn_end", "objection": "none", "cards": []}


def test_the_card_is_off_unless_the_company_has_its_flag(monkeypatch):
    response = client_for(FakeDb(), monkeypatch, card=False).post("/api/v1/copilot/live/card", json=BODY)
    assert response.status_code == 403 and response.json()["detail"] == "live_card_disabled"


def test_a_card_reading_answers_and_is_logged_as_a_points_reading_of_the_card_producer(monkeypatch):
    fake_model(monkeypatch, answer())
    db = FakeDb()
    response = client_for(db, monkeypatch).post("/api/v1/copilot/live/card", json=BODY)
    body = response.json()
    assert response.status_code == 200 and body["event"] == "shown" and body["state_version"] == 3 and "trace" not in body
    (row,) = db.inserted
    assert row["kind"] == "points" and row["capture_id"] == "draft-1" and row["prompt_version"] == live_card.PROMPT_VERSION
    assert row["detail"]["producer"] == "card" and row["detail"]["event"] == "shown" and row["detail"]["say"].startswith("Entiendo")


def test_a_checkpoint_that_is_not_a_moment_costs_nothing_and_is_not_logged(monkeypatch):
    calls = fake_model(monkeypatch, answer())
    db = FakeDb()
    response = client_for(db, monkeypatch).post("/api/v1/copilot/live/card", json={**BODY, "reason": "rep_turn"})
    assert response.json()["event"] == "skipped:not_a_moment" and calls == [] and db.inserted == []


def test_responder_reads_at_once_tells_the_reading_it_was_asked_and_takes_the_screen(monkeypatch):
    seen = []

    async def ask(system, user, schema, *, max_tokens, temperature):
        seen.append(user)
        meta = {"model": "direct:test", "latency_ms": 10, "error": None}
        if system == live_card.SYSTEM:
            return answer(line="¿Qué pasa hoy cuando uno de los dos no está y un cliente pregunta por su cuenta?"), meta
        if system == live_card.FACT_SYSTEM:
            return {"unsupported": False, "what": ""}, meta
        if system == live_card.CLOSING_SYSTEM:
            return {"closing": False, "evidence": ""}, meta
        return {"repeats": False, "same_as": "", "why": ""}, meta

    monkeypatch.setattr(live_card, "ask", ask)
    end = live_card.ends(CALL)
    on = [{"id": "a", "say": "¿Qué prioridades tenéis ahora?", "visible_t": round(end[-1], 1), "open": True}]
    result = run(live_card.read_card(reading(reason="responder", cards=on), CTX))
    assert result["moment"] == "asked" and result["event"] == "shown"
    assert result["closed"] == [{"id": "a", "outcome": "gone"}], "asked for, it replaces the card the rep has not used yet"
    assert "THE REP ASKED YOU NOW" in seen[0]
    # An automatic reading at the same moment waits for the rep to use the card on screen, and is not told it was asked.
    seen.clear()
    assert run(live_card.read_card(reading(reason="turn_end", cards=on), CTX))["event"] == "drop:rep_has_last_card"
    assert "THE REP ASKED YOU NOW" not in seen[0]


def test_asked_a_card_with_an_unsupported_claim_gets_one_more_try_but_an_automatic_one_does_not(monkeypatch):
    lines = iter([answer(line="¿Te enseño cómo quedaría en vuestro CRM?"), answer(line="¿Qué pasa hoy cuando uno de los dos no está?")])
    facts = iter([True, False])
    seen = []

    async def ask(system, user, schema, *, max_tokens, temperature):
        meta = {"model": "direct:test", "latency_ms": 10, "error": None}
        if system == live_card.SYSTEM:
            seen.append(user)
            return next(lines), meta
        if system == live_card.FACT_SYSTEM:
            return {"unsupported": next(facts), "what": "shows the CRM filled"}, meta
        if system == live_card.CLOSING_SYSTEM:
            return {"closing": False, "evidence": ""}, meta
        return {"repeats": False, "same_as": "", "why": ""}, meta

    monkeypatch.setattr(live_card, "ask", ask)
    result = run(live_card.read_card(reading(reason="responder"), CTX))
    assert result["event"] == "shown" and result["points"][0]["answer"].startswith("¿Qué pasa hoy")
    assert "STATES WHAT NO SOURCE SAYS (shows the CRM filled)" in seen[1]
    fake_model(monkeypatch, answer(), unsupported=True)
    assert run(live_card.read_card(reading(reason="turn_end"), CTX))["event"] == "drop:unsupported_fact"


def test_asked_again_the_same_words_are_another_try_not_nothing(monkeypatch):
    shown_say = "Vale, cada uno en su cabeza. ¿Y cuánto tarda un comercial nuevo en vender solo con ese sistema?"
    lines = iter([answer(line="Vale, cada uno en su cabeza. ¿Y cuánto tarda un comercial nuevo en vender solo así?"),
                  answer(line="¿Quién decide si probáis algo así, tú o alguien más?")])
    seen = []

    async def ask(system, user, schema, *, max_tokens, temperature):
        meta = {"model": "direct:test", "latency_ms": 10, "error": None}
        if system == live_card.SYSTEM:
            seen.append(user)
            return next(lines), meta
        if system == live_card.FACT_SYSTEM:
            return {"unsupported": False, "what": ""}, meta
        if system == live_card.CLOSING_SYSTEM:
            return {"closing": False, "evidence": ""}, meta
        return {"repeats": False, "same_as": "", "why": ""}, meta

    monkeypatch.setattr(live_card, "ask", ask)
    on = [{"id": "a", "say": shown_say, "visible_t": 5.0, "open": True}]
    result = run(live_card.read_card(reading(reason="responder", cards=on), CTX))
    assert result["event"] == "shown" and result["points"][0]["answer"].startswith("¿Quién decide")
    assert f"REPEATS «{shown_say}»" in seen[1]

