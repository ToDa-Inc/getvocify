"""Product questions in a document: a question a prospect could ask, with the answer the document gives, becomes
one of the team's own objections (category custom). Nothing the document does not literally say is kept."""

from __future__ import annotations

import asyncio

from app.services.playbooks import structure
from app.services.playbooks.questions import add_questions, extract_questions
from app.services.playbooks.structured import MAX_CUSTOM_OBJECTIONS, normalize_objections
from tests.playbooks.test_structure import FakeLLM

SOURCE = (
    "Preguntas frecuentes. ¿Se integra con Salesforce? Sí, con Salesforce y HubSpot mediante la integración nativa. "
    "¿Dónde se guardan los datos? En servidores de la UE, en Frankfurt."
)
SALESFORCE = {
    "label": "Integración con Salesforce",
    "trigger": "¿Se integra con Salesforce?",
    "answer": "Sí, con Salesforce y HubSpot mediante la integración nativa.",
    "quote": "Sí, con Salesforce y HubSpot mediante la integración nativa.",
}
DATA = {
    "label": "Dónde se guardan los datos",
    "trigger": "¿Dónde se guardan nuestros datos?",
    "answer": "En servidores de la UE, en Frankfurt.",
    "quote": "En servidores de la UE, en Frankfurt.",
}


def extract(llm, text=SOURCE, lang="es"):
    return asyncio.run(extract_questions(text, lang, llm=llm))


def test_a_question_with_a_literal_quote_becomes_a_custom_entry():
    entries = extract(FakeLLM({"questions": [SALESFORCE]}))
    assert entries == [{
        "category": "custom",
        "label": "Integración con Salesforce",
        "trigger": "¿Se integra con Salesforce?",
        "guidance": "Sí, con Salesforce y HubSpot mediante la integración nativa.",
    }]


def test_a_question_whose_quote_the_document_does_not_contain_is_dropped():
    invented = {**SALESFORCE, "quote": "Sí, con SAP y Oracle mediante conectores certificados."}
    assert extract(FakeLLM({"questions": [invented, DATA]})) == [
        {
            "category": "custom",
            "label": "Dónde se guardan los datos",
            "trigger": "¿Dónde se guardan nuestros datos?",
            "guidance": "En servidores de la UE, en Frankfurt.",
        }
    ]


def test_a_question_without_an_answer_or_a_label_is_dropped():
    assert extract(FakeLLM({"questions": [{**SALESFORCE, "answer": ""}, {**DATA, "label": ""}]})) == []


def test_texts_are_clipped_to_what_the_editor_saves():
    long_source = "Pregunta. " + ("Cabe todo lo que hace falta saber. " * 40)
    quote = "Cabe todo lo que hace falta saber."
    entry = extract(
        FakeLLM({"questions": [{"label": "L" * 90, "trigger": "T" * 300, "answer": "A" * 1500, "quote": quote}]}),
        text=long_source,
    )[0]
    assert len(entry["label"]) <= 60 and len(entry["trigger"]) <= 200 and len(entry["guidance"]) <= 1200
    normalize_objections([entry])  # it saves


def test_two_questions_with_the_same_label_keep_the_first():
    again = {**DATA, "label": "integración con salesforce"}
    assert [e["label"] for e in extract(FakeLLM({"questions": [SALESFORCE, again]}))] == ["Integración con Salesforce"]


def test_more_than_the_limit_keeps_the_limit():
    text = SOURCE + " " + " ".join(f"Dato número {i} es cierto." for i in range(MAX_CUSTOM_OBJECTIONS + 5))
    questions = [
        {"label": f"Pregunta {i}", "trigger": f"¿Dato {i}?", "answer": f"Dato número {i} es cierto.", "quote": f"Dato número {i} es cierto."}
        for i in range(MAX_CUSTOM_OBJECTIONS + 5)
    ]
    assert len(extract(FakeLLM({"questions": questions}), text=text)) == MAX_CUSTOM_OBJECTIONS


def test_a_failing_or_unusable_model_gives_nothing_and_never_raises():
    assert extract(FakeLLM(RuntimeError("boom"))) == []
    assert extract(FakeLLM("not an object")) == []
    assert extract(FakeLLM({"questions": "nope"})) == []
    assert extract(FakeLLM({"questions": [SALESFORCE]}), text="   ") == []


def test_added_questions_keep_the_existing_objections_and_never_overwrite_a_custom_one():
    existing = [
        {"category": "price", "guidance": "Lo comparamos con lo que pierden al mes."},
        {"category": "custom", "label": "Integración con Salesforce", "trigger": "x", "guidance": "Respuesta del jefe."},
    ]
    new = [
        {"category": "custom", "label": "integración con salesforce", "trigger": "y", "guidance": "Otra."},
        {"category": "custom", "label": "Dónde se guardan los datos", "trigger": "z", "guidance": "En la UE."},
    ]
    merged = add_questions(existing, new)
    assert [e.get("label") or e["category"] for e in merged] == ["price", "Integración con Salesforce", "Dónde se guardan los datos"]
    assert merged[1]["guidance"] == "Respuesta del jefe."


def test_added_questions_stop_at_the_custom_limit():
    existing = [{"category": "custom", "label": f"Ya {i}", "trigger": "", "guidance": "x"} for i in range(MAX_CUSTOM_OBJECTIONS)]
    assert len(add_questions(existing, [{"category": "custom", "label": "Una más", "trigger": "", "guidance": "y"}])) == MAX_CUSTOM_OBJECTIONS


def test_the_branches_prompt_is_opt_in_and_the_default_split_prompt_is_untouched():
    assert structure.SPLIT_PROMPT_VERSION == "playbook_split_v2"
    assert "branches" not in structure._split_prompt()
    with_branches = structure._split_prompt(structure.SPLIT_PROMPT_BRANCHES_VERSION)
    assert "branches" in with_branches and "Si " in with_branches and "1200" in with_branches


def test_split_source_sends_the_branches_prompt_only_when_asked():
    candidates = [{"key": "discovery", "label": "Discovery", "description": "cold call"}]
    for branches, expected in ((False, False), (True, True)):
        llm = FakeLLM({"types": []})
        asyncio.run(structure.split_source("Texto de ejemplo con suficiente contenido para repartir.", candidates, "es", llm=llm, branches=branches))
        assert ("branches" in llm.calls[0]["messages"][0]["content"]) is expected
