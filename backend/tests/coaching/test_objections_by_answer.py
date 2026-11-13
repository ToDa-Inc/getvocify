"""Coaching's objections table, grouped by the playbook answer each is for, with what happened right after the reply
(C04 v10) and what colleagues replied when the call moved on (Dani, 2026-11-10)."""

from app.services.coaching import rep_coaching as engine

ENTRIES = [
    {"entry_id": "objection:timing", "category": "timing", "guidance": "Pregunta qué cambiaría y deja fecha."},
    {"entry_id": "objection:custom:es_caro", "category": "custom", "label": "Es caro", "guidance": "¿Respecto a qué?"},
]


def row(objections, *, answers_read=True, memo="m1", user="u1", at="2026-11-09T10:00:00+00:00"):
    return {"memo_id": memo, "user_id": user, "observed_at": at, "is_conversation": True, "answers_read": answers_read,
            "objections": objections}


def obj(answer_id, after, *, category="timing", response="¿Qué cambiaría?", quote="ahora no"):
    return {"kind": "objection", "category": category, "objection_id": answer_id, "resolution": "open", "after": after,
            "after_quote": "déjame mirarlo" if after == "advanced" else None, "quote": quote, "response": response}


def test_each_objection_is_grouped_by_its_answer_and_one_with_none_has_its_own_row():
    rows = [row([obj("timing", "advanced"), obj("es_caro", "ended", category="price"), obj(None, "stalled", category="trust")])]
    table = {item["key"]: item for item in engine.objection_breakdown(rows, ENTRIES)}
    assert set(table) == {"timing", "custom:es_caro", "unanswered"}
    assert table["timing"]["advanced"] == 1 and table["timing"]["how"] == "Pregunta qué cambiaría y deja fecha."
    assert table["custom:es_caro"]["label"] == "Es caro" and table["custom:es_caro"]["ended"] == 1
    assert table["unanswered"]["stalled"] == 1 and table["unanswered"]["occurrences"][0]["quote"] == "ahora no"


def test_an_analysis_from_before_the_answers_keeps_its_category():
    rows = [row([obj(None, None, category="status_quo")], answers_read=False)]
    (item,) = engine.objection_breakdown(rows, ENTRIES)
    assert item["key"] == "status_quo" and item["advanced"] == item["stalled"] == item["ended"] == 0


def test_what_colleagues_said_when_the_call_moved_on_is_shown_for_that_objection_only():
    mine = [row([obj("timing", "ended", response=None)])]
    peers = [
        row([obj("timing", "advanced", response="¿Por qué, qué cambiaría para el año que viene?")], memo="p1", user="u2"),
        row([obj("timing", "ended", response="Vale, te llamo")], memo="p2", user="u2"),  # did not move on: not an example
        row([obj("es_caro", "advanced", category="price", response="¿Respecto a qué?")], memo="p3", user="u3"),  # not mine
    ]
    (item,) = engine.objection_breakdown(mine, ENTRIES, peer_rows=peers)
    assert item["worked"] == [{"quote": "ahora no", "response": "¿Por qué, qué cambiaría para el año que viene?", "after_quote": "déjame mirarlo",
                               "said": None, "response_said": None, "after_said": None}]


def test_once_a_call_has_the_newer_reading_older_calls_are_left_out_instead_of_shown_as_unknown():
    rows = [
        row([obj("timing", "advanced")], memo="new"),
        row([obj(None, None, category="status_quo")], answers_read=False, memo="old"),
    ]
    table = engine.objection_breakdown(rows, ENTRIES)
    assert [item["key"] for item in table] == ["timing"] and table[0]["by_after"] is True


def test_the_group_without_an_answer_is_always_last():
    rows = [row([obj(None, "ended", category="trust"), obj(None, "ended", category="trust"), obj("timing", "advanced")])]
    assert [item["key"] for item in engine.objection_breakdown(rows, ENTRIES)] == ["timing", "unanswered"]
