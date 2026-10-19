"""The live call assistant's producers (spec 2026-10-16): what the model writes passes through the checks in code, and the
endpoints are behind the per-company flag."""

import json
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")

import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import copilot as copilot_api
from app.deps import get_membership, get_supabase, get_user_id
from app.services.company import Membership
from app.services.copilot import events, live_brain, live_points, live_progress
from app.services.copilot.live_models import LiveReading

EXAMPLE = json.loads((Path(__file__).parents[3] / "shared/live-call/example.json").read_text(encoding="utf-8"))

SNAPSHOT = {
    "version_id": "pv-1", "sales_motion_key": "discovery",
    "steps": [
        {"step_id": "apertura", "label": "Apertura", "criterion": "Se presenta y da el marco.", "example": "Hola, soy Toni, será breve."},
        {"step_id": "problema", "label": "Plantear el problema", "criterion": "Expone el problema como común.", "example": "Los equipos de campo dejan el CRM para luego."},
        {"step_id": "treinta", "label": "Explicar en 30 segundos", "criterion": "Explica el producto en menos de 30 segundos.", "example": None},
    ],
    "entries": [
        {"entry_id": "objection:status_quo", "category": "status_quo", "guidance": "No discutir; repreguntar con algo medible."},
        {"entry_id": "objection:custom:email", "category": "other", "label": "Mándame un email", "trigger": "mándame un email", "guidance": "Ofrecer 15 minutos mañana."},
    ],
    "qualification": [
        {"criterion_id": "crm", "label": "CRM que usan", "good": "Nombra el CRM exacto."},
        {"criterion_id": "decide", "label": "Quién decide", "good": "Dice quién aprueba."},
    ],
}
CTX = live_brain.BrainContext(
    snapshot=SNAPSHOT, knowledge={"value_short": "CRM por voz"}, product_context="Vocify", history=None, today="TODAY: Friday 2026-10-16 (UTC)",
    playbook_version_id="pv-1",
)
NO_PLAYBOOK = live_brain.BrainContext(snapshot=None, knowledge={"value_short": "CRM por voz"}, product_context="", history=None, today="TODAY")


def turns(*items):
    return [{"id": f"t{i}", "who": who, "text": text, "t": i * 10.0} for i, (who, text) in enumerate(items)]


CALL = turns(
    ("you", "Hola Javier, soy Toni, será breve."),
    ("them", "Dime, pero rápido. ¿Se integra con HubSpot?"),
    ("you", "Sí, se integra con HubSpot."),
    ("them", "Usamos Salesforce y no queremos cambiar. Mándame un email."),
    ("you", "Vale."),
    ("them", "Y se lo reenviaré a la directora comercial."),
)


def reading(call=CALL, **kw):
    return LiveReading(call_id="c1", sales_motion_key="discovery", turns=call, **kw)


def point(**kw):
    base = {"ref": None, "turns": ["t1"], "kind": "question", "objection_type": "question", "quote": "¿Se integra con HubSpot?",
            "decision": "responder", "decision_note": "", "grounded": True, "source_id": "knowledge", "gap": "", "say": "Sí, se integra con HubSpot.",
            "repeated": False}
    return {**base, **kw}


def run(coro):
    return asyncio.run(coro)


# ---------- points ----------


def test_a_grounded_point_keeps_its_source_and_a_gap_becomes_the_honest_line():
    out = live_points.finalize({"points": [
        point(),
        point(turns=["t3"], quote="no queremos cambiar", kind="objection", objection_type="status_quo", decision="reconducir",
              decision_note="Antes de comparar: falta el dolor", source_id="objection:status_quo", say="¿Qué proceso os cuesta más hoy?"),
        point(turns=["t3"], quote="¿desde cuándo?", grounded=False, source_id=None, gap="La fecha no está escrita", say="Te lo confirmo hoy."),
    ]}, reading(), CTX)
    # In the order said: the third quote is not in t3, so its words are the start of t3, before "no queremos cambiar".
    first, third, second = out["points"]
    assert first["answer"] == "Sí, se integra con HubSpot." and first["source"] == {"id": "knowledge", "label": "Company knowledge"}
    assert second["decision"] == "reconducir" and second["source"]["label"] == "Playbook · status_quo"
    assert third["answer"] is None and third["fallback"] == "Te lo confirmo hoy." and third["gap"] == "La fecha no está escrita" and third["source"] is None
    assert all(p["is_update"] is False and p["outcome"] == "open" for p in out["points"])


def test_source_or_silence_a_claim_with_a_source_this_reading_does_not_have_is_not_shown():
    out = live_points.finalize({"points": [point(source_id="history")]}, reading(), CTX)  # no earlier calls in this reading
    assert out["points"] == [] and out["guards"] == {"unknown_source": 1, "responder_without_source": 1, "empty_say": 1}


def test_a_point_must_come_from_a_turn_the_other_side_said():
    out = live_points.finalize({"points": [point(turns=["t0"]), point(turns=["t99"], quote="nadie dijo esto"), point(turns=[], quote="nadie dijo esto")]}, reading(), CTX)
    assert out["points"] == [] and out["guards"] == {"no_prospect_turn": 3}
    # Cited wrongly but quoted right: found where THEY said it.
    (found,) = live_points.finalize({"points": [point(turns=["t99"])]}, reading(), CTX)["points"]
    assert found["turn_ids"] == ["t1"]


def test_their_words_are_a_verbatim_quote_or_the_start_of_the_turn():
    good, bad = live_points.finalize({"points": [
        point(quote="¿se integra con hubspot"),
        point(turns=["t3"], quote="algo que nadie dijo", kind="objection", objection_type="price", source_id="knowledge"),
    ]}, reading(), CTX)["points"]
    assert good["title"] == "¿se integra con hubspot"
    assert bad["title"] == "Usamos Salesforce y no queremos"


def test_one_point_per_thing_said_a_repeat_is_an_update_never_a_second_point():
    existing = [{"id": "pt-x", "kind": "question", "tag_key": "question", "title": "¿Se integra con HubSpot?", "turn_ids": ["t1"], "outcome": "open", "say": "Sí."}]
    # The model forgot the ref: the same kind, type and turns are the same point.
    out = live_points.finalize({"points": [point(ref=None)]}, reading(points=existing), CTX)
    assert out["points"] == [{"id": "pt-x", "is_update": True, "turn_ids": ["t1"], "repeated": False}]
    assert out["guards"] == {"duplicate_became_update": 1}
    # They say it again later: the same point, reopened, with the new turn; its words (on screen) are not rewritten.
    out = live_points.finalize({"points": [point(ref="pt-x", turns=["t5"], repeated=True, say="Otra frase.")]}, reading(points=existing), CTX)
    assert out["points"] == [{"id": "pt-x", "is_update": True, "turn_ids": ["t1", "t5"], "repeated": True}]


def test_a_second_question_in_the_same_turn_is_its_own_point_but_the_same_one_twice_is_not():
    out = live_points.finalize({"points": [
        point(turns=["t3"], quote="no queremos cambiar"),
        point(turns=["t3"], quote="Mándame un email", kind="objection", objection_type="objection:custom:email", source_id="objection:custom:email"),
        point(turns=["t3"], quote="no queremos cambiar"),
    ]}, reading(), CTX)
    assert [p["tag_key"] for p in out["points"]] == ["question", "objection:custom:email"]
    assert out["points"][1]["tag"] == "Mándame un email"
    assert out["guards"] == {"duplicate_in_result": 1}


def test_the_points_of_one_turn_come_back_each_on_its_own_in_the_order_said():
    call = turns(("you", "Te cuento"), ("them", "Mándame un email, ¿vale? Y yo se lo reenviaré a la directora comercial y lo hablamos."))
    out = live_points.finalize({"points": [  # the model wrote the second thing first
        point(turns=["t1"], quote="se lo reenviaré a la directora", kind="objection", objection_type="authority", decision="reconducir",
              source_id="call", say="¿Qué necesita ver ella para decidir?"),
        point(turns=["t1"], quote="Mándame un email", kind="objection", objection_type="objection:custom:email", decision="cerrar",
              source_id="objection:custom:email", say="Claro, ¿y si lo vemos 15 minutos mañana con ella?"),
    ]}, reading(call=call), CTX)
    assert [p["tag_key"] for p in out["points"]] == ["objection:custom:email", "authority"]
    assert all(p["turn_ids"] == ["t1"] for p in out["points"]) and out["guards"] == {}
    # A quote that drops a word they said is still found where it was said.
    text = "No tenemos para cambiar ahora. Y mira, no me fío mucho de que la IA rellene mis campos."
    assert live_points.offset_in("no me fío de que la IA", text) == live_brain.normalize(text).index("no me fio")


def test_nothing_to_handle_is_nothing():
    out = live_points.finalize({"points": [], "closed": []}, reading(), CTX)
    assert out["points"] == [] and out["closed"] == [] and out["nothing"] is True


def test_what_appears_on_its_own_is_one_or_two_sentences_capped_in_words():
    assert live_points.short("Sí, se integra con HubSpot. ¿Qué CRM usáis hoy?") == ("Sí, se integra con HubSpot. ¿Qué CRM usáis hoy?", False)
    # A third sentence, or one that would pass the cap, is left out: whole sentences only.
    line, cut = live_points.short("Sí. Lo usan equipos de campo. ¿Cuántos sois?")
    assert (line, cut) == ("Sí. Lo usan equipos de campo.", True)
    line, cut = live_points.short("Se integra con HubSpot. " + "Y además registra cada visita del equipo de campo sin que tengan que escribir nada en el móvil ni después.")
    assert (line, cut) == ("Se integra con HubSpot.", True)
    # One sentence too long on its own: cut at its last pause inside the cap.
    long = "Lo que hacemos es que el comercial habla al salir de la visita, y Vocify rellena el CRM con los datos, las tareas y el siguiente paso acordado."
    line, cut = live_points.short(long)
    assert cut and len(line.split()) <= live_points.ANSWER_MAX_WORDS and line == "Lo que hacemos es que el comercial habla al salir de la visita…"
    # In a point: the answer shown is the short one, and the cut is counted.
    (p,) = live_points.finalize({"points": [point(say="Sí, se integra con HubSpot. Y con Salesforce también según lo escrito. ¿Cuál usáis?")]}, reading(), CTX)["points"]
    assert p["answer"] == "Sí, se integra con HubSpot. Y con Salesforce también según lo escrito."


def test_a_figure_no_source_and_nobody_in_the_call_gave_is_an_invention_and_is_not_shown():
    out = live_points.finalize({"points": [
        point(say="De media recuperas entre 6 y 10 horas a la semana."),            # in no source
        point(turns=["t3"], quote="no queremos cambiar", kind="objection", objection_type="status_quo", source_id="objection:status_quo",
              say="¿Te va bien a las 10 o a las 12?"),                                # an hour nobody gave
    ]}, reading(), CTX)
    assert out["points"] == [] and out["guards"]["invented_number"] == 2


def test_numbers_said_in_the_call_in_words_or_digits_are_not_inventions():
    call = turns(("you", "Hola"), ("them", "Somos doce comerciales y usamos Salesforce desde 2019."))
    (p,) = live_points.finalize({"points": [point(turns=["t1"], quote="usamos Salesforce", source_id="call",
                                                  say="Con 12 comerciales desde 2019, ¿qué parte del CRM os cuesta más?")]}, reading(call=call), CTX)["points"]
    assert p["answer"]
    assert live_brain.numbers_in("veintidós y one hundred y 30") == {"22", "1", "100", "30"}


def test_ahora_never_carries_a_figure_nobody_gave():
    out = progress_for({"now": {"kind": "step", "id": "problema", "say": "Con 45 comerciales, ¿cuánto tarda cada uno?"}})
    assert out["now"]["say"] == "Los equipos de campo dejan el CRM para luego." and out["guards"] == {"invented_number": 1}


def test_a_question_the_rep_already_answered_is_not_a_new_point_unless_the_rep_asked():
    call = turns(("you", "Hola"), ("them", "¿Cuántos sois?"), ("you", "Somos dos fundadores más un equipo externo de producto"), ("them", "Vale, bien"))
    out = live_points.finalize({"points": [point(turns=["t1"], quote="¿Cuántos sois?", source_id="call", say="Somos dos fundadores.")]}, reading(call=call), CTX)
    assert out["points"] == [] and out["guards"] == {"rep_already_answered": 1}
    asked = live_points.finalize({"points": [point(turns=["t1"], quote="¿Cuántos sois?", source_id="call", say="Somos dos fundadores.")]}, reading(call=call, reason="responder"), CTX)
    assert len(asked["points"]) == 1


def test_a_fact_that_is_not_written_is_never_a_responder_decision():
    (p,) = live_points.finalize({"points": [point(grounded=False, source_id=None, gap="El precio no está escrito", say="Te lo confirmo hoy.")]}, reading(), CTX)["points"]
    assert p["decision"] is None and p["answer"] is None and p["fallback"] == "Te lo confirmo hoy."


def test_a_point_that_followed_the_teams_own_objection_is_that_objection():
    (p,) = live_points.finalize({"points": [point(turns=["t3"], type="other", quote="Mándame un email", decision="aplazar",
                                                  source_id="objection:custom:email", say="Claro, ¿15 minutos mañana?")]}, reading(), CTX)["points"]
    assert (p["kind"], p["tag_key"], p["tag"]) == ("objection", "objection:custom:email", "Mándame un email")


def test_they_come_back_to_it_only_after_the_rep_spoke_since():
    existing = [{"id": "pt-x", "kind": "question", "tag_key": "question", "title": "¿Se integra con HubSpot?", "turn_ids": ["t1"], "outcome": "open", "say": "Sí."}]
    # The model cites the next turn of theirs (the rep spoke at t2 and t4): they said it again.
    (again,) = live_points.finalize({"points": [point(ref="pt-x", turns=["t3"])]}, reading(points=existing), CTX)["points"]
    assert again["repeated"] is True and again["turn_ids"] == ["t1", "t3"]
    # The same utterance cited twice, nobody spoke in between: not a repeat.
    adjacent = turns(("them", "¿Se integra con HubSpot?"), ("them", "con HubSpot, digo"))
    existing = [{"id": "pt-x", "kind": "question", "tag_key": "question", "title": "¿Se integra con HubSpot?", "turn_ids": ["t0"], "outcome": "open", "say": "Sí."}]
    (same,) = live_points.finalize({"points": [point(ref="pt-x", turns=["t0", "t1"])]}, reading(call=adjacent, points=existing), CTX)["points"]
    assert same["repeated"] is False and same["turn_ids"] == ["t0"]


def test_a_point_that_was_still_being_read_gets_its_words_from_this_reading():
    existing = [{"id": "pt-x", "kind": "question", "tag_key": "question", "title": "¿Se integra?", "turn_ids": ["t1"], "outcome": "open"}]
    (update,) = live_points.finalize({"points": [point(ref="pt-x")]}, reading(points=existing), CTX)["points"]
    assert update["is_update"] and update["answer"] == "Sí, se integra con HubSpot." and "say_text" not in update


def test_without_a_playbook_there_is_no_decision_only_the_answer():
    (p,) = live_points.finalize({"points": [point(decision="reconducir", decision_note="x")]}, reading(), NO_PLAYBOOK)["points"]
    assert p["decision"] is None and p["decision_note"] is None and p["answer"]


def test_after_a_rep_turn_nothing_new_shows_but_points_can_close():
    existing = [{"id": "pt-x", "kind": "question", "tag_key": "question", "title": "t", "turn_ids": ["t1"], "outcome": "open"}]
    out = live_points.finalize(
        {"points": [point(turns=["t3"])], "closed": [{"id": "pt-x", "outcome": "answered", "why": "lo explicó"}]},
        reading(points=existing, reason="rep_turn"), CTX,
    )
    assert out["points"] == [] and out["closed"] == [{"id": "pt-x", "outcome": "answered", "why": "lo explicó"}]
    assert out["guards"] == {"new_point_after_rep_turn": 1}


def test_an_outcome_needs_the_conversation_to_have_gone_on():
    def close(outcome, call, ids=("t1",)):
        existing = [{"id": "pt-x", "kind": "question", "tag_key": "question", "title": "t", "turn_ids": list(ids), "outcome": "open"}]
        return live_points.finalize({"closed": [{"id": "pt-x", "outcome": outcome}]}, reading(call=call, points=existing), CTX)["closed"]

    assert close("answered", turns(("you", "a"), ("them", "pregunta"))) == []  # the rep has not spoken since
    assert close("answered", turns(("you", "a"), ("them", "pregunta"), ("you", "respuesta")))
    assert close("gone", turns(("you", "a"), ("them", "pregunta"), ("you", "x"))) == []  # they said nothing since
    assert close("gone", turns(("you", "a"), ("them", "pregunta"), ("them", "ya lo he visto")))
    moved = turns(("you", "a"), ("them", "pregunta"), ("them", "otra cosa"), ("you", "x"), ("them", "y otra"))
    assert close("unanswered", moved, ids=("t1",))
    assert close("unanswered", turns(("you", "a"), ("them", "pregunta"), ("them", "otra cosa"))) == []  # one turn is not moved on
    late = [{"id": f"t{i}", "who": "them" if i == 1 else "you", "text": "x y z", "t": 100.0 if i == 2 else float(i)} for i in range(3)]
    assert close("unanswered", late)  # 90 s later with nobody dealing with it
    # A final outcome is not rewritten, and the same outcome is not repeated.
    existing = [{"id": "pt-x", "kind": "question", "tag_key": "question", "title": "t", "turn_ids": ["t1"], "outcome": "promised"}]
    assert live_points.finalize({"closed": [{"id": "pt-x", "outcome": "answered"}]}, reading(points=existing), CTX)["closed"] == []


def fake_model(monkeypatch, answer, record=None):
    async def fake_stream(system, user, *, kind):
        if record is not None:
            record.update(system=system, user=user, kind=kind)
        text = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
        yield {"type": "token", "text": text[:10]}
        yield {"type": "text", "text": text, "model": "direct:test", "latency_ms": 123}

    monkeypatch.setattr(live_brain, "stream_json", fake_stream)


def read(req, ctx=CTX):
    async def collect():
        return [e async for e in live_points.read_points(req, ctx)]

    return run(collect())


def test_the_reading_streams_tokens_then_one_result_with_the_cursor(monkeypatch):
    seen: dict = {}
    fake_model(monkeypatch, {"points": [point()], "closed": []}, seen)
    events_out = read(reading(state_version=4))
    assert [e["type"] for e in events_out] == ["token", "result"]
    result = events_out[-1]
    assert result["state_version"] == 4 and result["cursor"] == f"t5:{len(CALL[-1]['text'])}" and result["model"] == "direct:test"
    assert result["points"][0]["id"].startswith("pt-")
    # The prompt carries the principle, the goal, the call with ids and the window mark.
    assert "get closer to the goal" in seen["system"] and "a meeting booked" in seen["user"] and "[t3] Them:" in seen["user"]


def test_unchanged_words_are_not_read_again_unless_the_rep_asked(monkeypatch):
    fake_model(monkeypatch, {"points": [point()]})
    cursor = f"t5:{len(CALL[-1]['text'])}"
    (skipped,) = read(reading(cursor=cursor))
    assert skipped["skipped"] == "no_new_words" and skipped["points"] == []
    assert read(reading(cursor=cursor, reason="responder"))[-1]["points"]


def test_a_model_that_does_not_write_json_is_an_error_not_a_point(monkeypatch):
    fake_model(monkeypatch, "lo siento, no puedo")
    assert read(reading())[-1] == {"type": "error", "message": "the model did not write JSON"}


# ---------- progress ----------


def progress_for(raw, **kw):
    return live_progress.finalize_progress(raw, reading(**kw), CTX, None)


def test_a_step_is_done_only_with_the_reps_own_words_and_a_data_point_with_theirs():
    out = progress_for({
        "steps": [
            {"id": "apertura", "turns": ["t0"], "quote": "soy Toni, será breve"},
            {"id": "problema", "turns": ["t0"], "quote": "el CRM se deja para luego"},  # not what the rep said
            {"id": "inventado", "turns": ["t0"], "quote": "soy Toni, será breve"},
        ],
        "data": [
            {"id": "crm", "turns": ["t3"], "value": "Salesforce", "quote": "Usamos Salesforce"},
            {"id": "decide", "turns": ["t2"], "value": "El comercial", "quote": "Sí, se integra"},  # the rep's words are not data
        ],
    })
    assert [s["id"] for s in out["steps"]] == ["apertura"] and out["steps"][0]["by"] == "brain"
    assert [d["id"] for d in out["data"]] == ["crm"] and out["data"][0]["quote"] == "Usamos Salesforce"
    assert out["guards"] == {"step_without_evidence": 1, "data_without_evidence": 1}


def test_a_model_that_cites_turns_by_number_or_the_wrong_turn_still_gets_its_evidence_located_by_the_quote():
    out = progress_for({
        "steps": [{"id": "apertura", "turns": [0], "quote": "soy Toni, será breve"}, {"id": "problema", "turns": ["t3"], "quote": "Los equipos de campo dejan el CRM"}],
        "data": [{"id": "crm", "turns": ["t1"], "value": "Salesforce", "quote": "Usamos Salesforce"}],  # said at t3, cited t1
    })
    assert [s["id"] for s in out["steps"]] == ["apertura"] and out["steps"][0]["turn_ids"] == ["t0"]
    assert out["data"][0]["turn_ids"] == ["t3"] and out["guards"] == {"step_without_evidence": 1}


def test_a_quote_may_drop_a_stutter_and_join_two_pieces_but_not_change_the_words():
    by_id = live_brain.turns_by_id([LiveReading(call_id="c", turns=turns(("you", "No, no te te pongo ahora muy rápido el contexto, Javier, que veo que eres CEO")), reason="turn_end").turns[0]])
    assert live_brain.is_quote_of("te pongo ahora muy rápido el contexto", ["t0"], by_id)
    assert live_brain.is_quote_of("te pongo ahora … veo que eres CEO", ["t0"], by_id)
    assert not live_brain.is_quote_of("te pongo ahora muy despacio el contexto", ["t0"], by_id)
    assert not live_brain.is_quote_of("eres CEO te pongo", ["t0"], by_id)  # out of order
    assert not live_brain.is_quote_of("", ["t0"], by_id)


def test_the_steps_own_example_cannot_lend_its_figures_to_ahora():
    snapshot = {**SNAPSHOT, "steps": [{**SNAPSHOT["steps"][1], "example": "Con vuestros 22 comerciales en España, ¿cuánto tarda cada uno?"}]}
    ctx = live_brain.BrainContext(snapshot=snapshot, knowledge=None, product_context="", history=None, today="TODAY", playbook_version_id="pv")
    out = live_progress.finalize_progress({"now": {"kind": "step", "id": "problema", "say": "Con tus 22 comerciales, ¿cuánto tarda cada uno?"}}, reading(), ctx, None)
    assert out["now"] == {"kind": "step", "id": "problema", "say": None}  # neither the model's line nor the example carries another prospect's figure


def test_what_is_done_or_the_reps_is_never_listed_again():
    out = progress_for(
        {"steps": [{"id": "apertura", "turns": ["t0"], "quote": "soy Toni"}], "data": [{"id": "crm", "turns": ["t3"], "value": "SF", "quote": "Usamos Salesforce"}]},
        progress={"done_steps": ["apertura"], "rep_unticked": ["crm"]},
    )
    assert out["steps"] == [] and out["data"] == []


def test_ahora_is_stable_unless_it_is_done_or_the_conversation_moved():
    base = {"kind": "step", "id": "problema", "say": "Los equipos de campo dejan el CRM."}
    out = progress_for({"now": {"kind": "data", "id": "crm", "say": "¿Qué CRM usáis?", "moved_on": False}}, progress={"now": base})
    assert out["now"] == base and out["guards"] == {"now_kept": 1}
    out = progress_for({"now": {"kind": "data", "id": "crm", "say": "¿Qué CRM usáis?", "moved_on": True}}, progress={"now": base})
    assert out["now"] == {"kind": "data", "id": "crm", "say": "¿Qué CRM usáis?"}
    out = progress_for({"now": {"kind": "data", "id": "crm", "say": "¿Qué CRM usáis?"}}, progress={"now": base, "rep_ticked": ["problema"]})
    assert out["now"]["id"] == "crm"
    # Nothing valid: the first pending item in the playbook's order, with the step's own example.
    out = progress_for({"now": {"kind": "step", "id": "no-existe"}}, progress={"done_steps": ["apertura"]})
    assert out["now"] == {"kind": "step", "id": "problema", "say": "Los equipos de campo dejan el CRM para luego."}
    assert out["missing"][0] == "problema" and "apertura" not in out["missing"]


def test_the_goal_needs_a_quote_and_a_call_type_with_a_goal():
    out = progress_for({"goal": {"reached": True, "turns": ["t5"], "value": "Reunión mañana", "quote": "se lo reenviaré a la directora"}})
    assert out["goal"]["reached"] and out["goal"]["value"] == "Reunión mañana"
    assert progress_for({"goal": {"reached": True, "turns": ["t5"], "quote": "nunca se dijo"}})["goal"] is None


def test_steps_about_delivery_are_not_offered_live():
    aids = {"steps": {"treinta": {"concept": "Explica en 30 s", "live": False}, "problema": {"concept": "Cuenta el problema", "live": True}}, "data": {}}
    prompt = live_progress.build_progress_prompt(reading(), CTX, aids)
    assert "treinta" not in prompt and "problema" in prompt
    out = live_progress.finalize_progress({"steps": [{"id": "treinta", "turns": ["t0"], "quote": "soy Toni"}]}, reading(), CTX, aids)
    assert out["steps"] == []


def test_a_type_change_reads_everything_again_and_marks_the_data_reread():
    out = progress_for({"data": [{"id": "crm", "turns": ["t3"], "value": "Salesforce", "quote": "Usamos Salesforce"}]}, type_changed=True)
    assert out["data"][0]["reread"] is True


def test_progress_without_a_playbook_says_so_and_asks_no_model(monkeypatch):
    async def never(*_a, **_k):
        raise AssertionError("no model call")

    monkeypatch.setattr(live_brain, "complete_json", never)
    result = run(live_progress.read_progress(reading(), NO_PLAYBOOK))
    assert result["has_playbook"] is False and result["steps"] == [] and result["now"] is None


def test_the_aids_are_generated_once_per_version(monkeypatch):
    live_progress._aids.clear()
    calls = []

    async def fake(system, user, *, kind):
        calls.append(kind)
        return {"steps": {"apertura": {"concept": "Preséntate", "live": True}, "treinta": {"concept": "30 s", "live": False}, "otro": {"concept": "x", "live": True}},
                "data": {"crm": {"question": "¿Qué CRM usáis?"}}}, {"model": "m", "latency_ms": 1, "error": None}

    monkeypatch.setattr(live_brain, "complete_json", fake)
    first, second = run(live_progress.aids_for(SNAPSHOT)), run(live_progress.aids_for(SNAPSHOT))
    assert calls == ["aids"] and first == second
    assert set(first["steps"]) == {"apertura", "treinta"} and first["steps"]["treinta"]["live"] is False  # ids the playbook does not have are dropped
    assert first["data"] == {"crm": {"question": "¿Qué CRM usáis?"}}
    edited = {**SNAPSHOT, "steps": [{**SNAPSHOT["steps"][0], "criterion": "Otra cosa."}] + SNAPSHOT["steps"][1:]}
    run(live_progress.aids_for(edited))
    assert calls == ["aids", "aids"]  # an edited version never reads a stale phrase


# ---------- recap ----------


def test_the_recap_drops_a_line_with_a_number_nobody_said_and_adds_what_is_unknown_in_code(monkeypatch):
    async def fake(system, user, *, kind):
        assert kind == "recap" and "[t5]" not in user  # reads up to the tap
        return {"lines": ["Javier usa Salesforce.", "Tienen 45 comerciales."]}, {"model": "m", "latency_ms": 5, "error": None}

    monkeypatch.setattr(live_brain, "complete_json", fake)
    out = run(live_progress.read_recap(reading(up_to="t3", progress={"known_data": ["crm"]}), CTX))
    assert out["lines"] == ["Javier usa Salesforce."] and out["unknown"] == ["Quién decide"] and out["up_to"] == "t3"
    assert out["guards"] == {"invented_number": 1}


# ---------- the shared shape ----------


def test_the_example_the_shared_state_reads_is_what_the_producers_write():
    (new, other, update) = EXAMPLE["points_result"]["points"]
    out = live_points.finalize({"points": [point(), point(turns=["t3"], kind="objection", objection_type="status_quo", decision="reconducir",
                                                         decision_note="x", source_id="objection:status_quo", say="¿Qué proceso os cuesta más?")]},
                               reading(), CTX)
    assert set(out["points"][0]) == set(new) and set(out["points"][1]) == set(other)
    existing = [{"id": "pt-x", "kind": "question", "tag_key": "question", "title": "t", "turn_ids": ["t1"], "outcome": "open", "say": "s"}]
    assert set(live_points.finalize({"points": [point(ref="pt-x")]}, reading(points=existing), CTX)["points"][0]) == set(update) - {"turn_ids"} | {"turn_ids"}
    assert set(EXAMPLE["points_result"]) - {"model", "latency_ms", "type"} <= set(out) | {"producer", "state_version", "cursor"}
    got = progress_for({"steps": [{"id": "apertura", "turns": ["t0"], "quote": "soy Toni"}], "data": [{"id": "crm", "turns": ["t3"], "value": "SF", "quote": "Usamos Salesforce"}]})
    assert set(got["steps"][0]) == set(EXAMPLE["progress_result"]["steps"][0])
    assert set(got["data"][0]) == set(EXAMPLE["progress_result"]["data"][0])
    assert set(got) - {"guards", "playbook_version_id"} <= set(EXAMPLE["progress_result"])


# ---------- the endpoints ----------


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


def client_for(db, monkeypatch, enabled=True):
    monkeypatch.setattr(copilot_api, "is_enabled", lambda _db, _company, flag: enabled and flag == "LIVE_BRAIN_ENABLED")

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


BODY = {"call_id": "draft-1", "sales_motion_key": "discovery", "call_mode": "meeting", "turns": CALL, "state_version": 2}


def test_the_endpoints_are_off_unless_the_company_has_the_flag(monkeypatch):
    client = client_for(FakeDb(), monkeypatch, enabled=False)
    for path in ("points", "progress", "recap"):
        response = client.post(f"/api/v1/copilot/live/{path}", json=BODY)
        assert response.status_code == 403 and response.json()["detail"] == "live_brain_disabled"


def test_points_stream_and_the_reading_is_logged_against_the_call(monkeypatch):
    fake_model(monkeypatch, {"points": [point()], "closed": []})
    db = FakeDb()
    response = client_for(db, monkeypatch).post("/api/v1/copilot/live/points", json=BODY)
    frames = [json.loads(block[6:]) for block in response.text.split("\n\n") if block.startswith("data: ")]
    assert [f["type"] for f in frames] == ["token", "result", "done"]
    assert frames[1]["state_version"] == 2 and frames[1]["points"][0]["answer"]
    (row,) = db.inserted
    assert row["kind"] == "points" and row["capture_id"] == "draft-1" and row["company_id"] == "co-1" and row["latency_ms"] == 123
    assert row["detail"]["reason"] == "turn_end" and row["detail"]["points"] == 1 and row["detail"]["state_version"] == 2
    assert row["latest_turn"].startswith("Y se lo reenviaré") and "turns" in row["detail"]


def test_progress_and_recap_return_json_and_log(monkeypatch):
    async def fake(system, user, *, kind):
        raw = {"steps": [{"id": "apertura", "turns": ["t0"], "quote": "soy Toni"}]} if kind == "progress" else {"lines": ["Usa Salesforce."]}
        return raw, {"model": "direct:test", "latency_ms": 900, "error": None}

    async def no_aids(_snapshot):
        return None

    monkeypatch.setattr(live_brain, "complete_json", fake)
    monkeypatch.setattr(live_progress, "aids_for", no_aids)
    db = FakeDb()
    client = client_for(db, monkeypatch)
    progress = client.post("/api/v1/copilot/live/progress", json=BODY).json()
    assert progress["steps"][0]["id"] == "apertura" and progress["producer"] == "progress" and progress["state_version"] == 2
    recap = client.post("/api/v1/copilot/live/recap", json=BODY).json()
    assert recap["lines"] == ["Usa Salesforce."]
    assert [r["kind"] for r in db.inserted] == ["progress", "recap"] and db.inserted[0]["detail"]["steps"] == 1


def test_a_model_failure_is_a_502_and_is_logged(monkeypatch):
    async def fake(system, user, *, kind):
        return None, {"model": None, "latency_ms": None, "error": "HTTP 503"}

    monkeypatch.setattr(live_brain, "complete_json", fake)
    monkeypatch.setattr(live_progress, "aids_for", lambda _s: asyncio.sleep(0))
    db = FakeDb()
    response = client_for(db, monkeypatch).post("/api/v1/copilot/live/recap", json=BODY)
    assert response.status_code == 502 and db.inserted[0]["error"] == "HTTP 503"


def test_the_brains_log_pauses_on_its_own_when_migration_082_is_missing(monkeypatch):
    class Failing(FakeDb):
        def table(self, name):
            raise RuntimeError("violates check constraint live_assist_events_kind_check")

    monkeypatch.setattr(events, "_brain_paused_until", 0.0)
    monkeypatch.setattr(events, "_paused_until", 0.0)
    events.record(Failing(), {"kind": "points", "user_id": "u"})
    assert events._brain_paused_until > 0 and events._paused_until == 0.0  # the turn checks and cards still log



def test_unanswered_points_lists_what_had_no_source_in_their_words():
    from app.services.copilot import events
    points = [
        {"is_update": False, "answer": "Sí, con HubSpot.", "title": "¿os integráis con HubSpot?", "kind": "question", "tag_key": "question"},
        {"is_update": False, "answer": None, "gap": "dónde se guardan datos", "title": "¿dónde guardáis los datos?", "kind": "question", "tag_key": "question"},
        {"is_update": True, "answer": None, "gap": "x", "title": "lo repite", "kind": "question"},
        {"is_update": False, "answer": None, "gap": None, "title": "  ", "kind": "objection"},
        {"is_update": False, "answer": None, "gap": "precio de planes", "title": "¿qué dos planes tenéis? " * 20, "kind": "question", "tag_key": "question"},
    ]
    rows = events.unanswered_points(points)
    assert [r["said"][:26] for r in rows] == ["¿dónde guardáis los datos?", "¿qué dos planes tenéis? ¿q"]
    assert rows[0] == {"said": "¿dónde guardáis los datos?", "missing": "dónde se guardan datos", "kind": "question", "tag": "question"}
    assert len(rows[1]["said"]) <= events.UNANSWERED_SAID_MAX


def test_unanswered_points_is_none_when_everything_was_answered_and_caps_the_list():
    from app.services.copilot import events
    assert events.unanswered_points([{"is_update": False, "answer": "ok", "title": "a"}]) is None
    assert events.unanswered_points(None) is None
    many = [{"is_update": False, "answer": None, "title": f"pregunta {i}", "kind": "question"} for i in range(6)]
    assert len(events.unanswered_points(many)) == events.UNANSWERED_MAX
