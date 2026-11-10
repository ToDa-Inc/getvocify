import pytest

from app.api import crm_pipedrive as api
from app.services.crm_providers.calling_registry import calling_adapter
from app.services.live_calls.crm_url import parse_crm_url

PEOPLE = {
    "42": {"id": 42, "name": "Ana Pérez", "phones": [{"value": "+34 611 222 333", "primary": True}], "emails": [{"value": "a@x.es", "primary": True}], "org_id": 10},
}


class Search:
    calls = 0

    def __init__(self, _client):
        pass

    async def get_person(self, pid):
        Search.calls += 1
        return PEOPLE.get(pid, {})

    async def get_organization(self, oid):
        return {"id": 10, "name": "Acme"}

    async def get_deal(self, did):
        return {"id": 7, "title": "Deal", "person_id": {"value": 42}, "org_id": {"value": 10, "name": "Acme"}} if did == "7" else {}

    async def get_lead(self, lid):
        return {"id": lid, "person_id": 42} if lid == "c94d8a70-d700-11f1-8ec0-61be409adeba" else {"id": lid, "person_id": None, "organization_id": None}

    async def get_activity(self, aid):
        return {
            "18": {"id": 18, "participants": [{"person_id": 99, "primary": False}, {"person_id": 42, "primary": True}]},
            "19": {"id": 19, "person_id": None, "deal_id": 7},
        }.get(aid, {"id": aid})

    async def persons_for_org(self, oid, limit=5):
        return [PEOPLE["42"]]


@pytest.fixture(autouse=True)
def world(monkeypatch):
    Search.calls = 0
    api._CONTEXT_CACHE._values.clear()
    monkeypatch.setattr(api, "_get_pipedrive_connection_row", lambda *_: {"id": "c"})
    monkeypatch.setattr(api, "_pd_client_from_row", lambda *_: object())
    monkeypatch.setattr(api, "PipedriveSearchService", Search)
    monkeypatch.setattr(api, "_session_vocab", lambda *a, **k: [])


@pytest.mark.asyncio
@pytest.mark.parametrize("url,expected", [
    ("https://acme.pipedrive.com/person/42", 1),
    ("https://acme.pipedrive.com/deal/7", 1),
    ("https://acme.pipedrive.com/organization/10", 1),
])
async def test_island_gets_a_callee_through_the_real_endpoints(url, expected):
    ctx = await calling_adapter("pipedrive").record_context(parse_crm_url(url), supabase=None, user_id="u")
    assert ctx.callee.contact_id == "42" and ctx.callee.phone == "+34611222333" and ctx.callee.name == "Ana Pérez"
    assert ctx.contacts_count == expected


@pytest.mark.asyncio
async def test_second_look_within_30s_does_not_hit_pipedrive():
    await api.get_pipedrive_person_context("42", supabase=None, user_id="u")
    await api.get_pipedrive_person_context("42", supabase=None, user_id="u")
    assert Search.calls == 1
    await api.get_pipedrive_person_context("42", supabase=None, user_id="other")
    assert Search.calls == 2


@pytest.mark.asyncio
async def test_unknown_person_has_no_phone():
    ctx = await calling_adapter("pipedrive").record_context(parse_crm_url("https://acme.pipedrive.com/person/99"), supabase=None, user_id="u")
    assert ctx.callee.phone is None


LEAD = "https://acme.pipedrive.com/leads/inbox/c94d8a70-d700-11f1-8ec0-61be409adeba"


@pytest.mark.asyncio
async def test_a_leads_inbox_page_is_called_through_the_leads_person():
    ctx = await calling_adapter("pipedrive").record_context(parse_crm_url(LEAD), supabase=None, user_id="u")
    assert (ctx.callee.contact_id, ctx.callee.phone, ctx.contacts_count) == ("42", "+34611222333", 1)


@pytest.mark.asyncio
async def test_a_lead_without_a_person_offers_nobody():
    other = LEAD.replace("c94d8a70", "00000000")
    ctx = await calling_adapter("pipedrive").record_context(parse_crm_url(other), supabase=None, user_id="u")
    assert ctx.callee is None


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "https://acme.pipedrive.com/activities/list?selected=18&tab=activity",  # its primary participant
    "https://acme.pipedrive.com/activities/list?selected=19&tab=activity",  # no person: its deal's
])
async def test_an_activity_open_in_the_list_is_called_through_who_it_is_with(url):
    ctx = await calling_adapter("pipedrive").record_context(parse_crm_url(url), supabase=None, user_id="u")
    assert (ctx.callee.contact_id, ctx.callee.phone) == ("42", "+34611222333")


@pytest.mark.asyncio
async def test_an_activity_with_nobody_offers_nobody():
    ctx = await calling_adapter("pipedrive").record_context(parse_crm_url("https://acme.pipedrive.com/activities/list?selected=20"), supabase=None, user_id="u")
    assert ctx.callee is None
