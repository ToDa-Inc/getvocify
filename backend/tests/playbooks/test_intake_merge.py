"""Several documents for the same call type become ONE draft: the intake replaces a type's draft, so what each file
found has to be put together before it is saved."""

from __future__ import annotations

from app.services.playbooks.intake import merge_split_results
from app.services.playbooks.structured import MAX_CRITERIA, MAX_STEPS


def doc(key="discovery", steps=(), objections=(), qualification=(), reason=None):
    return {
        "key": key, "reason": reason,
        "steps": [{"label": label, "criterion": f"criterio de {label}"} for label in steps],
        "objections": list(objections), "qualification": [{"label": label} for label in qualification],
    }


def test_nothing_in_nothing_out():
    assert merge_split_results([]) == {}
    assert merge_split_results([[], []]) == {}


def test_steps_are_put_together_in_order_without_repeating_a_step_by_its_name():
    merged = merge_split_results([[doc(steps=["Apertura", "Motivo"])], [doc(steps=["apertura", "Cierre"])]])
    assert [s["label"] for s in merged["discovery"]["steps"]] == ["Apertura", "Motivo", "Cierre"]
    assert merged["discovery"]["steps"][0]["criterion"] == "criterio de Apertura"


def test_the_first_answer_to_a_fixed_objection_stays_and_own_objections_are_added_by_name():
    first = [{"category": "price", "guidance": "A"}, {"category": "custom", "label": "Legal", "trigger": "t", "guidance": "g"}]
    second = [
        {"category": "price", "guidance": "B"}, {"category": "timing", "guidance": "T"},
        {"category": "custom", "label": "legal", "trigger": "x", "guidance": "otra"},
        {"category": "custom", "label": "Seguridad", "trigger": "s", "guidance": "ok"},
    ]
    merged = merge_split_results([[doc(objections=first)], [doc(objections=second)]])["discovery"]["objections"]
    assert [(o["category"], o.get("label"), o["guidance"]) for o in merged] == [
        ("price", None, "A"), ("custom", "Legal", "g"), ("timing", None, "T"), ("custom", "Seguridad", "ok"),
    ]


def test_criteria_are_added_by_name_up_to_the_limit():
    merged = merge_split_results([[doc(qualification=["Presupuesto", "Plazo"])], [doc(qualification=["presupuesto"] + [f"Dato {i}" for i in range(12)])]])
    labels = [q["label"] for q in merged["discovery"]["qualification"]]
    assert labels[:2] == ["Presupuesto", "Plazo"] and len(labels) == MAX_CRITERIA


def test_too_many_steps_are_cut_and_the_type_is_marked_as_grouped():
    merged = merge_split_results([[doc(steps=[f"Paso {i}" for i in range(10)])], [doc(steps=[f"Otro {i}" for i in range(10)])]])["discovery"]
    assert len(merged["steps"]) == MAX_STEPS and merged["reason"] == "grouped"


def test_each_call_type_is_kept_apart_and_a_grouped_reason_is_not_lost():
    merged = merge_split_results([[doc("discovery", steps=["A"], reason="grouped"), doc("closing", steps=["B"])], [doc("discovery", steps=["C"])]])
    assert list(merged) == ["discovery", "closing"]
    assert merged["discovery"]["reason"] == "grouped" and merged["closing"]["reason"] is None
