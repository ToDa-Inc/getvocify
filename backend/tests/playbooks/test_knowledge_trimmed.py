"""A list or text cut for size is reported, never saved in silence (Movertis lost 6 of 18 profiles at a cap of 12)."""
from app.services.playbooks.knowledge import MAX_ITEMS, MAX_LONG, MAX_SHORT, normalize_knowledge, trimmed


def test_eighteen_personas_are_kept():
    raw = {"personas": [{"name": f"Perfil {i}", "cares_about": "x"} for i in range(18)]}
    assert len(normalize_knowledge(raw)["personas"]) == 18
    assert trimmed(raw) == []


def test_a_list_over_the_cap_says_how_many_were_cut():
    raw = {"personas": [{"name": f"P{i}"} for i in range(MAX_ITEMS + 5)]}
    assert trimmed(raw) == [{"section": "personas", "sent": MAX_ITEMS + 5, "kept": MAX_ITEMS, "limit": "items"}]


def test_long_texts_and_long_fields_are_reported():
    raw = {"icp": "a" * (MAX_LONG + 10), "proofs": [{"customer": "A", "change": "b" * (MAX_SHORT + 1)}]}
    assert trimmed(raw) == [
        {"section": "icp", "sent": MAX_LONG + 10, "kept": MAX_LONG, "limit": "characters"},
        {"section": "proofs", "sent": MAX_SHORT + 1, "kept": MAX_SHORT, "limit": "characters per field"},
    ]


def test_duplicates_and_nameless_items_are_not_size_cuts():
    raw = {"personas": [{"name": "A"}, {"name": "a"}, {"cares_about": "no name"}], "differentiators": ["x", "X"]}
    assert trimmed(raw) == [] and trimmed("junk") == []
