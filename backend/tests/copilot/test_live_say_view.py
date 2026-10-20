"""The brain's outputs for the "Qué decir" view (build contract 2026-10-20 §2): go deeper, Responder with nothing, rewrite,
a question for a step, the parts of a step, and the UI events log."""

import json

from tests.copilot.test_live_brain import CALL, CTX, FakeDb, client_for, fake_model, point, read, reading, run, turns

from app.services.copilot import events, live_brain, live_points, live_progress

PARTS_SNAPSHOT = {
    **CTX.snapshot,
    "steps": CTX.snapshot["steps"] + [{
        "step_id": "encaje", "label": "Cualificar el encaje",
        "criterion": "Averigua al menos tres de estos datos: CRM que usan, número de comerciales, visitas al día, quién decide y plazo.",
        "example": None,
    }],
}
PARTS_AIDS = {
    "steps": {"encaje": {"concept": "Cualifica el encaje", "live": True, "need": 3, "parts": [
        {"id": "crm", "label": "CRM que usan"}, {"id": "comerciales", "label": "número de comerciales"},
        {"id": "visitas", "label": "visitas al día"}, {"id": "decide", "label": "quién decide"}, {"id": "plazo", "label": "plazo"},
    ]}},
    "data": {"crm": {"question": "¿Qué CRM usáis hoy?"}},
}
PARTS_CTX = live_brain.BrainContext(**{**CTX.__dict__, "snapshot": PARTS_SNAPSHOT})

PAIN = turns(
    ("you", "Hola Javier, soy Toni, será breve. ¿Cómo lleváis el seguimiento de las visitas?"),
    ("them", "Pues mira, el seguimiento es un caos y perdemos muchísimo tiempo con eso."),
)


def deepen(**kw):
    return point(**{"turns": ["t1"], "type": "deepen", "quote": "el seguimiento es un caos", "decision": None, "grounded": True,
                     "source_id": "step:problema", "say": "¿Qué es lo que más se os escapa del seguimiento?", **kw})


# ---------- go deeper ----------


def test_go_deeper_is_only_for_the_say_view():
    off = live_points.finalize({"points": [deepen()]}, reading(call=PAIN), CTX)
    assert off["points"] == [] and off["guards"] == {"deepen_off": 1}
    (on,) = live_points.finalize({"points": [deepen()]}, reading(call=PAIN, say_view=True), CTX)["points"]
    assert on["kind"] == "deepen" and on["tag_key"] == "deepen" and on["decision"] is None and on["gap"] is None
    assert on["answer"] == "¿Qué es lo que más se os escapa del seguimiento?" and on["fallback"] is None
    assert on["source"] == {"id": "problema", "label": "Playbook · Plantear el problema"} and on["turn_ids"] == ["t1"]


def test_go_deeper_serves_a_step_of_this_playbook_and_never_runs_without_steps():
    out = live_points.finalize({"points": [deepen(source_id="knowledge")]}, reading(call=PAIN, say_view=True), CTX)
    assert out["points"] == [] and out["guards"] == {"deepen_without_step": 1}
    no_steps = live_brain.BrainContext(**{**CTX.__dict__, "snapshot": {**CTX.snapshot, "steps": []}})
    assert live_points.finalize({"points": [deepen()]}, reading(call=PAIN, say_view=True), no_steps)["guards"] == {"deepen_off": 1}


def test_go_deeper_never_on_a_statement_that_already_gave_the_figure():
    said = turns(("you", "¿Cuánto tiempo perdéis?"), ("them", "Perdemos unas ocho horas semanales con el seguimiento."))
    out = live_points.finalize({"points": [deepen(quote="Perdemos unas ocho horas")]}, reading(call=said, say_view=True), CTX)
    assert out["points"] == [] and out["guards"] == {"deepen_figure_given": 1}
    # A figure about something else, in another sentence of the same turn, does not count.
    mixed = turns(("you", "Cuéntame."), ("them", "Somos 12 comerciales. El seguimiento es un caos total."))
    (ok,) = live_points.finalize({"points": [deepen(quote="El seguimiento es un caos")]}, reading(call=mixed, say_view=True), CTX)["points"]
    assert ok["kind"] == "deepen"


def test_go_deeper_one_open_at_a_time_and_one_per_reading():
    two = live_points.finalize({"points": [deepen(), deepen(quote="perdemos muchísimo tiempo", say="¿En qué se os va el tiempo?")]},
                               reading(call=PAIN, say_view=True), CTX)
    assert len(two["points"]) == 1 and two["guards"] == {"deepen_one_open": 1}
    open_one = [{"id": "pt-d", "kind": "deepen", "tag_key": "deepen", "title": "las visitas no se apuntan", "turn_ids": ["t0"], "outcome": "open", "say": "¿Por qué?"}]
    out = live_points.finalize({"points": [deepen()]}, reading(call=PAIN, say_view=True, points=open_one), CTX)
    assert out["points"] == [] and out["guards"] == {"deepen_one_open": 1}


def test_go_deeper_never_twice_on_the_same_topic_nor_while_the_rep_follows_it_up():
    taken = [{"id": "pt-d", "kind": "deepen", "tag_key": "deepen", "title": "el seguimiento es un caos", "turn_ids": ["t1"],
              "outcome": "answered", "say": "¿Qué se os escapa?"}]
    later = PAIN + turns(("you", "x"), ("them", "Y además el seguimiento es un caos con los pedidos."))[1:]
    later[-1]["id"], later[-1]["t"] = "t9", 90.0
    out = live_points.finalize({"points": [deepen(turns=["t9"], quote="el seguimiento es un caos")]}, reading(call=later, say_view=True, points=taken), CTX)
    assert out["points"] == [] and out["guards"] == {"deepen_same_topic": 1}
    following = PAIN + [{"id": "t2", "who": "you", "text": "¿Y eso por qué?", "t": 30.0}]
    out = live_points.finalize({"points": [deepen()]}, reading(call=following, say_view=True), CTX)
    assert out["points"] == [] and out["guards"] == {"deepen_rep_following": 1}


def test_the_say_view_prompt_teaches_go_deeper_and_the_old_one_is_unchanged(monkeypatch):
    seen: dict = {}
    fake_model(monkeypatch, {"points": [], "closed": []}, seen)
    read(reading(call=PAIN))
    assert "deepen" not in seen["system"] and "STEPS (" not in seen["user"]
    read(reading(call=PAIN, say_view=True))
    assert "GO DEEPER" in seen["system"] and '"deepen"' in seen["system"] and "STEPS (" in seen["user"]
    assert live_points.SYSTEM.count("{") == live_points.SYSTEM.count("}") and "{deepen" not in live_points.SYSTEM + live_points.SYSTEM_SAY


def test_every_point_keeps_the_turns_it_came_from():
    out = live_points.finalize({"points": [point(), point(turns=["t3", "t5"], quote="Mándame un email", kind="objection",
                                                         objection_type="other", source_id="objection:custom:email", say="Te propongo 15 minutos mañana.")]},
                               reading(), CTX)
    assert [p["turn_ids"] for p in out["points"]] == [["t1"], ["t3", "t5"]]


# ---------- Responder with nothing: the next best question ----------


def test_responder_with_nothing_gives_the_missing_item_and_its_question_in_the_calls_words(monkeypatch):
    seen: dict = {}
    fake_model(monkeypatch, {"points": [], "closed": [], "next": {"question": "Javier, ¿qué CRM usáis con la directora comercial?"}}, seen)
    (*_, result) = read(reading(reason="responder"))
    assert result["next"] == {"kind": "data", "id": "crm", "label": "CRM que usan", "question": "Javier, ¿qué CRM usáis con la directora comercial?"}
    assert "PENDING ITEM: CRM que usan" in seen["user"]


def test_responder_next_follows_the_progress_pick_and_skips_what_is_known(monkeypatch):
    fake_model(monkeypatch, {"points": [], "closed": [], "next": {"question": "¿Quién aprueba algo así?"}})
    progress = {"known_data": ["crm"], "now": {"kind": "data", "id": "decide"}}
    (*_, result) = read(reading(reason="responder", progress=progress))
    assert result["next"]["id"] == "decide" and result["next"]["label"] == "Quién decide"


def test_responder_next_falls_back_to_the_playbooks_question_and_is_null_with_a_point_or_an_invention(monkeypatch):
    live_progress._aids[live_progress.aids_key(CTX.snapshot)] = {"steps": {}, "data": {"crm": {"question": "¿Qué CRM usáis hoy?"}}}
    try:
        fake_model(monkeypatch, {"points": [], "closed": []})
        assert read(reading(reason="responder"))[-1]["next"]["question"] == "¿Qué CRM usáis hoy?"
        fake_model(monkeypatch, {"points": [], "closed": [], "next": {"question": "¿Usáis los 45 usuarios de Salesforce?"}})
        assert read(reading(reason="responder"))[-1]["next"]["question"] == "¿Qué CRM usáis hoy?"  # 45 was never said
        fake_model(monkeypatch, {"points": [point()], "closed": [], "next": {"question": "¿Qué CRM usáis?"}})
        assert read(reading(reason="responder"))[-1]["next"] is None
    finally:
        live_progress._aids.clear()
    fake_model(monkeypatch, {"points": [], "closed": []})
    assert "next" not in read(reading())[-1]  # only Responder asks for it


# ---------- rewrite ----------

SHOWN = {"id": "pt-1", "kind": "question", "tag_key": "question", "title": "¿Se integra con HubSpot?", "turn_ids": ["t1"],
         "outcome": "open", "say": "Sí, se integra con HubSpot.", "source_id": "knowledge", "versions": ["Sí, se integra con HubSpot."]}


def rewrite_req(point_in=SHOWN, version=1, **kw):
    return reading(reason="rewrite", points=[point_in], target={"point_id": point_in["id"], "version": version}, **kw)


def test_a_rewrite_is_the_same_point_from_another_angle_of_the_same_source_and_never_a_new_point(monkeypatch):
    seen: dict = {}
    fake_model(monkeypatch, {"answer": "¿Qué tendría que pasar entre HubSpot y Vocify para que os sirva?"}, seen)
    events_out = read(rewrite_req(version=1))
    result = events_out[-1]
    assert result["rewrite"] == {"point_id": "pt-1", "version": 2, "answer": "¿Qué tendría que pasar entre HubSpot y Vocify para que os sirva?"}
    assert result["points"] == [] and result["closed"] == [] and seen["kind"] == "rewrite"
    assert "CRM por voz" in seen["user"] and "- Sí, se integra con HubSpot." in seen["user"]  # its source and what was shown


def test_a_rewrite_that_repeats_a_shown_version_or_invents_a_figure_is_none(monkeypatch):
    fake_model(monkeypatch, {"answer": "Sí, se integra con HubSpot."})
    assert read(rewrite_req())[-1]["rewrite"] is None
    fake_model(monkeypatch, {"answer": "Lo usan 300 equipos con HubSpot."})
    out = read(rewrite_req())[-1]
    assert out["rewrite"] is None and out["guards"]["invented_number"] == 1
    fake_model(monkeypatch, {"answer": None})
    assert read(rewrite_req())[-1]["rewrite"] is None


def test_a_rewrite_of_an_unknown_point_is_a_question_back_never_a_fact(monkeypatch):
    unknown = {**SHOWN, "say": "Te lo confirmo hoy.", "source_id": None, "versions": ["Te lo confirmo hoy."]}
    seen: dict = {}
    fake_model(monkeypatch, {"answer": "Sí, también con Pipedrive."}, seen)
    out = read(rewrite_req(unknown))[-1]
    assert out["rewrite"] is None and out["guards"] == {"rewrite_unknown_not_a_question": 1}
    assert "SOURCE: none" in seen["user"]
    fake_model(monkeypatch, {"answer": "¿Qué necesitáis que haga con HubSpot exactamente?"})
    assert read(rewrite_req(unknown))[-1]["rewrite"]["answer"] == "¿Qué necesitáis que haga con HubSpot exactamente?"


def test_a_rewrite_for_a_point_the_reading_does_not_have_is_none_and_is_never_skipped_as_old_words(monkeypatch):
    fake_model(monkeypatch, {"answer": "x"})
    out = read(reading(reason="rewrite", points=[], target={"point_id": "pt-zz", "version": 1}))[-1]
    assert out["rewrite"] is None and out["guards"] == {"rewrite_unknown_point": 1}
    req = rewrite_req(cursor=f"t5:{len(CALL[-1]['text'])}")
    fake_model(monkeypatch, {"answer": "¿Qué os importa más de la integración con HubSpot?"})
    assert read(req)[-1]["rewrite"] is not None


def test_a_rewrite_takes_its_source_from_the_playbook_entry_the_point_followed(monkeypatch):
    entry_point = {**SHOWN, "kind": "objection", "tag_key": "objection:custom:email", "title": "Mándame un email", "turn_ids": ["t3"],
                   "say": "Te propongo 15 minutos mañana.", "source_id": "objection:custom:email", "versions": ["Te propongo 15 minutos mañana."]}
    seen: dict = {}
    fake_model(monkeypatch, {"answer": "¿Y si lo vemos 15 minutos mañana y te lo mando después?"}, seen)
    assert read(rewrite_req(entry_point))[-1]["rewrite"]["answer"].startswith("¿Y si lo vemos")
    assert "Ofrecer 15 minutos mañana." in seen["user"] and "Mándame un email" in seen["user"]


# ---------- a question for a step ----------


def test_ask_step_writes_one_question_for_that_pending_item_from_the_call(monkeypatch):
    seen: dict = {}
    fake_model(monkeypatch, {"question": "¿Quién más tendría que ver esto además de la directora comercial?"}, seen)
    result = read(reading(reason="ask_step", target={"kind": "data", "id": "decide"}))[-1]
    assert result["step_question"] == {"kind": "data", "id": "decide", "question": "¿Quién más tendría que ver esto además de la directora comercial?"}
    assert seen["kind"] == "ask_step" and "Quién decide" in seen["user"] and "[t5] Them:" in seen["user"]
    assert "APPROVED ANSWERS" not in seen["user"]  # a small prompt: it must be as fast as a point


def test_ask_step_for_an_item_that_is_done_or_not_in_the_playbook_is_none(monkeypatch):
    fake_model(monkeypatch, {"question": "¿x?"})
    done = read(reading(reason="ask_step", target={"kind": "step", "id": "apertura"}, progress={"done_steps": ["apertura"]}))[-1]
    assert done["step_question"] is None and done["guards"] == {"step_not_pending": 1}
    assert read(reading(reason="ask_step", target={"kind": "step", "id": "nope"}))[-1]["step_question"] is None


def test_ask_step_asks_for_the_first_missing_part_of_a_step_with_parts(monkeypatch):
    live_progress._aids[live_progress.aids_key(PARTS_SNAPSHOT)] = PARTS_AIDS
    try:
        seen: dict = {}
        fake_model(monkeypatch, {"question": "¿Cuántas visitas hacéis al día?"}, seen)
        req = reading(reason="ask_step", target={"kind": "step", "id": "encaje"}, progress={"parts": {"encaje": ["crm", "comerciales"]}})
        assert read(req, PARTS_CTX)[-1]["step_question"]["question"] == "¿Cuántas visitas hacéis al día?"
        assert "Still missing: visitas al día, quién decide, plazo (ask for the first one)" in seen["user"]
    finally:
        live_progress._aids.clear()


# ---------- the parts of a step ----------


def parts_progress(raw, **kw):
    return live_progress.finalize_progress(raw, reading(**kw), PARTS_CTX, PARTS_AIDS)


PARTS_CALL = turns(
    ("you", "¿Qué CRM usáis y cuántos sois?"),
    ("them", "Usamos Salesforce y somos doce comerciales."),
    ("you", "¿Y quién lo decidiría?"),
    ("them", "Lo decide la directora comercial."),
)


def test_a_step_with_parts_is_open_until_need_parts_are_heard_each_with_their_words():
    out = parts_progress({"parts": [
        {"step": "encaje", "id": "crm", "turns": ["t1"], "quote": "Usamos Salesforce"},
        {"step": "encaje", "id": "comerciales", "turns": ["t1"], "quote": "somos doce comerciales"},
        {"step": "encaje", "id": "plazo", "turns": ["t1"], "quote": "antes de enero"},  # nobody said it
        {"step": "encaje", "id": "inventado", "turns": ["t1"], "quote": "Usamos Salesforce"},  # not a part of the step
    ]}, call=PARTS_CALL)
    (step,) = out["steps"]
    assert step["id"] == "encaje" and step["status"] == "open" and step["need"] == 3 and "by" not in step
    assert [(p["id"], p["done"]) for p in step["parts"]] == [("crm", True), ("comerciales", True), ("visitas", False), ("decide", False), ("plazo", False)]
    assert step["parts"][0] == {"id": "crm", "label": "CRM que usan", "done": True, "quote": "Usamos Salesforce"}
    assert out["guards"] == {"part_without_evidence": 1}


def test_a_step_with_parts_is_done_when_need_parts_are_heard_across_readings():
    out = parts_progress({"parts": [{"step": "encaje", "id": "decide", "turns": ["t3"], "quote": "Lo decide la directora comercial"}]},
                         call=PARTS_CALL, progress={"parts": {"encaje": ["crm", "comerciales"]}})
    (step,) = out["steps"]
    assert step["status"] == "done" and step["by"] == "brain" and step["turn_ids"] == ["t3"] and step["quote"] == "Lo decide la directora comercial"
    assert sum(p["done"] for p in step["parts"]) == 3 and step["parts"][0]["quote"] is None  # known before: the client keeps its quote
    assert "encaje" not in out["missing"]


def test_a_step_with_parts_is_never_done_by_the_reps_words_and_heard_parts_are_not_listed_again():
    out = parts_progress({"steps": [{"id": "encaje", "turns": ["t0"], "quote": "¿Qué CRM usáis y cuántos sois?"}],
                          "parts": [{"step": "encaje", "id": "crm", "turns": ["t1"], "quote": "Usamos Salesforce"}]},
                         call=PARTS_CALL, progress={"parts": {"encaje": ["crm"]}})
    assert out["steps"] == [] and out["guards"] == {"step_with_parts_is_done_by_its_parts": 1}


def test_the_aids_list_a_steps_parts_only_in_the_criterions_own_words():
    raw = {"steps": {"encaje": {"concept": "Cualifica", "live": True, "need": 3, "parts": [
        {"id": "CRM que usan", "label": "CRM que usan"}, {"id": "n_mero", "label": "Número de comerciales"},
        {"id": "presupuesto", "label": "Presupuesto anual"}, {"id": "plazo", "label": "Plazo"},
    ]}, "apertura": {"concept": "Preséntate", "live": True, "parts": [{"id": "x", "label": "Saludo"}]}}}
    aids = live_progress._clean_aids(raw, PARTS_SNAPSHOT)
    assert aids["steps"]["encaje"]["parts"] == [
        {"id": "crm_que_usan", "label": "CRM que usan"}, {"id": "numero_de_comerciales", "label": "Número de comerciales"}, {"id": "plazo", "label": "Plazo"},
    ]
    assert aids["steps"]["encaje"]["need"] == 3 and "parts" not in aids["steps"]["apertura"]  # one part is not a list
    raw["steps"]["encaje"]["need"] = 9
    assert live_progress._clean_aids(raw, PARTS_SNAPSHOT)["steps"]["encaje"]["need"] == 3  # never more than the parts


def test_the_progress_prompt_lists_the_parts_and_what_was_heard():
    prompt = live_progress.build_progress_prompt(reading(call=PARTS_CALL, progress={"parts": {"encaje": ["crm"]}}), PARTS_CTX, PARTS_AIDS)
    assert "PARTS OF STEPS" in prompt and "crm (CRM que usan)" in prompt and "done when 3 are found" in prompt
    assert "Parts found: encaje: crm" in prompt


# ---------- UI events ----------


def test_ui_events_are_204_and_written_as_kind_ui_with_the_event_in_detail(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(events, "_ui_paused_until", 0.0)
    response = client_for(db, monkeypatch).post("/api/v1/copilot/live/events", json={"call_id": "draft-1", "call_mode": "softphone", "events": [
        {"kind": "shown", "at": 1760950000123, "point_id": "pt-1"},
        {"kind": "ask_step", "at": 12.5, "step_kind": "step", "step_id": "encaje", "detail": {"version": 2, "words": "x" * 500, "nested": {"no": 1}}},
        {"kind": "not_an_event", "at": 1},
    ]})
    assert response.status_code == 204 and response.content == b""
    (batch,) = db.inserted
    assert [r["kind"] for r in batch] == ["ui", "ui"] and all(r["capture_id"] == "draft-1" and r["company_id"] == "co-1" for r in batch)
    assert batch[0]["detail"] == {"event": "shown", "at": 1760950000123, "point_id": "pt-1"}
    assert batch[1]["detail"]["event"] == "ask_step" and batch[1]["detail"]["version"] == 2 and len(batch[1]["detail"]["words"]) == 300
    assert "nested" not in batch[1]["detail"] and batch[1]["call_mode"] == "softphone"


def test_ui_events_are_capped_at_50_and_write_nothing_without_the_flag(monkeypatch):
    db = FakeDb()
    client = client_for(db, monkeypatch)
    assert client.post("/api/v1/copilot/live/events", json={"call_id": "c", "events": [{"kind": "shown"}] * 51}).status_code == 422
    off = client_for(db, monkeypatch, enabled=False)
    assert off.post("/api/v1/copilot/live/events", json={"call_id": "c", "events": [{"kind": "shown"}]}).status_code == 204
    assert db.inserted == []


def test_a_failed_ui_write_pauses_the_ui_log_only(monkeypatch):
    class Broken(FakeDb):
        def table(self, name):
            raise RuntimeError("relation does not satisfy check")

    monkeypatch.setattr(events, "_ui_paused_until", 0.0)
    monkeypatch.setattr(events, "_brain_paused_until", 0.0)
    events.record_ui(Broken(), events.ui_rows(user_id="u", company_id=None, call_id="c", call_mode=None, sales_motion_key=None, events=[{"kind": "shown"}]))
    assert events._ui_paused_until > 0 and events._brain_paused_until == 0.0


def test_the_points_log_says_what_the_say_view_produced(monkeypatch):
    fake_model(monkeypatch, {"points": [], "closed": [], "next": {"question": "¿Qué CRM usáis?"}})
    db = FakeDb()
    body = {"call_id": "draft-1", "sales_motion_key": "discovery", "turns": CALL, "reason": "responder", "say_view": True}
    client_for(db, monkeypatch).post("/api/v1/copilot/live/points", json=body)
    (row,) = db.inserted
    assert row["detail"]["next"] == "crm" and row["detail"]["say_view"] is True and row["detail"]["deepen"] == 0
    assert json.dumps(row)  # serialisable as written


def test_go_deeper_takes_up_their_words_never_a_generic_pain_question():
    small_talk = turns(("you", "¿Seguimos?"), ("them", "Te pregunto esto porque sé por lo que estás pasando, vale, pues venga, vamos."))
    generic = deepen(quote="sé por lo que estás pasando", say="¿Qué es lo que más te cuesta hoy de cómo registra el equipo las visitas?")
    out = live_points.finalize({"points": [generic]}, reading(call=small_talk, say_view=True), CTX)
    assert out["points"] == [] and out["guards"] == {"deepen_not_their_words": 1}
    assert live_points.shares_their_words("¿Cuántos minutos le lleva ese copia y pega?", "lo copia, lo pega en el cloud")


def test_a_rewrite_never_presumes_what_the_call_does_not_show(monkeypatch):
    seen: dict = {}
    fake_model(monkeypatch, {"answer": None}, seen)
    read(rewrite_req())
    assert "Never presume anything about the prospect or the deal that the CALL does not show" in seen["system"]


def test_responder_that_brings_an_earlier_point_back_has_no_next(monkeypatch):
    existing = [{"id": "pt-x", "kind": "question", "tag_key": "question", "title": "¿Se integra con HubSpot?", "turn_ids": ["t1"], "outcome": "open", "say": "Sí."}]
    fake_model(monkeypatch, {"points": [point(ref="pt-x")], "closed": []})
    result = read(reading(reason="responder", points=existing))[-1]
    assert result["next"] is None and "next_without_question" not in result["guards"]


def test_the_step_question_and_next_never_presume_what_the_call_does_not_show():
    assert "Never presume anything the CALL does not show" in live_points.STEP_SYSTEM
    assert "never presuming what the call does not show" in live_points.NEXT_TEXT
    assert "OUR product, the demo or this call" in live_points.SYSTEM_SAY


def test_responder_with_nothing_pending_asks_about_the_last_thing_they_said(monkeypatch):
    everything = {"done_steps": [s["step_id"] for s in CTX.snapshot["steps"]], "known_data": ["crm", "decide"]}
    seen: dict = {}
    fake_model(monkeypatch, {"points": [], "closed": [], "next": {"question": "¿Y quién es esa directora comercial a la que se lo reenviarías?"}}, seen)
    result = read(reading(reason="responder", progress=everything))[-1]
    assert result["next"]["kind"] == "said" and result["next"]["id"] == "t5"
    assert result["next"]["label"].startswith("Y se lo reenviaré") and result["next"]["question"].startswith("¿Y quién es")
    assert "takes up the LAST" in seen["user"]


def test_a_question_about_what_they_said_must_take_up_their_words(monkeypatch):
    everything = {"done_steps": [s["step_id"] for s in CTX.snapshot["steps"]], "known_data": ["crm", "decide"]}
    fake_model(monkeypatch, {"points": [], "closed": [], "next": {"question": "¿Qué es lo que más te preocupa hoy?"}})
    result = read(reading(reason="responder", progress=everything))[-1]
    assert result["next"] is None and result["guards"] == {"next_not_their_words": 1}
