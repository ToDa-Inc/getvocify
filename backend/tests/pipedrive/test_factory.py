from app.services.crm_providers.errors import UnsupportedCRMProviderError
from app.services.crm_providers.factory import build_crm_provider
from app.services.crm_providers.pipedrive_provider import PipedriveCRMProvider


def test_factory_returns_pipedrive_provider():
    conn = {
        "id": "c1",
        "provider": "pipedrive",
        "access_token": "tok",
        "metadata": {"api_domain": "https://acme.pipedrive.com"},
    }
    provider = build_crm_provider(None, conn)
    assert isinstance(provider, PipedriveCRMProvider)


def test_factory_unknown_still_raises():
    try:
        build_crm_provider(None, {"provider": "zoho"})
        raise AssertionError("expected UnsupportedCRMProviderError")
    except UnsupportedCRMProviderError as e:
        assert "zoho" in str(e)
