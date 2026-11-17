"""A preview's HubSpot lookups for several contacts run at the same time, not one after another.

On 2026-11-17 a call naming only "José" matched 5 contacts and the preview spent ~1.5 s fetching each
one's company in turn, with the island waiting.
"""

import asyncio

from app.services.hubspot.contact_identity import _candidates_from_contacts, _deal_matches_for_contact
from app.services.hubspot.types import HubSpotContact


class Clock:
    def __init__(self):
        self.in_flight = 0
        self.most = 0

    async def call(self, value):
        self.in_flight += 1
        self.most = max(self.most, self.in_flight)
        await asyncio.sleep(0.01)
        self.in_flight -= 1
        return value


class Associations:
    def __init__(self, clock, links):
        self.clock, self.links = clock, links

    async def get_associations(self, from_type, object_id, to_type):
        return await self.clock.call(self.links.get((object_id, to_type), []))


class Client:
    def __init__(self, clock):
        self.clock = clock

    async def get(self, path, params=None):
        object_id = path.rsplit("/", 1)[-1]
        if "/companies/" in path:
            return await self.clock.call({"id": object_id, "properties": {"name": f"Company {object_id}"}})
        if object_id == "bad":
            await self.clock.call(None)
            raise RuntimeError("deal read failed")
        return await self.clock.call({"id": object_id, "properties": {"dealname": f"Deal {object_id}"}})


class Search:
    def __init__(self, clock):
        self.client = Client(clock)


def test_every_candidate_company_is_looked_up_at_once_and_kept_in_order():
    clock = Clock()
    links = {(str(i), "companies"): [f"c{i}"] for i in range(5)}
    contacts = [HubSpotContact(id=str(i), properties={"firstname": "José"}, createdAt="2026-01-01T00:00:00Z", updatedAt="2026-01-01T00:00:00Z") for i in range(5)]

    out = asyncio.run(
        _candidates_from_contacts(
            contacts, search=Search(clock), associations=Associations(clock, links), match_reason="name", confidence=0.4
        )
    )

    assert [m.company_name for m in out] == [f"Company c{i}" for i in range(5)]
    assert clock.most == 5


def test_a_contacts_deals_are_read_at_once_and_one_failing_read_is_only_counted():
    clock = Clock()
    links = {("k", "deals"): ["d1", "bad", "d2"]}

    deals = asyncio.run(
        _deal_matches_for_contact(
            Associations(clock, links),
            Search(clock),
            "k",
            contact_name="José",
            contact_email="",
            company_name=None,
            limit_deals=5,
            pipeline_id=None,
        )
    )

    assert [d.deal_id for d in deals] == ["d1", "d2"]
    assert clock.most == 3


def test_a_locked_contact_is_not_looked_up_again_and_the_company_is_read_once():
    """A contact with no deals (2026-11-17, 12:26): the fuzzy deal search looked the contact up again by name
    and searched the company twice (with and without the pipeline filter), and HubSpot answered 429."""
    from app.models.memo import MemoExtraction
    from app.services.hubspot.matching import HubSpotMatchingService

    calls = []

    class Search:
        async def search(self, object_type, filters, properties=None, limit=10):
            calls.append((object_type, filters[0].propertyName))
            if object_type == "companies":
                return [{"id": "co1"}]
            return []

    class Assoc:
        async def get_associations(self, from_type, object_id, to_type):
            calls.append(("assoc", object_id))
            return ["d9"]

    class Client:
        async def post(self, path, data=None):
            calls.append(("batch", path))
            return {"results": [{"id": "d9", "properties": {"dealname": "Other", "pipeline": "other"}}]}

    service = HubSpotMatchingService(Client(), Search(), Assoc())

    async def no_lookup(*a, **k):
        raise AssertionError("the locked contact was looked up again")

    service.resolve_contact_anchor = no_lookup
    anchor = type("Anchor", (), {"deal_matches": []})()
    extraction = MemoExtraction(companyName="Acme", contactName="José")

    deals = asyncio.run(service.find_matching_deals(extraction, limit=5, pipeline_id="main", known_anchor=anchor))

    # Filtered out by the pipeline first, then offered by the retry without it: the same deal, read once.
    assert [d.deal_id for d in deals] == ["d9"]
    assert calls.count(("companies", "name")) == 1
    assert calls.count(("batch", "/crm/v3/objects/deals/batch/read")) == 1


def test_a_deal_name_is_searched_once_for_the_pipeline_and_the_retry_without_it():
    from app.models.memo import MemoExtraction
    from app.services.hubspot.matching import HubSpotMatchingService

    searches = []

    class Search:
        async def search(self, object_type, filters, properties=None, limit=10):
            searches.append((object_type, filters[0].operator, filters[0].value, len(filters)))
            if object_type == "deals" and filters[0].operator == "CONTAINS_TOKEN" and filters[0].value == "Acme Labs":
                return [
                    {"id": "off", "properties": {"dealname": "Acme Labs renewal", "pipeline": "other"}},
                    {"id": "on", "properties": {"dealname": "Acme Labs pilot", "pipeline": "main"}},
                ]
            return []

    class Assoc:
        async def get_associations(self, *a):
            return []

    service = HubSpotMatchingService(object(), Search(), Assoc())
    anchor = type("Anchor", (), {"deal_matches": []})()

    deals = asyncio.run(
        service.find_matching_deals(MemoExtraction(companyName="Acme Labs"), limit=3, pipeline_id="main", known_anchor=anchor)
    )

    # The deal in the account's pipeline is offered, and every deal search went to HubSpot once, without the filter.
    assert [d.deal_id for d in deals] == ["on"]
    deal_searches = [s for s in searches if s[0] == "deals"]
    assert len(deal_searches) == len(set(deal_searches)) and all(n == 1 for *_, n in deal_searches)


def test_without_a_deal_in_the_pipeline_the_other_pipelines_are_offered_as_before():
    from app.models.memo import MemoExtraction
    from app.services.hubspot.matching import HubSpotMatchingService

    class Search:
        async def search(self, object_type, filters, properties=None, limit=10):
            if object_type == "deals" and filters[0].value == "Acme Labs":
                return [{"id": "off", "properties": {"dealname": "Acme Labs renewal", "pipeline": "other"}}]
            return []

    class Assoc:
        async def get_associations(self, *a):
            return []

    service = HubSpotMatchingService(object(), Search(), Assoc())
    anchor = type("Anchor", (), {"deal_matches": []})()
    deals = asyncio.run(
        service.find_matching_deals(MemoExtraction(companyName="Acme Labs"), limit=3, pipeline_id="main", known_anchor=anchor)
    )
    assert [d.deal_id for d in deals] == ["off"]
