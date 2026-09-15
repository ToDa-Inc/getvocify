from app.services.hubspot.contact_identity import stored_contact_phone


def test_stored_contact_phone_prefers_phone_then_mobile():
    assert stored_contact_phone({"phone": "+34600111222", "mobilephone": "+34600999000"}) == "+34600111222"
    assert stored_contact_phone({"phone": "", "mobilephone": "600111222"}) == "600111222"


def test_stored_contact_phone_uses_hubspot_search_and_whatsapp_fields():
    assert stored_contact_phone({
        "phone": None,
        "mobilephone": "",
        "hs_whatsapp_phone_number": "+34648739267",
    }) == "+34648739267"
    assert stored_contact_phone({
        "phone": None,
        "hs_searchable_calculated_phone_number": "34648739267",
    }) == "34648739267"


def test_stored_contact_phone_is_none_when_hubspot_has_no_number():
    assert stored_contact_phone({}) is None
    assert stored_contact_phone(None) is None
