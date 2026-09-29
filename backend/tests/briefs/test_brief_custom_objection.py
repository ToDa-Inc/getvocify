"""C04 v7: the pre-call brief answers a company-own objection with that entry's guidance."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-briefs-32-chars")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-briefs-32-chars")

from app.services.briefs.v2 import say_line

ENTRIES = [
    {"entry_id": "objection:price", "category": "price", "guidance": "Habla de retorno, no de tarifa."},
    {
        "entry_id": "objection:custom:integracion-erp", "category": "custom", "label": "Integración con el ERP",
        "trigger": "Su ERP no se conecta", "question": "¿Qué ERP usáis?", "guidance": "Tenemos API abierta y lo vemos con su equipo técnico.",
    },
    {"entry_id": "objection:custom:rgpd", "category": "custom", "label": "RGPD", "trigger": "Dudas de datos"},
]


def _intel(*objections):
    return {"objections": list(objections)}


def _objection(**extra):
    return {"id": "obj-1", "kind": "objection", "category": "other", "resolution": "open", "quote": "mi ERP es propio", **extra}


def test_a_custom_objection_uses_its_own_guidance_and_label():
    line = say_line(intelligence=_intel(_objection(objection_id="integracion-erp")), playbook_entries=ENTRIES)
    assert line["type"] == "say" and line["source"] == "playbook" and line["source_ref"] == "obj-1"
    assert line["text"] == "Integración con el ERP: Tenemos API abierta y lo vemos con su equipo técnico."
    assert "\n" not in line["text"] and "¿Qué ERP" not in line["text"]  # one line: the guidance


def test_the_custom_answer_wins_over_the_category_answer():
    line = say_line(
        intelligence=_intel(_objection(category="price", objection_id="integracion-erp")), playbook_entries=ENTRIES,
    )
    assert line["text"].startswith("Integración con el ERP: ")


def test_a_custom_entry_without_guidance_falls_back_to_the_category_answer():
    line = say_line(intelligence=_intel(_objection(category="price", objection_id="rgpd")), playbook_entries=ENTRIES)
    assert line["text"] == "Precio: Habla de retorno, no de tarifa."


def test_a_custom_entry_without_guidance_and_no_category_answer_says_nothing():
    assert say_line(intelligence=_intel(_objection(objection_id="rgpd")), playbook_entries=ENTRIES) is None


def test_an_id_the_playbook_no_longer_has_is_ignored():
    assert say_line(intelligence=_intel(_objection(objection_id="borrada")), playbook_entries=ENTRIES) is None
    line = say_line(intelligence=_intel(_objection(category="price", objection_id="borrada")), playbook_entries=ENTRIES)
    assert line["text"] == "Precio: Habla de retorno, no de tarifa."


def test_without_an_id_nothing_changes():
    line = say_line(intelligence=_intel(_objection(category="price")), playbook_entries=ENTRIES)
    assert line["text"] == "Precio: Habla de retorno, no de tarifa."
    assert say_line(intelligence=_intel(_objection()), playbook_entries=ENTRIES) is None
    assert say_line(intelligence=_intel(_objection(objection_id=None)), playbook_entries=None) is None


def test_a_resolved_custom_objection_is_not_brought_back():
    resolved = _objection(objection_id="integracion-erp", resolution="resolved")
    assert say_line(intelligence=_intel(resolved), playbook_entries=ENTRIES) is None


def test_the_first_open_objection_with_an_answer_is_the_one_shown():
    line = say_line(
        intelligence=_intel(
            _objection(id="obj-a", category="other"),
            _objection(id="obj-b", objection_id="integracion-erp"),
        ),
        playbook_entries=ENTRIES,
    )
    assert line["source_ref"] == "obj-b"
