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
    return {"their_latest": "Pone el precio como freno.", "understanding_confidence": "high", "action": "deepen",
            "card_on_screen": "no_card", "because": "el precio nos preocupa bastante", "decision": "card", "line": line,
            "source": "context", "source_quote": "", **kw}


def fake_model(monkeypatch, reading_out, *, unsupported=False, closing=False, repeats=False, retry=None):
    calls = []

    async def ask(system, user, schema, *, max_tokens, temperature, hedge_s=None):
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


def test_a_question_of_theirs_is_urgent_even_when_the_turn_check_saw_nothing():
    # «Ya, pero es que eso es caro, ¿no?»: the turn check said "none" in 2 of 3 tries (synthetic Movertis call, 2026-11-09).
    call = CALL[:1] + [{"id": "t1", "who": "them", "text": "Ya, pero es que eso es caro, ¿no? Con veinte furgonetas no sé si me sale a cuenta.", "t": 6.0}]
    end = live_card.ends(call)
    assert live_card.due("turn_end", "none", call, end, end[-1], None) == "them_urgent"


def test_a_short_question_is_read_and_a_bare_tag_question_is_not():
    # «¿Y exactamente qué es lo que hacéis?» was asked three times on a real call (2026-11-11): once it reached the brain
    # it was not read, for having three words of substance where four are asked of any turn.
    def moment(text, objection="none"):
        call = CALL[:1] + [{"id": "t1", "who": "them", "text": text, "t": 6.0}]
        end = live_card.ends(call)
        return live_card.due("turn_end", objection, call, end, end[-1], None)

    assert moment("¿Y exactamente qué es lo que hacéis?") == "them_urgent"
    assert moment("¿Y qué precio tiene?", "question") == "them_urgent"
    # Nothing to answer: a tag question, or a few words nobody flagged.
    assert moment("¿Vale?") is None and moment("¿Sabes?") is None
    assert moment("Es muy caro.") is None


def test_the_reading_is_told_the_objection_they_raised_and_its_approved_answer(monkeypatch):
    snapshot = {**SNAPSHOT, "entries": SNAPSHOT["entries"] + [
        {"entry_id": "objection:custom:es_caro", "label": "Es caro", "guidance": "¿Respecto a qué te parece caro?"}]}
    note = live_card.spotted("objection:custom:es_caro", snapshot)
    assert "THEY JUST RAISED: «Es caro»" in note and "¿Respecto a qué te parece caro?" in note and "never instead of it" in note
    assert "Plan desde 49 €" in live_card.spotted("price", snapshot)
    assert live_card.spotted("none", snapshot) == "" and live_card.spotted(None, snapshot) == ""
    assert live_card.spotted("trust", snapshot) == "\n\nTHEY JUST RAISED: an objection (trust). Answer it before anything else."
    seen = []

    async def ask(system, user, schema, *, max_tokens, temperature, hedge_s=None):
        meta = {"model": "direct:test", "latency_ms": 10, "error": None}
        if system == live_card.SYSTEM:
            seen.append(user)
            return answer(), meta
        if system == live_card.FACT_SYSTEM:
            return {"unsupported": False, "what": ""}, meta
        if system == live_card.CLOSING_SYSTEM:
            return {"closing": False, "evidence": ""}, meta
        return {"repeats": False, "same_as": "", "why": ""}, meta

    monkeypatch.setattr(live_card, "ask", ask)
    run(live_card.read_card(reading(reason="turn_end", objection="price"), CTX))
    assert "THEY JUST RAISED" in seen[0] and "Plan desde 49 €" in seen[0]


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


def test_a_card_never_pairs_a_weekday_with_another_days_date_nor_invents_an_hour():
    # Cards a reading wrote on synthetic Movertis calls (2026-11-09: Monday 9; Thursday 12, Tuesday 10).
    sources = "TODAY: Monday 2026-11-09 (Europe/Madrid)"
    fix = live_card.fixed_days
    assert fix("Perfecto, lo dejamos para después del puente; ¿te parece el martes 12 a las 10:00?", sources, "") == (
        "Perfecto, lo dejamos para después del puente; ¿te parece el martes?"
    )
    assert fix("Con esto que me cuentas, ¿te encaja una reunión de 20 minutos el jueves 12 a las 10?", sources, "") == (
        "Con esto que me cuentas, ¿te encaja una reunión de 20 minutos el jueves 12?"
    )
    # An hour said in the call stays; minutes are not a date.
    said = "¿Te viene mejor el jueves a las 10 o el viernes a las 12?"
    assert fix("Entonces el jueves 12 a las 10, ¿te lo confirmo?", sources, said) == "Entonces el jueves 12 a las 10, ¿te lo confirmo?"
    assert fix("¿Lo vemos el martes 10 en 20 minutos?", sources, "") == "¿Lo vemos el martes 10 en 20 minutos?"
    # An hour in words or with «horas» goes whole (a reading wrote «el miércoles a las 10 horas»; another «a las diez»).
    assert fix("¿Te llamo el miércoles a las 10 horas y lo comentamos?", sources, "") == "¿Te llamo el miércoles y lo comentamos?"
    assert fix("¿Fijamos el jueves a las diez y lo vemos juntos?", sources, "") == "¿Fijamos el jueves y lo vemos juntos?"
    assert fix("¿Fijamos el jueves a las diez y media?", sources, "") == "¿Fijamos el jueves?"
    assert fix("Llámale a partir de las diez, ¿te va el jueves a las diez?", sources, "a partir de las diez") == (
        "Llámale a partir de las diez, ¿te va el jueves a las diez?")
    # Any number said in the call is not an hour said: the rep's opening had «a diez minutos o a 300 kilómetros».
    assert fix("¿te llamo el miércoles a las 10 y lo vemos en 20 minutos?", sources,
               "¿cómo sabes si está a diez minutos o a 300 kilómetros?") == "¿te llamo el miércoles y lo vemos en 20 minutos?"
    # A date with its month it cannot vouch for keeps the month, not a weekday that would read as next week.
    assert fix("Perfecto, te lo mando. ¿Te llamo el martes 12 de enero para retomarlo?", sources, "") == (
        "Perfecto, te lo mando. ¿Te llamo en enero para retomarlo?")
    assert fix("¿Te va bien el jueves 12 de noviembre?", sources, "") == "¿Te va bien el jueves 12 de noviembre?"
    # A date past the calendar cannot be checked: the weekday alone.
    assert fix("Te llamo en junio; ¿te parece el martes 2?", sources, "") == "Te llamo en junio; ¿te parece el martes?"


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
    # The rep spoke after the old card and they finished a new intervention, a minute later: the screen is free.
    result = run(live_card.read_card(reading(reason="turn_end", cards=[old], now_t=60.0), CTX))
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
    fake_model(monkeypatch, answer(because="priorizamos las cuentas grandes"))
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
    result = run(live_card.read_card(reading(reason="turn_end", cards=shown, now_t=60.0), CTX))
    assert result["event"] == "drop:repeats→silence" and calls.count(live_card.SYSTEM) == 2


def test_the_reading_writes_their_latest_words_then_the_move_then_the_card():
    # What it weighs (what is happening, hypotheses, the unknown, the situation) is not written: the card came at 1.3 s
    # with those fields and at 0.8 s without, deciding the same. The card is never written before the move.
    fields = live_card.SCHEMA["required"]
    assert fields == list(live_card.SCHEMA["properties"]) == [
        "their_latest", "understanding_confidence", "action", "card_on_screen", "because", "decision", "line", "source", "source_quote"]
    for gone in ('"what_is_happening"', '"observed"', '"hypotheses"', '"unknown"', '"situation"', '"last_move"'):
        assert gone not in live_card.SYSTEM
    assert "you do not write them" in live_card.SYSTEM and "company's SITUATIONS" in live_card.SYSTEM


def test_a_card_that_names_a_day_nobody_said_gets_one_more_try(monkeypatch):
    # «¿Jueves o viernes te viene mejor?» after «podríamos verlo» (replay of a real call, 2026-11-11): the day is the rep's.
    assert live_card.proposed_day("Pues te lo enseño en 15 minutos. ¿Jueves o viernes te viene mejor?", "Podríamos verlo.")
    assert not live_card.proposed_day("Entonces el jueves te llamo, ¿te mando la invitación?", "Llámame el Jueves mejor.")
    assert not live_card.proposed_day("¿Qué día te viene bien para verlo 15 minutos?", "Podríamos verlo.")
    proposes = answer(line="Pues te lo enseño en 15 minutos con tus comerciales. ¿Jueves o viernes te viene mejor?")
    calls = fake_model(monkeypatch, proposes, retry=answer(line="Pues te lo enseño en 15 minutos con tus comerciales. ¿Qué día te viene bien?"))
    result = run(live_card.read_card(reading(reason="turn_end"), CTX))
    assert result["event"] == "shown" and calls.count(live_card.SYSTEM) == 2
    assert result["points"][0]["answer"].endswith("¿Qué día te viene bien?")
    # Still a day on the second try: nothing is shown.
    fake_model(monkeypatch, proposes, retry=proposes)
    assert run(live_card.read_card(reading(reason="turn_end"), CTX))["event"] == "drop:proposes_day"
    # A day they said themselves stays.
    call = CALL + turns(("them", "Si acaso llámame el jueves y lo miramos con calma.", 14.0))
    call[-1]["id"] = "t9"
    calls = fake_model(monkeypatch, answer(line="Perfecto, te llamo el jueves y lo miramos con calma.", because="llámame el jueves y lo miramos"))
    assert run(live_card.read_card(reading(call=call, reason="turn_end"), CTX))["event"] == "shown" and calls.count(live_card.SYSTEM) == 1


def test_an_unsupported_fact_or_a_closing_call_shows_nothing(monkeypatch):
    fake_model(monkeypatch, answer(), unsupported=True)
    assert run(live_card.read_card(reading(reason="turn_end"), CTX))["event"] == "drop:unsupported_fact"
    call = CALL + [{"id": "t5", "who": "them", "text": "Vale, gracias, hasta luego", "t": 12.0}]
    fake_model(monkeypatch, answer(), closing=True)
    assert run(live_card.read_card(reading(call=call, reason="turn_end"), CTX))["event"] in ("drop:call_closing", "drop:after_goodbye")


def test_the_card_the_rep_has_not_used_yet_stays_changes_or_goes_as_the_reading_says(monkeypatch):
    # They keep talking: a card shown during their intervention is one the rep has not had the chance to use.
    long = turns(("you", CALL[0]["text"], 0.0),
                 ("them", " ".join(["ahora mismo tenemos otras prioridades y el precio nos preocupa bastante"] * 8), 6.0))
    end = live_card.ends(long)

    def on(age):
        return [{"id": "a", "say": "¿Qué prioridades tenéis ahora?", "visible_t": round(end[-1] - age, 1), "open": True}]

    def reading_with(cards):
        return reading(call=long, reason="turn_end", cards=cards)

    # Shown while they were still talking: the rep has not had the chance to use it.
    fake_model(monkeypatch, answer(card_on_screen="keep", decision="silence", line=""))
    result = run(live_card.read_card(reading_with(on(22)), CTX))
    assert result["event"] == "keep" and result["points"] == [] and result["closed"] == []
    # A better move replaces it, once it could be read.
    fake_model(monkeypatch, answer(card_on_screen="replace"))
    result = run(live_card.read_card(reading_with(on(22)), CTX))
    assert result["event"] == "replace" and result["points"] and result["closed"] == [{"id": "a", "outcome": "gone"}]
    assert result["trace"]["replaces"] == "a"
    fake_model(monkeypatch, answer(card_on_screen="replace"))
    result = run(live_card.read_card(reading_with(on(1)), CTX))
    assert result["event"] == "drop:card_on_screen_too_new" and result["points"] == []
    # Made wrong by what they said: off at once. Only no longer the best: not before it could be read.
    fake_model(monkeypatch, answer(card_on_screen="invalid", decision="silence", line=""))
    result = run(live_card.read_card(reading_with(on(1)), CTX))
    assert result["event"] == "invalid" and result["closed"] == [{"id": "a", "outcome": "gone"}]
    fake_model(monkeypatch, answer(card_on_screen="withdraw", decision="silence", line=""))
    result = run(live_card.read_card(reading_with(on(1)), CTX))
    assert result["event"] == "keep:card_on_screen_too_new" and result["closed"] == []


def test_a_new_card_waits_its_turn_unless_they_asked_or_objected(monkeypatch):
    calls = fake_model(monkeypatch, answer())
    end = live_card.ends(CALL)
    used = [{"id": "a", "say": "¿Qué prioridades tenéis ahora?", "visible_t": round(end[-1] - 10, 1), "open": False}]
    # A card of the reading's own initiative (a deeper question) waits: the reading is asked, its card is not shown.
    result = run(live_card.read_card(reading(reason="turn_end", objection="none", cards=used), CTX))
    assert result["event"] == "drop:too_soon_after_last_card" and result["points"] == [] and calls.count(live_card.SYSTEM) == 1
    # An objection the turn check saw is not kept waiting.
    fake_model(monkeypatch, answer())
    result = run(live_card.read_card(reading(reason="turn_end", objection="price", cards=used), CTX))
    assert result["moment"] == "them_urgent" and result["event"] == "shown"
    # Nor is a card that answers what they raised when the turn check saw nothing («ya trabajamos con Granola»: its card
    # came 27 s late on a real call, 2026-11-11). The reading says so itself: its move is "answer" or "clarify".
    for move in ("answer", "clarify"):
        fake_model(monkeypatch, answer(action=move))
        result = run(live_card.read_card(reading(reason="turn_end", objection="none", cards=used), CTX))
        assert result["moment"] == "them_end" and result["event"] == "shown"


def test_a_note_about_what_to_do_is_not_a_card():
    assert not live_card.says_as_is("Con su sistema ya cubierto en el después, explorar qué pasa cuando la duda surge en directo.")
    assert not live_card.says_as_is("Cambiar de la comparación funcional a la cobertura real: ¿qué pasa en las otras?")
    assert live_card.says_as_is("Vale, ¿y qué os aporta Gemini en el día a día?")
    assert live_card.says_as_is("Entiendo, te pregunto por el seguimiento: ¿quién lo lleva?")


def test_a_card_rests_on_their_own_words(monkeypatch):
    fake_model(monkeypatch, answer(because="nos falla el seguimiento de cada reunión"))
    result = run(live_card.read_card(reading(reason="turn_end"), CTX))
    assert result["event"] == "drop:no_reason_in_their_words" and result["points"] == []


def test_the_prompts_hold_the_hierarchy_the_situations_and_the_proposal_rule():
    assert "When they disagree, the higher level wins" in live_card.SYSTEM
    # The situation is weighed, no longer written: its rule stays word for word.
    assert "which of the company's SITUATIONS fits this moment" in live_card.SYSTEM
    assert "your action does what it says to do and nothing it says not to do" in " ".join(live_card.SYSTEM.split())
    assert "asks again what they already answered" in live_card.FACT_SYSTEM and "General knowledge" in live_card.FACT_SYSTEM
    # What they say about the seller's product is not a source for it: «Exacto: Fireflies captura…» confirmed their guess
    # (real meeting, 2026-11-11); the check let it pass in 1 of 3 runs before this line, in 0 of 3 with it.
    assert "is not a source" in live_card.FACT_SYSTEM and "supports nothing about the product" in live_card.FACT_SYSTEM
    sources = live_card.sources_text(CTX, "discovery")
    assert "APPROVED ANSWERS (" in sources and "(Level 4: ways to answer." in sources


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

    async def ask(system, user, schema, *, max_tokens, temperature, hedge_s=None):
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
    # An automatic reading at the same moment does not change a card the rep could not read yet, and is not told it was asked.
    seen.clear()
    assert run(live_card.read_card(reading(reason="turn_end", cards=on), CTX))["event"] == "drop:card_on_screen_too_new"
    assert "THE REP ASKED YOU NOW" not in seen[0]


def test_asked_a_card_with_an_unsupported_claim_gets_one_more_try_but_an_automatic_one_does_not(monkeypatch):
    lines = iter([answer(line="¿Te enseño cómo quedaría en vuestro CRM?"), answer(line="¿Qué pasa hoy cuando uno de los dos no está?")])
    facts = iter([True, False])
    seen = []

    async def ask(system, user, schema, *, max_tokens, temperature, hedge_s=None):
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


def test_an_automatic_answer_no_source_supports_is_dropped_not_rewritten(monkeypatch):
    # It used to be rewritten as «Eso te lo confirmo con el equipo técnico…»: our sentence, not the company's, and a second
    # reading. On Movertis calls (2026-11-12) those cards were filler, often to no question at all.
    seen = []

    async def ask(system, user, schema, *, max_tokens, temperature, hedge_s=None):
        meta = {"model": "direct:test", "latency_ms": 10, "error": None}
        if system == live_card.SYSTEM:
            seen.append(user)
            return answer(line="La instalación no os obliga a parar furgonetas, se hace en un rato.", action="answer"), meta
        if system == live_card.FACT_SYSTEM:
            return {"unsupported": True, "what": ""}, meta
        if system == live_card.CLOSING_SYSTEM:
            return {"closing": False, "evidence": ""}, meta
        return {"repeats": False, "same_as": "", "why": ""}, meta

    monkeypatch.setattr(live_card, "ask", ask)
    result = run(live_card.read_card(reading(reason="turn_end"), CTX))
    assert result["event"] == "drop:unsupported_fact" and result["points"] == [] and len(seen) == 1


def test_asked_again_the_same_words_are_another_try_not_nothing(monkeypatch):
    shown_say = "Vale, cada uno en su cabeza. ¿Y cuánto tarda un comercial nuevo en vender solo con ese sistema?"
    lines = iter([answer(line="Vale, cada uno en su cabeza. ¿Y cuánto tarda un comercial nuevo en vender solo así?"),
                  answer(line="¿Quién decide si probáis algo así, tú o alguien más?")])
    seen = []

    async def ask(system, user, schema, *, max_tokens, temperature, hedge_s=None):
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



def test_the_cards_reach_the_playbooks_improvement_step():
    # Since the card became everyone's brain (2026-11-09) the improvement step got nothing: it reads these rows.
    from types import SimpleNamespace as T
    turns = [T(id="t0", who="you", text="¿Os encaja?"), T(id="t1", who="them", text="Ya, pero es que eso es caro, ¿no?")]
    answered = {"moment": "them_urgent", "points": [{
        "id": "card-1", "kind": "question", "turn_ids": ["t1"], "answer": "¿Respecto a qué te parece caro?",
        "source": {"id": "objection:custom:es_caro", "label": "Playbook · Es caro"},
    }]}
    common = dict(user_id="u", company_id="co", call_mode="softphone", sales_motion_key="frio", call_id="c1", turns=turns)
    (row,) = events.strategic_card_rows(**common, objection="objection:custom:es_caro", result=answered)
    assert row["is_objection"] and row["kind"] == "points" and row["latest_turn"] == "Ya, pero es que eso es caro, ¿no?"
    assert row["entry_id"] == row["source_id"] == "objection:custom:es_caro" and row["objection_type"] == "custom"
    assert row["say_this"] == "¿Respecto a qué te parece caro?" and row["detail"]["card"] == "shown"
    # Flagged and nothing shown: a missed objection, what the gaps count.
    (missed,) = events.strategic_card_rows(**common, objection="price", result={"moment": "them_urgent", "points": []})
    assert missed["detail"]["card"] == "missed" and missed["objection_type"] == "price" and missed["say_this"] is None
    # A question built only on the conversation, at a turn nobody flagged: not something to answer, not logged.
    deepen = {"moment": "them_end", "points": [{"id": "card-2", "kind": "deepen", "turn_ids": ["t1"], "answer": "¿Qué os falta?", "source": None}]}
    assert events.strategic_card_rows(**common, objection="none", result=deepen) == []


def test_a_response_replaces_a_card_the_rep_has_not_used_but_never_one_just_shown(monkeypatch):
    # They keep talking: the card shown during their intervention is one the rep has not had the chance to use.
    long = turns(("you", CALL[0]["text"], 0.0),
                 ("them", " ".join(["ahora mismo tenemos otras prioridades y el precio nos preocupa bastante"] * 8), 6.0))
    end = live_card.ends(long)

    def event(age, objection="none", on_screen_responds=False, **reading_out):
        on = [{"id": "a", "say": "¿Qué prioridades tenéis ahora?", "visible_t": round(end[-1] - age, 1), "open": True,
               "responds": on_screen_responds}]
        fake_model(monkeypatch, answer(**{"card_on_screen": "replace", **reading_out}))
        return run(live_card.read_card(reading(call=long, reason="turn_end", objection=objection, cards=on), CTX))

    # The reading's own initiative: the card on screen is not changed before it could be read (20 s).
    assert event(10)["event"] == "drop:card_on_screen_too_new"
    # A response to what they raised takes the screen: flagged by the turn check, or said by the reading's own move
    # («¿cuántos sois en la empresa?» got nothing behind a card 10 s old, real call, 2026-11-11).
    assert event(10, objection="price")["event"] == "replace"
    assert event(10, action="answer")["event"] == "replace" and event(10, action="clarify")["event"] == "replace"
    # Over a card of the reading's own initiative, at once: a deeper question appeared 0.6 s before «me parece bastante
    # caro» was read, and the price went unanswered behind it (replay of a real call, 2026-11-11).
    assert event(1, objection="price")["event"] == "replace" and event(1, action="answer")["event"] == "replace"
    # Over a card that was itself a response, not before it could be read: one card changed three times in 6 s while the
    # same objection was still being said.
    assert event(3, objection="price", on_screen_responds=True)["event"] == "drop:card_on_screen_too_new"
    assert event(3, action="answer", on_screen_responds=True)["event"] == "drop:card_on_screen_too_new"
    assert event(10, action="answer", on_screen_responds=True)["event"] == "replace"
    # The same card reworded waits like any other.
    assert event(10, action="answer", card_on_screen="update")["event"] == "drop:card_on_screen_too_new"
    # A «¿no?» closing their sentence is a question to the code, not a response: a deeper question replaced an answer 1.3 s
    # after it appeared (real meeting, 2026-11-11). The reading's own move decides.
    tagged = turns(("you", CALL[0]["text"], 0.0),
                   ("them", " ".join(["nos cuesta que lo lleven a cabo en la mayoría de las ocasiones"] * 8) + ", ¿no?", 6.0))
    ends_tagged = live_card.ends(tagged)

    def tag_event(age, **reading_out):
        on = [{"id": "a", "say": "¿Qué prioridades tenéis ahora?", "visible_t": round(ends_tagged[-1] - age, 1), "open": True, "responds": True}]
        fake_model(monkeypatch, answer(**{"card_on_screen": "replace", "because": "nos cuesta que lo lleven a cabo", **reading_out}))
        return run(live_card.read_card(reading(call=tagged, reason="turn_end", objection="none", cards=on), CTX))

    result = tag_event(10, action="deepen")
    assert result["moment"] == "them_urgent" and result["event"] == "drop:card_on_screen_too_new"
    assert tag_event(10, action="answer")["event"] == "replace"
    # The log says how old the card on screen was, its kind, and whether the client says the kind at all.
    assert result["trace"]["on_screen"] == {"age_s": 10.0, "responds": True, "client_says_kind": True}
    # The card says which kind it is, for the next reading: a response, or the reading's own initiative.
    assert event(10, action="answer")["points"][0]["responds"] is True
    fake_model(monkeypatch, answer())
    assert run(live_card.read_card(reading(reason="turn_end"), CTX))["points"][0]["responds"] is False


def test_a_card_appears_when_its_reading_ends_not_when_it_was_asked_for(monkeypatch):
    # A reading of 4.1 s made its card look 4.1 s older than it was to the next reading (real meeting, 2026-11-11).
    fake_model(monkeypatch, answer())
    clock = iter([100.0])
    monkeypatch.setattr(live_card.time, "perf_counter", lambda: next(clock, 104.1))
    result = run(live_card.read_card(reading(reason="turn_end", now_t=60.0), CTX))
    point = result["points"][0]
    assert result["event"] == "shown" and point["said_at"] == 60.0 and point["visible_t"] == 64.1


def test_the_checks_are_asked_again_sooner_than_the_reading(monkeypatch):
    waits = {}

    async def ask(system, user, schema, *, max_tokens, temperature, hedge_s=live_card.HEDGE_S):
        waits[system] = hedge_s
        meta = {"model": "direct:test", "latency_ms": 10, "error": None}
        if system == live_card.SYSTEM:
            return answer(), meta
        if system == live_card.FACT_SYSTEM:
            return {"unsupported": False, "what": ""}, meta
        if system == live_card.CLOSING_SYSTEM:
            return {"closing": False, "evidence": ""}, meta
        return {"repeats": False, "same_as": "", "why": ""}, meta

    monkeypatch.setattr(live_card, "ask", ask)
    assert run(live_card.read_card(reading(reason="turn_end"), CTX))["event"] == "shown"
    assert waits[live_card.SYSTEM] == live_card.HEDGE_S
    assert waits[live_card.FACT_SYSTEM] == waits[live_card.CLOSING_SYSTEM] == live_card.CHECK_HEDGE_S
    assert live_card.CHECK_HEDGE_S == 1.0 < live_card.HEDGE_S == 1.5


def test_putting_the_call_off_is_not_the_call_closing():
    assert "llámame la semana que viene" in live_card.CLOSING_SYSTEM and "only once a goodbye" in live_card.CLOSING_SYSTEM


def _providers(monkeypatch, answers):
    """`answers`: per request, in the order they are sent, (delay in s, content or an exception)."""
    sent = []

    async def post(client, url, headers, payload):
        i = len(sent)
        sent.append("openrouter" if url == live_card.OPENROUTER_URL else "direct")
        delay, out = answers[i]
        await asyncio.sleep(delay)
        if isinstance(out, Exception):
            raise out
        return out

    monkeypatch.setattr(live_card, "_post", post)
    monkeypatch.setattr(live_card, "live_direct", lambda: ("https://together.test", "key", "x"))
    monkeypatch.setattr(live_card.settings, "OPENROUTER_API_KEY", "or-key", raising=False)
    return sent


def test_a_slow_reading_is_asked_of_together_again_and_the_first_answer_wins(monkeypatch):
    sent = _providers(monkeypatch, [(0.5, '{"n": 1}'), (0.05, '{"n": 2}')])
    out, meta = run(live_card.ask("s", "u", {}, max_tokens=10, temperature=0, hedge_s=0.1))
    assert out == {"n": 2} and sent == ["direct", "direct"] and meta["model"].startswith("direct:")


def test_a_reading_in_time_is_asked_once(monkeypatch):
    sent = _providers(monkeypatch, [(0.01, '{"n": 1}')])
    out, _ = run(live_card.ask("s", "u", {}, max_tokens=10, temperature=0, hedge_s=0.1))
    assert out == {"n": 1} and sent == ["direct"]


def test_openrouter_only_when_both_requests_to_together_fail(monkeypatch):
    sent = _providers(monkeypatch, [(0.01, RuntimeError("HTTP 503")), (0.01, RuntimeError("HTTP 503")), (0.01, '{"n": 3}')])
    out, meta = run(live_card.ask("s", "u", {}, max_tokens=10, temperature=0, hedge_s=0.1))
    assert out == {"n": 3} and sent == ["direct", "direct", "openrouter"] and meta["model"].startswith("openrouter:")


def test_two_slow_requests_to_together_do_not_bring_in_openrouter(monkeypatch):
    sent = _providers(monkeypatch, [(0.4, '{"n": 1}'), (0.4, '{"n": 2}')])
    out, _ = run(live_card.ask("s", "u", {}, max_tokens=10, temperature=0, hedge_s=0.1))
    assert out == {"n": 1} and sent == ["direct", "direct"]
