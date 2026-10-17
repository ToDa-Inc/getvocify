"""The rules that turn a company's own types into the rest of the product's vocabulary (roles, visibility, keys)."""

from __future__ import annotations

from app.services.sales_process.logic import assigned_types, role_from_types, slug_key, stage_for

ROWS = [
    {"key": "cold", "position": 1, "stage": "first_contact"},
    {"key": "demo", "position": 2, "stage": "deal"},
]


def stage(key):
    return stage_for(key, ROWS)


def test_a_type_of_the_process_has_the_stage_its_company_gave_it():
    assert (stage("cold"), stage("demo")) == ("first_contact", "deal")


def test_a_catalog_type_the_company_never_edited_keeps_what_its_role_said():
    assert stage_for("discovery", []) == "first_contact"  # the SDR cold call
    assert stage_for("closing", []) == "deal"  # the AE's
    assert stage_for("something-of-their-own", []) == "first_contact"


def test_the_company_wins_over_the_catalog():
    assert stage_for("closing", [{"key": "closing", "position": 1, "stage": "first_contact"}]) == "first_contact"


def test_the_role_comes_from_the_stages_of_what_the_person_runs():
    assert role_from_types(["cold"], stage) == "sdr"
    assert role_from_types(["demo"], stage) == "ae"
    assert role_from_types(["cold", "demo"], stage) == "general"


def test_everything_or_nothing_assigned_is_a_general_member():
    assert role_from_types(None, stage) == "general"
    assert role_from_types([], stage) == "general"


def test_types_that_no_longer_exist_are_forgotten_and_an_empty_list_means_all():
    assert assigned_types(["cold", "gone", "demo"], {"cold", "demo"}) == ["cold", "demo"]
    assert assigned_types(["gone"], {"cold"}) is None
    assert assigned_types([], {"cold"}) is None and assigned_types(None, {"cold"}) is None
    assert assigned_types(["cold", "cold"], {"cold"}) == ["cold"]


def test_a_name_becomes_a_key_that_is_free():
    assert slug_key("Llamada en frío", set()) == "llamada_en_frio"
    assert slug_key("Llamada en frío", {"llamada_en_frio"}) == "llamada_en_frio_2"
    assert slug_key("¿¿??", set()) == "tipo"
