"""Objections with no answer, from calls read after they ended and from live help, grouped by meaning into one question
each for the Head of Sales, with a colleague's reply that moved the call forward as a draft (Dani, 2026-11-10)."""

import asyncio

from app.services.playbooks.call_gaps import from_calls, unanswered_gaps


def call(objections, *, read=True, motion="discovery", at="2026-11-09T10:00:00+00:00"):
    return {"is_conversation": True, "answers_read": read, "motion": motion, "observed_at": at, "objections": objections}


def obj(quote, *, answer=None, after=None, response="Entiendo, ¿respecto a qué?"):
    return {"kind": "objection", "objection_id": answer, "quote": quote, "after": after, "response": response}


class Groups:
    def __init__(self, groups):
        self.groups, self.messages = groups, None

    def chat_json(self, messages, **_):
        self.messages = messages
        return {"groups": self.groups}


class Broken:
    def chat_json(self, messages, **_):
        raise RuntimeError("provider down")


def run(**kwargs):
    kwargs.setdefault("events", [])
    kwargs.setdefault("entries", [])
    return asyncio.run(unanswered_gaps(lang="es", **kwargs))


def test_only_objections_with_no_answer_in_calls_read_against_every_answer_count():
    rows = [
        call([obj("Es caro para nosotros"), obj("Ahora no es el momento", answer="timing"), obj("no")]),
        call([obj("Ya tenemos proveedor")], read=False),
    ]
    assert [p["text"] for p in from_calls(rows)] == ["Es caro para nosotros"]


def test_phrases_with_one_meaning_become_one_question_with_how_many_said_it():
    rows = [call([obj("Es caro para nosotros"), obj("Se nos va de precio")]), call([obj("Ya tenemos proveedor")])]
    llm = Groups([{"items": [0, 1], "example": 0}, {"items": [2], "example": 2}])
    gaps = run(call_rows=rows, llm=llm)
    assert [(g.seen, g.example) for g in gaps] == [(2, "Es caro para nosotros"), (1, "Ya tenemos proveedor")]
    assert gaps[0].question == "Un cliente dijo «Es caro para nosotros» ¿Qué respondéis?" and gaps[0].kind == "real"


def test_a_reply_after_which_the_call_moved_forward_is_the_draft_and_one_that_did_not_is_not():
    rows = [call([obj("Es caro para nosotros", after="advanced", response="¿Caro respecto a qué?"),
                  obj("Se nos va de precio", after="ended", response="Vale, lo dejamos")])]
    (gap,) = run(call_rows=rows, llm=Groups([{"items": [0, 1], "example": 1}]))
    assert gap.draft == "¿Caro respecto a qué?"


def test_live_help_phrases_join_the_same_groups():
    events = [{"latest_turn": "Nos sale caro ahora mismo", "is_objection": True, "source_id": None, "created_at": "2026-11-08"}]
    rows = [call([obj("Es caro para nosotros")])]
    (gap,) = run(call_rows=rows, events=events, llm=Groups([{"items": [0, 1], "example": 0}]))
    assert gap.seen == 2


def test_the_company_answers_go_to_the_model_so_it_leaves_covered_ones_out():
    llm = Groups([])
    entries = [{"label": "Es caro", "trigger": "cuando dicen que es caro", "guidance": "¿Respecto a qué?"}]
    assert run(call_rows=[call([obj("Es caro para nosotros")])], entries=entries, llm=llm) == []
    assert "Es caro: cuando dicen que es caro" in llm.messages[-1]["content"]


def test_when_the_model_fails_live_help_is_grouped_by_first_words_as_before():
    events = [{"latest_turn": "¿Se integra con Salesforce?", "is_objection": True, "source_id": None}]
    (gap,) = run(call_rows=[call([obj("Es caro para nosotros")])], events=events, llm=Broken())
    assert gap.example == "¿Se integra con Salesforce?"


def test_a_number_the_model_repeats_or_invents_is_ignored():
    rows = [call([obj("Es caro para nosotros"), obj("Ya tenemos proveedor")])]
    gaps = run(call_rows=rows, llm=Groups([{"items": [0, 7], "example": 7}, {"items": [0, 1], "example": 0}]))
    assert [(g.seen, g.example) for g in gaps] == [(1, "Es caro para nosotros"), (1, "Ya tenemos proveedor")]
