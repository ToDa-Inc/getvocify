from app.services.pipedrive.page_context import assoc_id, contact_from_person, deal_raw_extraction, person_names


def test_assoc_id_int_and_nested():
    assert assoc_id(20) == "20"
    assert assoc_id({"id": 7}) == "7"
    assert assoc_id({"value": 9}) == "9"
    assert assoc_id(None) is None


def test_person_names_splits_full_name():
    assert person_names({"name": "Ada Lovelace"}) == ("Ada", "Lovelace", "Ada Lovelace")
    assert person_names({"first_name": "Ada", "last_name": "Lovelace"}) == (
        "Ada",
        "Lovelace",
        "Ada Lovelace",
    )


def test_contact_from_person_phone_for_dialer():
    contact = contact_from_person(
        {
            "id": 20,
            "name": "Ada Lovelace",
            "emails": [{"value": "ada@acme.com", "primary": True}],
            "phones": [{"value": "+15551212", "primary": True}],
            "org_id": {"id": 10, "name": "Acme"},
        }
    )
    assert contact["contact_id"] == "20"
    assert contact["phone"] == "+15551212"
    assert contact["email"] == "ada@acme.com"
    assert contact["company_id"] == "10"
    assert contact["company_name"] == "Acme"


def test_deal_raw_extraction_title_is_dealname():
    raw = deal_raw_extraction(
        {"title": "Acme", "value": 1000, "stage_id": 5, "expected_close_date": "2026-01-01"}
    )
    assert raw["dealname"] == "Acme"
    assert raw["amount"] == 1000.0
    assert raw["dealstage"] == "5"
    assert raw["closedate"] == "2026-01-01"
