"""The trial's cases: what a customer might say, never an answer. Real phrases first (what prospects really said in the
last weeks), then ones the company's own material suggests, then the usual objections, always between 10 and 12."""

from __future__ import annotations

import asyncio

from app.services.playbooks.trial import MAX_CASES, MIN_CASES, TYPICAL_OBJECTIONS, build_cases
from tests.playbooks.test_structure import FakeLLM


def make(events=(), texts=(), llm=None, lang="es", limit=MAX_CASES):
    return asyncio.run(build_cases(events=list(events), source_texts=list(texts), entries=[], lang=lang, motion_key="discovery", limit=limit, llm=llm))


def real(turn, n=1, objection=True):
    return [{"id": f"e-{turn[:5]}-{i}", "latest_turn": turn, "is_objection": objection, "source_id": None, "sales_motion_key": "discovery"} for i in range(n)]


def test_a_company_with_nothing_gets_the_usual_objections():
    cases = make()
    assert MIN_CASES <= len(cases) <= MAX_CASES
    assert {c["source"] for c in cases} == {"typical"}
    assert len({c["id"] for c in cases}) == len(cases)
    assert all(set(c) == {"id", "source", "client_text", "motion_key"} and c["motion_key"] == "discovery" for c in cases)
    assert cases[0]["client_text"] == TYPICAL_OBJECTIONS["es"][0][1]


def test_what_prospects_really_said_comes_first_most_repeated_first_and_at_most_eight():
    events = real("¿Y si no nos gusta cómo cancelamos el servicio?", 3) + real("Es muy caro para un equipo de cuatro comerciales") + sum((real(f"Pregunta real número {i} de un cliente") for i in range(12)), [])
    cases = make(events)
    reals = [c for c in cases if c["source"] == "real"]
    assert len(reals) == 8
    assert reals[0]["client_text"] == "¿Y si no nos gusta cómo cancelamos el servicio?"
    assert [c["source"] for c in cases[:8]] == ["real"] * 8


def test_short_repeated_or_non_objection_phrases_are_not_cases():
    events = real("Hola") + real("Sí, claro, me parece bien todo lo que cuentas", objection=False) + real("¿Tenéis app para el móvil de los comerciales?", 2)
    reals = [c["client_text"] for c in make(events) if c["source"] == "real"]
    assert reals == ["¿Tenéis app para el móvil de los comerciales?"]


def test_the_companys_own_material_adds_phrases_a_customer_could_say():
    llm = FakeLLM({"phrases": ["¿Dónde se guardan nuestros datos?", "¿Qué pasa si superamos los usuarios del plan?"]})
    cases = make(real("¿Tenéis app para el móvil de los comerciales?"), texts=["Servidores en la UE. Plan Pro hasta 20 usuarios."], llm=llm)
    docs = [c["client_text"] for c in cases if c["source"] == "document"]
    assert docs == ["¿Dónde se guardan nuestros datos?", "¿Qué pasa si superamos los usuarios del plan?"]
    assert MIN_CASES <= len(cases) <= MAX_CASES
    assert "Never write the answer" in llm.calls[0]["messages"][0]["content"]


def test_a_failing_model_never_breaks_the_trial_it_is_completed_with_the_usual_ones():
    cases = make(texts=["Algo de material"], llm=FakeLLM(RuntimeError("boom")))
    assert len(cases) >= MIN_CASES and {c["source"] for c in cases} == {"typical"}


def test_the_same_phrase_is_never_twice():
    llm = FakeLLM({"phrases": ["¿Se integra con nuestro CRM?", "¿Se integra con nuestro CRM?"]})
    texts = [c["client_text"].casefold() for c in make(texts=["x"], llm=llm)]
    assert len(texts) == len(set(texts))


def test_an_english_company_gets_english_phrases():
    cases = make(lang="en")
    assert cases[0]["client_text"] == TYPICAL_OBJECTIONS["en"][0][1]


def test_the_limit_is_respected():
    assert len(make(limit=4)) == 4
