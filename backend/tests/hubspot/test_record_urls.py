from app.services.hubspot.account_info import (
    build_company_record_url,
    build_contact_record_url,
    build_deal_record_url,
    build_record_url,
)
from app.services.hubspot.types import SyncResult


def test_build_record_url_contact_company_deal():
    assert (
        build_contact_record_url("123", "c1")
        == "https://app.hubspot.com/contacts/123/record/0-1/c1"
    )
    assert (
        build_deal_record_url("123", "d1")
        == "https://app.hubspot.com/contacts/123/record/0-3/d1"
    )
    assert (
        build_company_record_url("123", "co1", region="eu1")
        == "https://app-eu1.hubspot.com/contacts/123/record/0-2/co1"
    )
    assert (
        build_record_url("123", "c1", "0-1", ui_domain="app-eu1.hubspot.com")
        == "https://app-eu1.hubspot.com/contacts/123/record/0-1/c1"
    )


def test_sync_result_has_contact_url():
    result = SyncResult(memo_id="m1", contact_id="c1", contact_url="https://app.hubspot.com/contacts/1/record/0-1/c1")
    assert result.contact_url.endswith("/0-1/c1")
