"""What happened to each live-help suggestion: did the rep say it, did it settle the objection or doubt. The "resolved"
half comes from what the post-call reading already decided for the same objection; only "did they use it" (and
questions, which that reading does not cover) go to a judge. Unknown is a verdict, never a success."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.services.playbooks.outcomes import (
    match_objection,
    judge_question,
    judge_use,
    MIN_AGE_HOURS,
    outcome_for_event,
    ready_for_judging,
    score_labels,
    success_stats,
    transcript_window,
)
from tests.playbooks.test_structure import FakeLLM

TURN = "Es muy caro para nosotros, la verdad"
SUGGESTION = "Pregunta cuánto tiempo pierden hoy."
OBJECTION = {"kind": "objection", "category": "price", "quote": "Es muy caro para nosotros", "response": "Entiendo, ¿cuánto tiempo pierde hoy el equipo apuntando a mano?", "resolution": "resolved", "objection_id": None}


def event(turn=TURN, kind="price", **extra):
    return {
        "id": "e1", "created_at": "2026-10-10T10:00:00+00:00", "capture_id": "m1", "sales_motion_key": "discovery",
        "latest_turn": turn, "objection_type": kind, "entry_id": None, "source_id": "objection:price", "say_this": SUGGESTION, "is_objection": True, **extra,
    }


def memo(objections=(OBJECTION,), transcript="Them: Es muy caro para nosotros, la verdad\nYou: Entiendo, ¿cuánto tiempo pierde hoy el equipo?\nThem: Unas cinco horas. Vale, sigue."):
    return {"id": "m1", "transcript": transcript, "extraction": {"intelligence": {"objections": list(objections)}}}


def run(coro):
    return asyncio.run(coro)


# --- matching -------------------------------------------------------------------------------------------------


def test_a_suggestion_is_matched_to_the_objection_the_post_call_reading_found():
    assert match_objection(event(), [OBJECTION]) is OBJECTION


def test_a_different_kind_of_objection_or_a_different_phrase_is_not_a_match():
    other = {**OBJECTION, "category": "timing"}
    far = {**OBJECTION, "quote": "No es buen momento, llamadme en otoño"}
    assert match_objection(event(), [other]) is None
    assert match_objection(event(), [far]) is None
    assert match_objection(event(), []) is None


def test_a_question_or_an_own_objection_is_matched_by_its_words_alone():
    own = {**OBJECTION, "category": "other"}
    assert match_objection(event(kind="question"), [own]) is own
    assert match_objection(event(kind=None), [own]) is own


def test_the_best_of_several_wins():
    near = {**OBJECTION, "quote": "Es muy caro para nosotros, la verdad", "response": "mejor"}
    assert match_objection(event(), [OBJECTION, near]) is near


# --- the judges -----------------------------------------------------------------------------------------------


def test_a_rep_who_said_nothing_did_not_use_it_and_no_model_is_asked():
    llm = FakeLLM({"used": "used"})
    assert run(judge_use(SUGGESTION, None, llm=llm)) == "not_used"
    assert run(judge_use(SUGGESTION, "  ", llm=llm)) == "not_used"
    assert llm.calls == []


def test_use_is_judged_by_meaning_and_an_unreadable_answer_is_unknown():
    assert run(judge_use(SUGGESTION, "¿Cuánto tiempo pierden?", llm=FakeLLM({"used": "adapted"}))) == "adapted"
    assert run(judge_use(SUGGESTION, "Otra cosa", llm=FakeLLM({"used": "maybe"}))) == "unknown"
    assert run(judge_use(SUGGESTION, "Otra cosa", llm=FakeLLM(RuntimeError("boom")))) == "unknown"
    llm = FakeLLM({"used": "used"})
    run(judge_use(SUGGESTION, "¿Cuánto tiempo pierden?", llm=llm))
    assert "meaning" in llm.calls[0]["messages"][0]["content"] and llm.calls[0]["model"]


def test_a_question_is_judged_on_the_transcript_and_the_reps_words_must_be_in_it():
    window = "You: Os lo confirmo y os paso el detalle.\nThem: Perfecto, gracias."
    good = FakeLLM({"used": "used", "resolved": "resolved", "rep_said": "Os lo confirmo y os paso el detalle."})
    assert run(judge_question(window, "¿Se integra con Salesforce?", "Os lo confirmo.", llm=good)) == {"used": "used", "resolved": "resolved", "rep_said": "Os lo confirmo y os paso el detalle."}
    invented = FakeLLM({"used": "used", "resolved": "resolved", "rep_said": "Texto que nadie dijo."})
    assert run(judge_question(window, "x", "y", llm=invented))["rep_said"] is None
    bad = FakeLLM({"used": "nope", "resolved": "resolved"})
    assert run(judge_question(window, "x", "y", llm=bad)) == {"used": "unknown", "resolved": "unknown", "rep_said": None}
    assert run(judge_question(window, "x", "y", llm=FakeLLM(RuntimeError("boom"))))["used"] == "unknown"


def test_resolved_only_counts_when_the_line_was_used_or_adapted():
    llm = FakeLLM({"used": "not_used", "resolved": "resolved", "rep_said": None})
    assert run(judge_question("You: otra cosa", "x", "y", llm=llm))["resolved"] == "unknown"


# --- one event ------------------------------------------------------------------------------------------------


def test_the_resolution_comes_from_the_post_call_reading_and_the_reps_words_from_its_response():
    result = run(outcome_for_event(event(), memo(), llm=FakeLLM({"used": "used"})))
    assert result["used"] == "used" and result["resolved"] == "resolved" and result["resolved_by"] == "extraction"
    assert result["rep_text"] == OBJECTION["response"]
    assert result["event_id"] == "e1" and result["capture_id"] == "m1" and result["sales_motion_key"] == "discovery"
    assert result["client_text"] == TURN and result["suggestion_text"] == SUGGESTION and result["observed_at"] == "2026-10-10T10:00:00+00:00"
    assert result["source_id"] == "objection:price" and result["objection_type"] == "price"


@pytest.mark.parametrize("resolution,expected", [("open", "not_resolved"), ("unknown", "unknown"), (None, "unknown")])
def test_an_open_or_unclear_objection_is_not_resolved_or_unknown(resolution, expected):
    result = run(outcome_for_event(event(), memo([{**OBJECTION, "resolution": resolution}]), llm=FakeLLM({"used": "adapted"})))
    assert result["resolved"] == expected


def test_an_objection_the_rep_never_answered_means_the_suggestion_was_not_used():
    result = run(outcome_for_event(event(), memo([{**OBJECTION, "response": None, "resolution": "open"}]), llm=FakeLLM({"used": "used"})))
    assert result["used"] == "not_used" and result["rep_text"] is None


def test_a_question_goes_to_the_judge_with_the_transcript_from_that_moment():
    llm = FakeLLM({"used": "adapted", "resolved": "resolved", "rep_said": "Entiendo, ¿cuánto tiempo pierde hoy el equipo?"})
    result = run(outcome_for_event(event(kind="question"), memo(objections=[]), llm=llm))
    assert (result["used"], result["resolved"], result["resolved_by"]) == ("adapted", "resolved", "judge")
    assert result["rep_text"] == "Entiendo, ¿cuánto tiempo pierde hoy el equipo?"
    assert "Unas cinco horas" in llm.calls[0]["messages"][1]["content"]


def test_without_a_call_or_without_the_moment_in_it_nothing_is_guessed_and_no_model_is_asked():
    llm = FakeLLM({"used": "used", "resolved": "resolved"})
    gone = run(outcome_for_event(event(), None, llm=llm))
    lost = run(outcome_for_event(event(turn="Algo que no está en la transcripción de la llamada", kind="question"), memo(objections=[]), llm=llm))
    for result in (gone, lost):
        assert (result["used"], result["resolved"]) == ("unknown", "unknown") and result["resolved_by"] == "judge"
    assert llm.calls == []


def test_the_window_starts_at_what_the_prospect_said():
    text = "You: Hola\nThem: Es muy caro para nosotros, la verdad\nYou: Entiendo.\nThem: Vale."
    assert transcript_window(text, "Es muy caro para nosotros", chars=500).startswith("Them: Es muy caro")
    assert transcript_window(text, "algo distinto que no aparece", chars=500) is None


# --- later and apart: only what is already closed and processed -----------------------------------------------


NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)


def aged(hours):
    return event(created_at=(NOW - timedelta(hours=hours)).isoformat())


def test_a_card_is_judged_only_hours_after_the_call_and_once_its_post_call_reading_exists():
    assert MIN_AGE_HOURS >= 1
    assert ready_for_judging(aged(MIN_AGE_HOURS + 1), memo(), now=NOW) is True
    assert ready_for_judging(aged(1), memo(), now=NOW) is False  # the call may still be going, or still being processed
    assert ready_for_judging(aged(MIN_AGE_HOURS + 1), None, now=NOW) is False
    assert ready_for_judging(aged(MIN_AGE_HOURS + 1), {"id": "m1", "transcript": "x"}, now=NOW) is False
    assert ready_for_judging(aged(MIN_AGE_HOURS + 1), {"id": "m1", "extraction": {}}, now=NOW) is False
    assert ready_for_judging(event(created_at="no es una fecha"), memo(), now=NOW) is False
    assert ready_for_judging({**aged(10), "capture_id": None}, memo(), now=NOW) is False


# --- the numbers ----------------------------------------------------------------------------------------------


def rows(*pairs):
    return [{"used": used, "resolved": resolved} for used, resolved in pairs]


def test_the_success_rate_is_resolved_over_the_times_it_was_used_with_a_clear_verdict():
    stats = success_stats(rows(("used", "resolved"), ("adapted", "resolved"), ("used", "resolved"), ("used", "not_resolved")))
    assert stats["rate"] == 0.75 and stats["resolved"] == 3 and stats["clear"] == 4 and stats["unknown"] == 0


def test_unknown_never_counts_as_success_and_is_not_in_the_denominator():
    stats = success_stats(rows(("used", "resolved"), ("used", "resolved"), ("used", "resolved"), ("used", "unknown"), ("not_used", "unknown"), ("unknown", "unknown")))
    assert stats["rate"] == 1.0 and stats["clear"] == 3 and stats["unknown"] == 1 and stats["used"] == 4


def test_below_three_clear_cases_there_is_no_rate_only_counts():
    stats = success_stats(rows(("used", "resolved"), ("used", "not_resolved")))
    assert stats["rate"] is None and stats["resolved"] == 1 and stats["clear"] == 2
    assert success_stats([])["rate"] is None and success_stats([])["sample"] == 0


def test_the_use_rate_is_how_often_it_was_used_among_the_clear_verdicts():
    stats = success_stats(rows(("used", "resolved"), ("not_used", "unknown"), ("not_used", "unknown"), ("adapted", "not_resolved"), ("unknown", "unknown")))
    assert stats["use_rate"] == 0.5 and stats["judged"] == 4
    assert success_stats(rows(("used", "resolved"), ("not_used", "unknown")))["use_rate"] is None


# --- the feasibility check against labelled calls --------------------------------------------------------------


def test_the_check_goes_on_when_the_verdicts_agree_with_the_labels_and_few_are_unknown():
    labelled = [{"used": "used", "resolved": "resolved", "label_used": "used", "label_resolved": "resolved"}] * 9 + [{"used": "unknown", "resolved": "unknown", "label_used": "used", "label_resolved": "resolved"}]
    result = score_labels(labelled)
    assert result["agreement"] == 0.9 and result["unknown_rate"] == 0.1 and result["decision"] == "SIGUE" and result["n"] == 10


def test_it_stops_when_they_disagree_or_too_many_are_unknown():
    disagree = [{"used": "used", "resolved": "resolved", "label_used": "not_used", "label_resolved": "unknown"}] * 5 + [{"used": "used", "resolved": "resolved", "label_used": "used", "label_resolved": "resolved"}] * 5
    assert score_labels(disagree)["decision"] == "DETENER"
    unknowns = [{"used": "unknown", "resolved": "unknown", "label_used": "used", "label_resolved": "resolved"}] * 4 + [{"used": "used", "resolved": "resolved", "label_used": "used", "label_resolved": "resolved"}] * 6
    result = score_labels(unknowns)
    assert result["unknown_rate"] == 0.4 and result["decision"] == "DETENER"


def test_rows_without_a_label_are_left_out_and_no_labels_is_no_decision():
    assert score_labels([{"used": "used", "resolved": "resolved", "label_used": "", "label_resolved": ""}])["decision"] == "SIN ETIQUETAS"
    assert score_labels([])["n"] == 0
