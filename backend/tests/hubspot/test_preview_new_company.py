from app.services.hubspot.preview import proposed_new_company


def test_proposed_new_company_skipped_when_company_already_linked():
    assert (
        proposed_new_company(
            has_existing_company=True,
            company_name="Acme",
            company_props={"crm_utilizado": "zoho"},
        )
        is None
    )


def test_proposed_new_company_from_name_and_properties():
    assert proposed_new_company(
        has_existing_company=False,
        company_name="Acme",
        company_props={"name": "Acme", "crm_utilizado": "zoho"},
    ) == {"name": "Acme", "properties": {"crm_utilizado": "zoho"}}


def test_proposed_new_company_from_properties_only():
    assert proposed_new_company(
        has_existing_company=False,
        company_name=None,
        company_props={"crm_utilizado": "zoho"},
    ) == {"properties": {"crm_utilizado": "zoho"}}


def test_proposed_new_company_requires_a_signal():
    assert (
        proposed_new_company(
            has_existing_company=False,
            company_name="  ",
            company_props={},
        )
        is None
    )
