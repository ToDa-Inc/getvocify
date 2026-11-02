import pytest

from app.api import crm_pipedrive
from app.services.crm_providers.calling_registry import calling_adapter
from app.services.live_calls.crm_url import CrmRecord, parse_crm_url


def _record(url: str) -> CrmRecord:
    record = parse_crm_url(url)
    assert isinstance(record, CrmRecord)
    return record


def _loader(answer, seen):
    async def load(record_id, *, supabase, user_id):
        seen.append((record_id, user_id))
        if isinstance(answer, Exception):
            raise answer
        return answer

    return load


@pytest.mark.asyncio
async def test_person_page_is_callable_at_its_primary_number(monkeypatch):
    seen = []
    monkeypatch.setattr(
        crm_pipedrive,
        "get_pipedrive_person_context",
        _loader({"contactId": "901", "contactName": "Ada Lovelace", "contactPhone": "+34 612 345 678"}, seen),
    )
    context = await calling_adapter("pipedrive").record_context(
        _record("https://acme.pipedrive.com/person/901"), supabase=None, user_id="u1"
    )
    assert seen == [("901", "u1")]
    assert (context.callee.contact_id, context.callee.name, context.callee.phone) == ("901", "Ada Lovelace", "+34612345678")
    assert context.contacts_count == 1


@pytest.mark.asyncio
async def test_person_without_a_dialable_number_has_a_callee_but_no_phone(monkeypatch):
    monkeypatch.setattr(
        crm_pipedrive,
        "get_pipedrive_person_context",
        _loader({"contactId": "901", "contactName": "Ada", "contactPhone": "ext 12"}, []),
    )
    context = await calling_adapter("pipedrive").record_context(
        _record("https://acme.pipedrive.com/person/901"), supabase=None, user_id="u1"
    )
    assert context.callee.contact_id == "901"
    assert context.callee.phone is None


@pytest.mark.asyncio
async def test_deal_is_callable_through_its_person(monkeypatch):
    seen = []
    monkeypatch.setattr(
        crm_pipedrive,
        "get_pipedrive_deal_context",
        _loader(
            {
                "contactId": "901",
                "contactName": "Ada",
                "contactPhone": "+34612345678",
                "contacts": [{"contact_id": "901"}],
            },
            seen,
        ),
    )
    context = await calling_adapter("pipedrive").record_context(
        _record("https://acme.pipedrive.com/deal/55"), supabase=None, user_id="u1"
    )
    assert seen == [("55", "u1")]
    assert context.callee.contact_id == "901"
    assert context.contacts_count == 1


@pytest.mark.asyncio
async def test_organization_with_several_people_has_no_callee_until_one_is_picked(monkeypatch):
    monkeypatch.setattr(
        crm_pipedrive,
        "get_pipedrive_org_context",
        _loader({"contactId": None, "contacts": [{"contact_id": "1"}, {"contact_id": "2"}]}, []),
    )
    context = await calling_adapter("pipedrive").record_context(
        _record("https://acme.pipedrive.com/organization/12"), supabase=None, user_id="u1"
    )
    assert context.callee is None
    assert context.contacts_count == 2


@pytest.mark.asyncio
async def test_a_failed_read_offers_no_call(monkeypatch):
    monkeypatch.setattr(crm_pipedrive, "get_pipedrive_person_context", _loader(RuntimeError("boom"), []))
    context = await calling_adapter("pipedrive").record_context(
        _record("https://acme.pipedrive.com/person/901"), supabase=None, user_id="u1"
    )
    assert context.callee is None
    assert context.contacts_count == 0
