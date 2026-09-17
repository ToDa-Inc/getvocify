import pytest

from app.models.memo import MemoExtraction
from app.services.hubspot.contact_identity import ContactAnchor, IdentityResolution
from app.services.pipedrive.identity import PipedriveIdentityService
from app.services.pipedrive.search import PipedriveSearchService


class _Search:
    def __init__(self, persons=None, orgs=None, person=None):
        self.persons = persons or []
        self.orgs = orgs or []
        self.person = person
        self.deals = []

    async def get_person(self, pid):
        return self.person or {}

    async def search_persons(self, term, *, fields="name,email,phone", limit=10):
        return list(self.persons)

    async def search_organizations(self, term, *, limit=10):
        return list(self.orgs)

    async def get_organization(self, oid):
        return {"id": oid, "name": "Acme"}

    async def deals_for_person(self, person_id, *, limit=5):
        return list(self.deals)


@pytest.mark.asyncio
async def test_email_autolocks():
    search = _Search(persons=[{"id": 9, "name": "Ada", "emails": [{"value": "ada@acme.com", "primary": True}]}])
    res = await PipedriveIdentityService(search).resolve_identity(
        MemoExtraction(contactEmail="ada@acme.com", contactName="Ada")
    )
    assert isinstance(res, IdentityResolution)
    assert isinstance(res.selected, ContactAnchor)
    assert res.selected.contact_id == "9"
    assert res.candidates == []


@pytest.mark.asyncio
async def test_email_does_not_lock_fuzzy_non_matching_hit():
    search = _Search(persons=[{"id": 9, "name": "Ada", "emails": [{"value": "other@acme.com", "primary": True}]}])
    res = await PipedriveIdentityService(search).resolve_identity(
        MemoExtraction(contactEmail="ada@acme.com")
    )
    assert res.selected is None


@pytest.mark.asyncio
async def test_name_is_candidates_only():
    search = _Search(persons=[{"id": 1, "name": "Ada"}, {"id": 2, "name": "Ada Lopez"}])
    res = await PipedriveIdentityService(search).resolve_identity(MemoExtraction(contactName="Ada"))
    assert res.selected is None
    assert len(res.candidates) == 2


@pytest.mark.asyncio
async def test_company_only_does_not_lock_person():
    search = _Search(orgs=[{"id": 44, "name": "Acme"}])
    res = await PipedriveIdentityService(search).resolve_identity(MemoExtraction(companyName="Acme"))
    assert res.selected is None
    assert res.company_id == "44"


@pytest.mark.asyncio
async def test_phone_unique_locks():
    search = _Search(persons=[{"id": 3, "name": "Ada", "phones": [{"value": "+34600", "primary": True}]}])
    res = await PipedriveIdentityService(search).resolve_identity(MemoExtraction(contactPhone="+34600"))
    assert res.selected is not None
    assert res.selected.contact_id == "3"


def test_search_service_type_hint():
    assert PipedriveSearchService
