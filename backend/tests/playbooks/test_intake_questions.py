"""The company intake with the playbook assistant on: the product questions a document answers are saved as the
team's own objections, and the objection answers may carry branches. With the assistant off nothing changes."""

from __future__ import annotations

import pytest

from app.config import settings
from app.services import feature_flags
from app.services.playbooks.structure import set_playbook_structure_llm
from tests.playbooks.test_company_intake import MIXED, MIXED_ANSWER, _client, _post
from tests.playbooks.test_structure import FakeLLM

FAQ = "¿Se integra con Salesforce? Sí, con Salesforce y HubSpot mediante la integración nativa."
QUESTION = {
    "label": "Integración con Salesforce",
    "trigger": "¿Se integra con Salesforce?",
    "answer": "Sí, con Salesforce y HubSpot mediante la integración nativa.",
    "quote": "Sí, con Salesforce y HubSpot mediante la integración nativa.",
}
SALESFORCE = {
    "category": "custom", "id": "integracion_con_salesforce", "label": "Integración con Salesforce",
    "trigger": "¿Se integra con Salesforce?", "guidance": "Sí, con Salesforce y HubSpot mediante la integración nativa.",
}
NO_PROCESS = {"types": [], "company": {}}


@pytest.fixture
def assistant_on(monkeypatch):
    monkeypatch.setattr(settings, "PLAYBOOK_ASSISTANT_ENABLED", True)
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()


def _customs(editor):
    return [o for o in editor["objections"] if o["category"] == "custom"]


def test_questions_join_the_first_detected_call_type(assistant_on):
    llm = FakeLLM(MIXED_ANSWER, {"questions": [QUESTION]})
    set_playbook_structure_llm(llm)
    body = _post(_client(), payload=f"{MIXED}\n{FAQ}").json()
    discovery, closing = body["types"]
    assert _customs(discovery["editor"]) == [SALESFORCE]
    assert _customs(closing["editor"]) == []
    assert len(llm.calls) == 2
    assert "branches" in llm.calls[0]["messages"][0]["content"]


def test_a_product_sheet_goes_into_the_playbook_that_already_has_content(assistant_on):
    client = _client()
    client.store.save_draft(
        "co-1", "closing",
        [{"step_id": "demo", "label": "Demo", "criterion": "Enseña lo que resuelve su problema."}],
        [{"category": "price", "guidance": "Lo comparamos con lo que pierden.", "entry_id": "objection:price", "source_ref": "editor"}],
    )
    set_playbook_structure_llm(FakeLLM(NO_PROCESS, {"questions": [QUESTION]}))
    body = _post(client, payload=FAQ).json()
    assert body["reason"] is None and body["fallback"] is False
    assert [t["sales_motion_key"] for t in body["types"]] == ["closing"]
    editor = body["types"][0]["editor"]
    assert [s["step_id"] for s in editor["steps"]] == ["demo"]
    assert [o["category"] for o in editor["objections"]] == ["price", "custom"]
    assert _customs(editor) == [SALESFORCE]


def test_a_product_sheet_in_an_empty_company_creates_the_first_draft_with_only_the_questions(assistant_on):
    set_playbook_structure_llm(FakeLLM(NO_PROCESS, {"questions": [QUESTION]}))
    body = _post(_client(), payload=FAQ).json()
    assert [t["sales_motion_key"] for t in body["types"]] == ["discovery"]
    editor = body["types"][0]["editor"]
    assert editor["steps"] == [] and _customs(editor) == [SALESFORCE]


def test_failing_to_read_questions_never_breaks_the_intake(assistant_on):
    set_playbook_structure_llm(FakeLLM(MIXED_ANSWER, RuntimeError("boom")))
    body = _post(_client(), payload=f"{MIXED}\n{FAQ}").json()
    assert [t["sales_motion_key"] for t in body["types"]] == ["discovery", "closing"]
    assert all(_customs(t["editor"]) == [] for t in body["types"])


def test_without_questions_a_product_sheet_still_says_there_is_no_process(assistant_on):
    set_playbook_structure_llm(FakeLLM(NO_PROCESS, {"questions": []}))
    body = _post(_client(), payload=FAQ).json()
    assert body["types"] == [] and body["reason"] == "no_process"


def test_with_the_assistant_off_there_is_one_model_call_and_no_branches(monkeypatch):
    monkeypatch.setattr(settings, "PLAYBOOK_ASSISTANT_ENABLED", False)
    feature_flags.clear_cache()
    llm = FakeLLM(MIXED_ANSWER)
    set_playbook_structure_llm(llm)
    body = _post(_client(), payload=f"{MIXED}\n{FAQ}").json()
    assert len(llm.calls) == 1
    assert "branches" not in llm.calls[0]["messages"][0]["content"]
    assert all(_customs(t["editor"]) == [] for t in body["types"])
