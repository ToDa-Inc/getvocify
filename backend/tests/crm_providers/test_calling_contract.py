"""Every CRM the island can call must also be recognised on screen.

Adding a CRM to `CALLING_ADAPTERS` without its page URLs here (and their
parsing in `live_calls/crm_url.py`) fails these tests.
"""

import pytest

from app.services.crm_providers.calling_registry import CALLING_ADAPTERS
from app.services.live_calls.crm_url import CrmRecord, parse_crm_url

PAGE_FIXTURES = {
    "hubspot": [
        ("https://app.hubspot.com/contacts/147506535/record/0-1/901", "contact"),
        ("https://app-eu1.hubspot.com/contacts/147506535/record/0-3/55", "deal"),
        ("https://app.hubspot.com/contacts/147506535/record/0-2/12", "company"),
    ],
}


@pytest.mark.parametrize("provider", sorted(CALLING_ADAPTERS))
def test_every_callable_crm_has_page_urls_that_parse_to_it(provider):
    assert provider in PAGE_FIXTURES, f"add {provider} record page URLs to PAGE_FIXTURES"
    for url, object_type in PAGE_FIXTURES[provider]:
        record = parse_crm_url(url)
        assert isinstance(record, CrmRecord), url
        assert (record.provider, record.object_type) == (provider, object_type)


@pytest.mark.parametrize("provider", sorted(CALLING_ADAPTERS))
def test_adapter_is_registered_under_its_own_name(provider):
    assert CALLING_ADAPTERS[provider].provider == provider
