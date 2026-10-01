"""Fill with AI ("Dile a Vocify"): the model returns only changes and deterministic code applies them,
so a request about one thing never rewrites the rest; the result always saves; the company notes keep
the structuring guards (no competitor or number nobody gave)."""

from __future__ import annotations

import pytest

from app.services.playbooks.fill import (
    apply_company_changes,
    apply_playbook_changes,
    restrict_company,
    restrict_to,
)
from app.services.playbooks.knowledge import normalize_knowledge
from app.services.playbooks.structure import set_playbook_structure_llm
from tests.playbooks.test_company_intake import _client
from tests.playbooks.test_structure import FakeLLM

BASE = "/api/v1/playbooks"

CURRENT = {
    "steps": [
        {"step_id": "apertura", "label": "Apertura", "criterion": "Se presenta y pide un minuto."},
        {"step_id": "dolor", "label": "Descubrir el dolor", "criterion": "Pregunta cómo lo hacen hoy."},
    ],
    "objections": [{"category": "price", "guidance": "Pregunta cuánto les cuesta hoy."}],
    "qualification": [{"criterion_id": "presupuesto", "label": "Presupuesto"}],
}


@pytest.fixture(autouse=True)
def _reset_llm():
    yield
    set_playbook_structure_llm(None)


# --- applying a playbook's changes -------------------------------------------------------------


def test_only_what_the_model_names_changes():
    result = apply_playbook_changes(CURRENT, {
        "steps": [{"index": 2, "criterion": "Pregunta cómo lo hacen hoy y el prospecto nombra un problema."}],
    })
    assert result["steps"][0] == CURRENT["steps"][0]
    assert result["steps"][1] == {
        "step_id": "dolor", "label": "Descubrir el dolor",
        "criterion": "Pregunta cómo lo hacen hoy y el prospecto nombra un problema.",
    }
    assert result["objections"] == CURRENT["objections"]
    assert result["qualification"] == CURRENT["qualification"]
    assert result["changes"] == 1


def test_adds_removes_and_ignores_indexes_that_do_not_exist():
    result = apply_playbook_changes(CURRENT, {
        "steps": [
            {"index": None, "label": "Cerrar reunión", "criterion": "Propone día y hora y el prospecto acepta."},
            {"index": 9, "label": "Fantasma"},
        ],
        "remove_steps": [1],
        "qualification": [{"index": 1, "good": "Da una cifra."}, {"index": None, "label": "Quién decide"}],
    })
    assert [s["label"] for s in result["steps"]] == ["Descubrir el dolor", "Cerrar reunión"]
    assert result["qualification"] == [
        {"criterion_id": "presupuesto", "label": "Presupuesto", "good": "Da una cifra."},
        {"label": "Quién decide"},
    ]


def test_objections_are_upserted_by_category_and_custom_label():
    result = apply_playbook_changes(CURRENT, {"objections": [
        {"category": "price", "trigger": "¿Cuánto os cuesta hoy el CRM?"},
        {"category": "timing"},  # a fixed category without its answer is not added
        {"category": "custom", "label": "Ya tenemos Aircall", "guidance": "¿Y qué pasa después de colgar?"},
        {"category": "made_up", "guidance": "x"},
    ]})
    by = {o.get("label") or o["category"]: o for o in result["objections"]}
    assert by["price"]["guidance"] == "Pregunta cuánto les cuesta hoy."
    assert "timing" not in by and "made_up" not in by
    assert by["Ya tenemos Aircall"]["category"] == "custom" and by["Ya tenemos Aircall"]["id"]
    removed = apply_playbook_changes(result, {"remove_objections": [{"category": "custom", "label": "ya tenemos aircall"}]})
    assert [o["category"] for o in removed["objections"]] == ["price"]


def test_markdown_is_dropped_and_an_attitude_criterion_is_left_for_the_manager():
    result = apply_playbook_changes(CURRENT, {"steps": [
        {"index": 1, "label": "**Apertura** con permiso"},
        {"index": 2, "criterion": "Genera confianza con el prospecto."},
    ]})
    assert result["steps"][0]["label"] == "Apertura con permiso"
    assert result["steps"][1]["criterion"] == ""


def test_a_request_that_changes_nothing_returns_the_same_content():
    result = apply_playbook_changes(CURRENT, {"steps": [], "objections": "nonsense"})
    assert result["changes"] == 0
    assert result["steps"] == CURRENT["steps"]


def test_a_completion_on_one_item_can_change_nothing_else():
    ops = {
        "steps": [{"index": 1, "criterion": "Otro."}, {"index": 2, "criterion": "Pregunta y el prospecto nombra un problema."}],
        "objections": [
            {"category": "price", "guidance": "Otra respuesta."},
            {"category": "authority", "guidance": "Pide que te presente a quien decide.", "trigger": "No soy quien decide esto"},
        ],
        "remove_steps": [1],
    }
    only_step = apply_playbook_changes(CURRENT, restrict_to(ops, {"steps": [2]}))
    assert [s["criterion"] for s in only_step["steps"]] == [
        "Se presenta y pide un minuto.", "Pregunta y el prospecto nombra un problema.",
    ]
    assert only_step["objections"] == CURRENT["objections"]
    only_authority = apply_playbook_changes(CURRENT, restrict_to(ops, {"objections": [{"category": "authority"}]}))
    assert [o["category"] for o in only_authority["objections"]] == ["price", "authority"]
    assert only_authority["objections"][0]["guidance"] == "Pregunta cuánto les cuesta hoy."
    # a fixed category keeps how the prospect says it
    assert only_authority["objections"][1]["trigger"] == "No soy quien decide esto"


# --- applying the company's changes -----------------------------------------------------------


EXISTING = normalize_knowledge({
    "icp": "Startups B2B con SDRs.",
    "competitors": [{"name": "Gong", "how_to_talk": "Llaman en español."}],
})


def test_company_items_are_upserted_by_name_and_only_given_fields_change():
    knowledge, filled = apply_company_changes(EXISTING, {"set": {
        "competitors": [{"name": "gong", "how_to_talk": "Quieren análisis de pipeline."}],
        "value_short": "Rellenamos el CRM al colgar.",
    }}, "Añade cuándo perdemos contra Gong " + str(EXISTING))
    gong = knowledge["competitors"][0]
    assert gong["how_to_talk"] == "Quieren análisis de pipeline."
    assert knowledge["icp"] == "Startups B2B con SDRs."
    assert filled == ["value_short", "competitors"]


def test_a_competitor_or_a_number_nobody_gave_is_dropped():
    knowledge, _ = apply_company_changes(EXISTING, {"set": {
        "competitors": [{"name": "Chorus", "how_to_talk": "x"}],
        "proofs": [{"customer": "Ríos", "change": "Menos tiempo en el CRM. -73 % improvement"}],
    }}, "Añade el caso de Ríos: tardaban 40 minutos")
    assert [c["name"] for c in knowledge["competitors"]] == ["Gong"]
    # The change field with digits not in the source is emptied
    assert knowledge["proofs"][0]["change"] == ""


def test_company_items_are_removed_by_name():
    knowledge, filled = apply_company_changes(EXISTING, {"remove": {"competitors": ["GONG"]}}, "quita Gong")
    assert knowledge["competitors"] == [] and filled == ["competitors"]


def test_a_company_completion_changes_only_that_item_or_those_fields():
    ops = {"set": {
        "icp": "Otro ICP.", "pricing": "Por comercial y mes.",
        "competitors": [{"name": "Gong", "how_to_talk": "Piden análisis."}, {"name": "Chorus", "how_to_talk": "x"}],
    }, "remove": {"competitors": ["Gong"]}}
    only_gong, _ = apply_company_changes(EXISTING, restrict_company(ops, {"list": "competitors", "name": "gong"}), "Gong Chorus")
    assert [c["name"] for c in only_gong["competitors"]] == ["Gong"]
    assert only_gong["competitors"][0]["how_to_talk"] == "Piden análisis." and only_gong["icp"] == "Startups B2B con SDRs."
    only_pricing, filled = apply_company_changes(EXISTING, restrict_company(ops, {"texts": ["pricing"]}), "")
    assert filled == ["pricing"] and only_pricing["icp"] == "Startups B2B con SDRs."


# --- HTTP -------------------------------------------------------------------------------------


def test_fill_returns_the_changed_playbook_and_saves_nothing():
    llm = FakeLLM({"summary": "Añadida la respuesta a «no decido».", "objections": [
        {"category": "authority", "guidance": "Pide que te presente a quien decide."},
    ]})
    set_playbook_structure_llm(llm)
    client = _client()
    response = client.post(f"{BASE}/discovery/fill", json={"kind": "text", "payload": "Si dicen que no deciden…", "current": CURRENT})
    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "Añadida la respuesta a «no decido»."
    assert [o["category"] for o in body["objections"]] == ["price", "authority"]
    assert "Current playbook" in llm.calls[0]["messages"][1]["content"]
    assert client.get(f"{BASE}/discovery/editor").json()["source"] == "empty"  # nothing saved


def test_fill_is_422_when_the_model_fails_and_403_for_a_member():
    set_playbook_structure_llm(FakeLLM(TimeoutError()))
    response = _client().post(f"{BASE}/discovery/fill", json={"kind": "text", "payload": "Añade un paso", "current": CURRENT})
    assert response.status_code == 422 and response.json()["detail"]["code"] == "fill_failed"
    member = _client(role="member").post(f"{BASE}/discovery/fill", json={"kind": "text", "payload": "x", "current": CURRENT})
    assert member.status_code == 403


def test_company_fill_saves_at_once_with_the_conflict_check():
    set_playbook_structure_llm(FakeLLM(
        {"summary": "Añadido Gong.", "set": {"competitors": [{"name": "Gong", "how_to_talk": "Llaman en español."}]}},
        {"summary": "Añadido cuándo perdemos.", "set": {"competitors": [{"name": "Gong", "how_to_talk": "Piden análisis."}]}},
    ))
    client = _client()
    response = client.post(f"{BASE}/company/fill", json={"kind": "text", "payload": "Competimos con Gong: ganamos cuando llaman en español"})
    assert response.status_code == 200
    body = response.json()
    assert body["filled"] == ["competitors"] and body["summary"] == "Añadido Gong."
    assert client.get(f"{BASE}/company").json()["knowledge"]["competitors"][0]["name"] == "Gong"
    stale = client.post(f"{BASE}/company/fill", json={
        "kind": "text", "payload": "Competimos con Gong", "base_updated_at": "2000-01-01T00:00:00+00:00",
    })
    assert stale.status_code == 409


def test_fill_with_a_scope_tells_the_model_and_applies_only_that_item():
    llm = FakeLLM({"summary": "x", "objections": [
        {"category": "price", "guidance": "Cambiada."},
        {"category": "timing", "guidance": "¿Te llamo el martes?"},
    ]})
    set_playbook_structure_llm(llm)
    response = _client().post(f"{BASE}/discovery/fill", json={
        "kind": "text", "payload": "Escribe la respuesta a «No es el momento».", "current": CURRENT,
        "scope": {"objections": [{"category": "timing"}]},
    })
    body = response.json()
    assert {o["category"]: o["guidance"] for o in body["objections"]} == {
        "price": "Pregunta cuánto les cuesta hoy.", "timing": "¿Te llamo el martes?",
    }
    assert "Change ONLY: objection timing" in llm.calls[0]["messages"][1]["content"]

