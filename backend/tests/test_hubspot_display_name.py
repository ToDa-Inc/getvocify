from app.services.hubspot.contact_identity import display_name


def test_a_missing_last_name_is_not_written_as_none():
    assert display_name({"firstname": "Andrea mora", "lastname": None}) == "Andrea mora"


def test_both_names_are_joined():
    assert display_name({"firstname": "Marc", "lastname": "Boixet"}) == "Marc Boixet"


def test_no_names_is_none():
    assert display_name({"firstname": None, "lastname": " "}) is None
