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
