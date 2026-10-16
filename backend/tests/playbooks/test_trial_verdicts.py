"""What the Head of Sales decides about each case of the trial, and what the trial says at the end. A verdict changes
the draft only through the editor's own limits: an answer that does not fit is refused and the draft stays as it was."""

from __future__ import annotations

import asyncio

import pytest

from app.services.company import Membership
from app.services.playbooks.repository import InMemoryPlaybookRepository
from app.services.playbooks.structure import set_playbook_structure_llm
from app.services.playbooks.structured import MAX_CUSTOM_OBJECTIONS, MAX_GUIDANCE
from app.services.playbooks.trial import activate, add_branch, apply_verdict, similar_phrase, trial_result
from app.services.playbooks.versions import PublishError
from tests.playbooks.test_structure import FakeLLM

CASE = {"id": "c1", "source": "typical", "client_text": "Me parece caro para lo que hacéis.", "motion_key": "discovery"}
EDITOR = {
    "steps": [{"step_id": "apertura", "label": "Apertura", "criterion": "Se presenta."}],
    "objections": [
        {"category": "price", "guidance": "Pregunta cuánto pierden hoy."},
        {"category": "custom", "id": "mandame_un_email", "label": "Mándame un email", "trigger": "Mándame un email", "guidance": "Pide cinco minutos."},
    ],
    "qualification": [],
}


def verdict(editor=EDITOR, entry_id="objection:price", kind="corrected", text="Lo comparamos con lo que pierden al mes.", **extra):
    return apply_verdict(editor, CASE, entry_id, kind, text, **extra)


def test_approving_or_not_knowing_changes_nothing():
    for kind in ("approve", "unknown"):
        result = verdict(kind=kind, text=None)
        assert result["objections"] == EDITOR["objections"] and result["steps"] == EDITOR["steps"]


def test_a_correction_replaces_the_answer_it_was_about_and_nothing_else():
    result = verdict()
    assert result["objections"][0] == {"category": "price", "guidance": "Lo comparamos con lo que pierden al mes."}
    assert result["objections"][1] == EDITOR["objections"][1]
    assert result["entry_id"] == "objection:price"


def test_a_correction_of_an_own_objection_finds_it_by_its_id():
    result = verdict(entry_id="objection:custom:mandame_un_email", text="Dime qué necesitas y te lo mando hoy.")
    assert result["objections"][1]["guidance"] == "Dime qué necesitas y te lo mando hoy."
    assert result["objections"][0] == EDITOR["objections"][0]


def test_a_case_with_no_answer_becomes_an_own_objection_named_after_what_the_customer_said():
    result = verdict(entry_id=None, text="Te lo cuento en cinco minutos.")
    created = result["objections"][-1]
    assert created["category"] == "custom" and created["trigger"] == CASE["client_text"]
    assert created["label"] == "Me parece caro para lo que" and created["guidance"] == "Te lo cuento en cinco minutos."
    assert result["entry_id"] == "objection:custom:me_parece_caro_para_lo_que"


def test_a_fixed_kind_without_an_answer_gets_it():
    result = verdict(EDITOR | {"objections": []}, entry_id="objection:timing", text="¿Lo vemos en dos semanas?")
    assert result["objections"] == [{"category": "timing", "guidance": "¿Lo vemos en dos semanas?"}]


def test_never_say_is_added_to_the_answer_and_needs_an_answer_to_attach_to():
    result = verdict(kind="never_say", text="que es barato")
    assert result["objections"][0]["guidance"] == "Pregunta cuánto pierden hoy. No digas: que es barato."
    with pytest.raises(ValueError, match="no_answer_to_attach"):
        verdict(entry_id=None, kind="never_say", text="que es barato")


def test_a_branch_is_added_to_the_answer_with_the_situation_that_calls_for_it():
    result = verdict(kind="branch", text="Enseña el ahorro de horas.", when="lo comparan con una herramienta gratuita")
    assert result["objections"][0]["guidance"] == "Pregunta cuánto pierden hoy. Si lo comparan con una herramienta gratuita: Enseña el ahorro de horas."


def test_a_branch_that_does_not_fit_can_be_kept_as_an_own_objection_named_after_the_situation():
    result = verdict(kind="own", text="Enseña el ahorro de horas.", when="Ya tenemos una herramienta gratuita que cubre eso.")
    created = result["objections"][-1]
    assert created["category"] == "custom" and created["trigger"] == "Ya tenemos una herramienta gratuita que cubre eso."
    assert created["label"] == "Ya tenemos una herramienta gratuita que" and created["guidance"] == "Enseña el ahorro de horas."
    assert result["objections"][0] == EDITOR["objections"][0]
    assert result["entry_id"] == "objection:custom:ya_tenemos_una_herramienta_gratuita_que"
    with pytest.raises(ValueError, match="guidance_too_long"):
        verdict(kind="own", text="x" * (MAX_GUIDANCE + 1), when="Otra situación distinta de las demás")


def test_an_answer_that_does_not_fit_is_refused_and_the_draft_is_untouched():
    with pytest.raises(ValueError, match="guidance_too_long"):
        verdict(text="x" * (MAX_GUIDANCE + 1))
    long_editor = EDITOR | {"objections": [{"category": "price", "guidance": "y" * (MAX_GUIDANCE - 5)}]}
    with pytest.raises(ValueError, match="guidance_too_long"):
        verdict(long_editor, kind="branch", text="No cabe en lo que queda.", when="es caro")
    with pytest.raises(ValueError, match="guidance_too_long"):
        add_branch("y" * (MAX_GUIDANCE - 5), "es caro", "No cabe en lo que queda.")
    assert EDITOR["objections"][0]["guidance"] == "Pregunta cuánto pierden hoy."


def test_a_correction_needs_words_and_an_own_objection_needs_room():
    with pytest.raises(ValueError, match="text_required"):
        verdict(text="   ")
    full = EDITOR | {"objections": [{"category": "custom", "id": f"o{i}", "label": f"Objeción {i}", "trigger": "", "guidance": "x"} for i in range(MAX_CUSTOM_OBJECTIONS)]}
    with pytest.raises(ValueError, match="too_many_custom_objections"):
        verdict(full, entry_id=None, text="Respuesta nueva.")


def test_the_result_counts_what_was_approved_and_names_the_weak_topics():
    decided = [{"verdict": "approve", "topic": "price"}] * 9 + [{"verdict": "corrected", "topic": "security"}, {"verdict": "unknown", "topic": "security"}, {"verdict": "never_say", "topic": "price"}]
    result = trial_result(decided)
    assert result == {"approved": 9, "total": 12, "percent": 75, "weak_topics": ["security", "price"], "warn": True, "can_activate": True}


def test_with_fewer_than_three_cases_there_is_no_percentage_and_never_a_warning():
    result = trial_result([{"verdict": "approve", "topic": "price"}, {"verdict": "corrected", "topic": "price"}])
    assert result["percent"] is None and result["warn"] is False and result["approved"] == 1 and result["total"] == 2
    assert trial_result([])["percent"] is None


def test_eighty_percent_or_more_has_no_warning():
    assert trial_result([{"verdict": "approve", "topic": "x"}] * 4 + [{"verdict": "corrected", "topic": "x"}])["warn"] is False


def test_a_similar_phrase_is_one_different_thing_the_customer_could_say():
    llm = FakeLLM({"phrase": "Ya tenemos una herramienta gratuita que cubre eso."})
    assert asyncio.run(similar_phrase(CASE, "es", llm=llm)) == "Ya tenemos una herramienta gratuita que cubre eso."
    assert asyncio.run(similar_phrase(CASE, "es", llm=FakeLLM(RuntimeError("boom")))) == ""
    assert asyncio.run(similar_phrase(CASE, "es", llm=FakeLLM({"phrase": CASE["client_text"]}))) == ""


# --- activating ----------------------------------------------------------------------------------------------

MEMBER = Membership(id="m", company_id="co-1", user_id="u-1", role="owner", status="active", sales_role=None)


def test_activating_publishes_the_drafts_that_have_one_and_reports_the_ones_that_cannot():
    repo = InMemoryPlaybookRepository()
    repo.save_draft("co-1", "discovery", [{"step_id": "apertura", "label": "Apertura", "criterion": "Se presenta."}], [])
    outcome = activate(repo, MEMBER, ["discovery", "closing"])
    assert outcome["published"] == ["discovery"]
    assert outcome["failed"] == [{"key": "closing", "code": "not_a_draft"}]
    assert repo.list_types("co-1")["discovery"]["status"] == "published"
