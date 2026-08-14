"""
Characterization test for HubSpotAssociationService.get_associations().

Written after finding that the parser expected `objectId`/`id` on each result,
or a nested `to[].toObjectId`, but HubSpot's real response for
GET /crm/v4/objects/{type}/{id}/associations/{toType} puts `toObjectId`
directly on each result item (confirmed against HubSpot's own OpenAPI schema:
MultiAssociatedObjectWithLabel, `required: [associationTypes, toObjectId]`).

The old parser matched none of its checks against that real shape, so it
returned [] for every association lookup in the app - contact<->deal,
contact<->company, deal<->contact, deal<->company - indistinguishable from a
genuinely empty association. A Fase 0 characterization test on this exact
response shape would have caught it the day it was introduced.
"""

from app.services.hubspot.associations import HubSpotAssociationService


class _StubClient:
    """Stands in for HubSpotClient - get_associations() only calls .get()."""

    def __init__(self, response):
        self._response = response

    async def get(self, path, params=None):
        return self._response


# The real shape, verbatim against HubSpot's documented schema for this
# endpoint - not a guess, not the shape a *different* (batch) endpoint returns.
REAL_V4_ASSOCIATIONS_RESPONSE = {
    "results": [
        {
            "toObjectId": "801234567",
            "associationTypes": [{"category": "HUBSPOT_DEFINED", "typeId": 4, "label": None}],
        },
        {
            "toObjectId": "801234999",
            "associationTypes": [{"category": "HUBSPOT_DEFINED", "typeId": 4, "label": None}],
        },
    ],
    "paging": {},
}


async def test_get_associations_parses_real_v4_shape():
    """toObjectId sits directly on each result - must be extracted, not [].
    """
    service = HubSpotAssociationService(_StubClient(REAL_V4_ASSOCIATIONS_RESPONSE))

    ids = await service.get_associations("contacts", "12345", "deals")

    assert ids == ["801234567", "801234999"]


async def test_get_associations_genuinely_empty_results():
    """A real 'no associations' response (empty results array) stays []."""
    service = HubSpotAssociationService(_StubClient({"results": [], "paging": {}}))

    ids = await service.get_associations("contacts", "12345", "deals")

    assert ids == []


async def test_get_associations_missing_results_key():
    """A malformed/unexpected response body degrades to [], not a crash."""
    service = HubSpotAssociationService(_StubClient({}))

    ids = await service.get_associations("contacts", "12345", "deals")

    assert ids == []
