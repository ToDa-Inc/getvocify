"""A model call: a transcript the Head of Sales marks as a good example. Vocify proposes real examples for the steps and
the situation in which an objection answer worked (as a branch of that answer). Every proposal carries the passage it
comes from; nothing the transcript does not literally contain is kept; nothing is applied without being asked."""

from __future__ import annotations

import asyncio

import pytest

from app.services.playbooks.fill import FillError
from app.services.playbooks.model_calls import (
    MAX_TRANSCRIPT_CHARS,
    apply_proposals,
    propose,
    speaker_warning,
)
from app.services.playbooks.structured import MAX_EXAMPLE, MAX_GUIDANCE
from tests.playbooks.test_structure import FakeLLM

TRANSCRIPT = (
    "Rep: Hola Marcos, soy Dani de Vocify, ¿tienes un minuto?\n"
    "Cliente: Sí, dime.\n"
    "Rep: Te llamo porque vi que trabajáis con equipos comerciales en obra. ¿Cómo apuntáis hoy lo que pasa en cada visita?\n"
    "Cliente: Pues en un Excel, pero es muy caro cambiar de herramienta ahora mismo.\n"
    "Rep: Lo entiendo. Antes de hablar de precio, ¿cuánto tiempo pierde el equipo a la semana apuntando a mano?\n"
    "Cliente: Unas cinco horas, la verdad. Vale, cuéntame más.\n"
)
OPENING = "Hola Marcos, soy Dani de Vocify, ¿tienes un minuto?"
CURRENT = {
    "steps": [
        {"step_id": "apertura", "label": "Apertura", "criterion": "Se presenta y pide un minuto."},
        {"step_id": "dolor", "label": "Descubrir el dolor", "criterion": "Pregunta cómo lo hacen hoy."},
    ],
    "objections": [{"category": "price", "guidance": "Pregunta cuánto les cuesta hoy."}],
    "qualification": [],
}
EXAMPLE = {
    "step_index": 1, "example": OPENING,
    "excerpt": [{"speaker": "rep", "text": OPENING}],
}
BRANCH = {
    "category": "price", "label": None, "when": "dicen que cambiar es caro mientras usan un Excel",
    "answer": "Reconoce la duda y pregunta cuánto tiempo pierden a la semana apuntando a mano antes de hablar de precio.",
    "excerpt": [
        {"speaker": "client", "text": "es muy caro cambiar de herramienta ahora mismo."},
        {"speaker": "rep", "text": "Antes de hablar de precio, ¿cuánto tiempo pierde el equipo a la semana apuntando a mano?"},
    ],
}


def run(llm, transcript=TRANSCRIPT, scope=None, note="", current=CURRENT):
    return asyncio.run(propose(transcript, scope or {"kind": "whole"}, note, current, "es", llm=llm))


def test_a_real_sentence_becomes_the_example_of_the_step_it_belongs_to():
    result = run(FakeLLM({"step_examples": [EXAMPLE], "objection_branches": []}))
    assert result["speaker_warning"] is False
    assert result["proposals"] == [{
        "id": "p1", "kind": "step_example", "step_index": 1, "text": OPENING,
        "excerpt": [{"speaker": "rep", "text": OPENING}],
    }]


def test_an_objection_that_worked_becomes_a_branch_with_the_moment_it_applies_to():
    result = run(FakeLLM({"step_examples": [], "objection_branches": [BRANCH]}))
    [proposal] = result["proposals"]
    assert proposal["kind"] == "objection_branch" and proposal["category"] == "price"
    assert proposal["when"] == BRANCH["when"] and proposal["text"] == BRANCH["answer"]
    assert [e["speaker"] for e in proposal["excerpt"]] == ["client", "rep"]


def test_a_proposal_whose_passage_is_not_in_the_transcript_is_dropped():
    invented = {**EXAMPLE, "excerpt": [{"speaker": "rep", "text": "Os ofrezco un 50% de descuento si firmáis hoy."}]}
    wrong_example = {**EXAMPLE, "example": "Frase que nadie dijo."}
    assert run(FakeLLM({"step_examples": [invented, wrong_example], "objection_branches": []}))["proposals"] == []


def test_a_step_that_does_not_exist_is_dropped_and_ids_are_sequential():
    out_of_range = {**EXAMPLE, "step_index": 9}
    result = run(FakeLLM({"step_examples": [out_of_range, EXAMPLE], "objection_branches": [BRANCH]}))
    assert [p["id"] for p in result["proposals"]] == ["p1", "p2"]
    assert [p["kind"] for p in result["proposals"]] == ["step_example", "objection_branch"]


def test_an_example_is_clipped_to_what_a_step_holds():
    long_line = "Hola " + "Marcos " * 80
    transcript = f"Rep: {long_line}\nCliente: Dime.\n"
    result = run(FakeLLM({"step_examples": [{"step_index": 1, "example": long_line, "excerpt": [{"speaker": "rep", "text": long_line[:60]}]}], "objection_branches": []}), transcript=transcript)
    assert len(result["proposals"][0]["text"]) <= MAX_EXAMPLE


def test_the_chosen_moment_and_the_note_reach_the_model():
    llm = FakeLLM({"step_examples": [], "objection_branches": []})
    run(llm, scope={"kind": "moment", "text": "es muy caro cambiar de herramienta"}, note="Así se rebate el precio")
    user = llm.calls[0]["messages"][1]["content"]
    assert "es muy caro cambiar de herramienta" in user and "Así se rebate el precio" in user and "Descubrir el dolor" in user


def test_a_failing_model_raises_a_fill_error():
    with pytest.raises(FillError):
        run(FakeLLM(RuntimeError("boom")))


def test_empty_and_huge_transcripts_are_refused():
    with pytest.raises(ValueError, match="empty_transcript"):
        run(FakeLLM({}), transcript="   ")
    with pytest.raises(ValueError, match="transcript_too_long"):
        run(FakeLLM({}), transcript="Rep: hola\n" * (MAX_TRANSCRIPT_CHARS // 8))


@pytest.mark.parametrize("text,expected", [
    (TRANSCRIPT, False),
    ("Rep: Hola, ¿qué tal?\nRep: Te llamo por esto.\n", True),
    ("Hola, ¿qué tal? Te llamo por esto sin etiquetas de nadie.", True),
    ("SPEAKER: S1\nHola\nSPEAKER: S2\nDime\n", False),
    ("Tú: Hola\nEllos: Dime\n", False),
])
def test_one_speaker_or_none_means_the_labels_cannot_be_trusted(text, expected):
    assert speaker_warning(text) is expected


def test_applying_sets_the_example_and_appends_the_branch_to_the_answer():
    proposals = [
        {"id": "p1", "kind": "step_example", "step_index": 1, "text": OPENING},
        {"id": "p2", "kind": "objection_branch", "category": "price", "when": "dicen que cambiar es caro", "text": "Pregunta cuánto tiempo pierden."},
    ]
    result = apply_proposals(CURRENT, proposals)
    assert result["applied"] == ["p1", "p2"] and result["skipped"] == []
    assert result["steps"][0]["example"] == OPENING and "example" not in result["steps"][1]
    assert result["objections"][0]["guidance"] == "Pregunta cuánto les cuesta hoy. Si dicen que cambiar es caro: Pregunta cuánto tiempo pierden."


def test_a_branch_for_an_own_objection_that_does_not_exist_creates_it():
    proposal = {"id": "p1", "kind": "objection_branch", "category": "custom", "label": "Tenemos que pasarlo por legal", "when": "no hay contrato tipo", "text": "Ofrece enviar el borrador."}
    result = apply_proposals(CURRENT, [proposal])
    created = result["objections"][-1]
    assert created["category"] == "custom" and created["label"] == "Tenemos que pasarlo por legal"
    assert created["guidance"] == "Si no hay contrato tipo: Ofrece enviar el borrador."


def test_a_branch_that_does_not_fit_leaves_the_answer_as_it_was():
    full = {**CURRENT, "objections": [{"category": "price", "guidance": "x" * (MAX_GUIDANCE - 10)}]}
    result = apply_proposals(full, [{"id": "p1", "kind": "objection_branch", "category": "price", "when": "es caro", "text": "Una respuesta larga que no cabe."}])
    assert result["applied"] == [] and result["skipped"] == [{"id": "p1", "code": "guidance_too_long"}]
    assert result["objections"] == full["objections"]


def test_applying_never_touches_what_it_was_not_asked_about():
    result = apply_proposals(CURRENT, [{"id": "p1", "kind": "step_example", "step_index": 7, "text": "x"}, {"id": "p2", "kind": "nope"}])
    assert result["skipped"] == [{"id": "p1", "code": "step_not_found"}, {"id": "p2", "code": "unsupported"}]
    assert result["steps"] == CURRENT["steps"] and result["objections"] == CURRENT["objections"]
