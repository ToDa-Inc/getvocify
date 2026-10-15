"""One call's objections for Coaching's record of calls, even when no step could be judged in it."""

from app.services.coaching import rep_coaching as engine

ENTRIES = [
    {"category": "price", "entry_id": "e1", "guidance": "Antes de hablar de números, mide el coste de hoy."},
    {"category": "custom", "entry_id": "objection:custom:excel", "label": "Seguimos con Excel", "guidance": "Pregunta cuánto tarda."},
]


def _row(objections, conversation=True):
    return {"is_conversation": conversation, "steps": [], "objections": objections}


def test_lists_objections_with_the_key_the_playbook_answers_them_by():
    row = _row([
        {"kind": "objection", "category": "price", "resolution": "open", "quote": "carísimo", "response": None},
        {"kind": "objection", "category": "custom", "objection_id": "excel", "resolution": "resolved", "quote": "con Excel", "response": "¿Cuánto tarda?"},
        {"kind": "obstacle", "category": "timing", "resolution": "open", "quote": "voy conduciendo", "response": None},
    ])
    out = engine.call_objections(row, ENTRIES)
    assert [o["key"] for o in out] == ["price", "custom:excel"]
    assert out[0]["how"].startswith("Antes de hablar") and out[1]["label"] == "Seguimos con Excel"
    assert out[0]["resolution"] == "open" and out[1]["resolution"] == "resolved"


def test_a_non_conversation_has_none():
    assert engine.call_objections(_row([{"kind": "objection", "category": "price"}], conversation=False), ENTRIES) == []


def _step_row(memo_id, at, state, quote="cita"):
    return {
        "memo_id": memo_id, "observed_at": at, "is_conversation": True,
        "steps": [{"step_id": "s1", "label": "Abrir", "criterion": "Cita algo", "state": state, "quote": quote, "reason": "motivo", "advice": None}],
    }


def test_slipped_steps_list_the_calls_it_went_well_in_only_when_asked():
    steps = [{"step_id": "s1", "label": "Abrir", "criterion": "Cita algo"}]
    rows = [_step_row("m1", "2026-10-14T10:00:00+00:00", "missing"), _step_row("m2", "2026-10-13T10:00:00+00:00", "done"), _step_row("m3", "2026-10-12T10:00:00+00:00", "done")]
    slips_only = engine.slipped_steps(rows, steps)[0]["occurrences"]
    with_done = engine.slipped_steps(rows, steps, include_done=True)[0]["occurrences"]
    assert [o["state"] for o in slips_only] == ["missing"]
    assert [o["state"] for o in with_done] == ["missing", "done", "done"]
