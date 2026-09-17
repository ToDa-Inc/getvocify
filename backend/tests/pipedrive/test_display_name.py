from app.services.whatsapp.processor import _crm_display_name


def test_pipedrive_display_name():
    assert _crm_display_name("pipedrive") == "Pipedrive"
    assert _crm_display_name("hubspot") == "HubSpot"
    assert _crm_display_name("salesforce") == "Salesforce"
    assert _crm_display_name("other") == "CRM"
