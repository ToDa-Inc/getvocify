"""The record on screen, from the CRM page URLs the desktop sees."""

import pytest

from app.services.live_calls.crm_url import CrmPage, CrmRecord, parse_crm_url, record_on_screen

HS = "https://app-eu1.hubspot.com/contacts/147506535"


@pytest.mark.parametrize(
    "url, expected",
    [
        (f"{HS}/record/0-1/879829962968?eschref=%2Fcontacts", CrmRecord("hubspot", "contact", "879829962968", "147506535")),
        ("https://app.hubspot.com/contacts/1/record/0-3/55", CrmRecord("hubspot", "deal", "55", "1")),
        ("https://app.hubspot.com/contacts/1/record/0-2/56/", CrmRecord("hubspot", "company", "56", "1")),
        ("https://app.hubspot.com/contacts/1/contact/57", CrmRecord("hubspot", "contact", "57", "1")),
        ("https://Acme.pipedrive.com/person/42", CrmRecord("pipedrive", "contact", "42", "acme")),
        ("https://acme.pipedrive.com/deal/7", CrmRecord("pipedrive", "deal", "7", "acme")),
        ("https://acme.pipedrive.com/organization/8", CrmRecord("pipedrive", "company", "8", "acme")),
    ],
)
def test_records(url, expected):
    assert parse_crm_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        f"{HS}/objects/0-1/views/all/list",
        "https://app-eu1.hubspot.com/sequences/147506535",
        "https://app.hubspot.com/contacts/1/record/0-5/9",
        "https://acme.pipedrive.com/pipeline",
    ],
)
def test_crm_pages_that_are_not_records(url):
    assert isinstance(parse_crm_url(url), CrmPage)


@pytest.mark.parametrize(
    "url",
    [
        "https://app-eu1.hubspot.com/calling-integration-popup-ui/147506535",
        "https://app-eu1.hubspot.com/calling-cross-tab-embed/147506535/calling-remote-app",
        "https://app-eu1.hubspot.com/calling/147506535/twilio?subjectId=1",
        "https://www.hubspot.com/pricing",
        "https://knowledge.hubspot.com/a",
        "https://api.pipedrive.com/v1/persons/1",
        "https://mail.google.com/mail/u/0",
        "http://app.hubspot.com/contacts/1/record/0-1/2",
        "",
        None,
    ],
)
def test_not_where_the_rep_is(url):
    assert parse_crm_url(url) is None


def test_front_most_crm_page_decides():
    record = f"{HS}/record/0-1/901"
    calling = "https://app-eu1.hubspot.com/calling-integration-popup-ui/147506535"
    lst = f"{HS}/objects/0-1/views/all/list"
    assert record_on_screen([calling, record]).record_id == "901"
    assert record_on_screen([lst, record]) is None
    assert record_on_screen([record, lst]).record_id == "901"
    assert record_on_screen(["https://mail.google.com/", record]).record_id == "901"
    assert record_on_screen([]) is None
