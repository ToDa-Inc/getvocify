"""The preview does not search every contact sharing a name when the contact is already known."""

import asyncio
from types import SimpleNamespace

from app.api.memos import _deals_and_identity


class _Provider:
    def __init__(self, identity, deals):
        self.identity, self.deals = identity, deals
        self.searched = 0
        self.resolved_with = None

    async def resolve_identity(self, extraction, **kwargs):
        self.resolved_with = kwargs["preferred_contact_id"]
        return self.identity

    async def find_matching_deals(self, extraction, **kwargs):
        self.searched += 1
        return self.deals


def _run(provider, contact_id):
    return asyncio.run(_deals_and_identity(provider, object(), pipeline_id=None, contact_id=contact_id))


def _identity(deals):
    return SimpleNamespace(selected=SimpleNamespace(deal_matches=deals))


def test_a_known_contact_with_linked_deals_skips_the_name_search():
    provider = _Provider(_identity(["d1"]), deals=["fuzzy"])
    matches, identity = _run(provider, "c1")
    assert matches == [] and provider.searched == 0
    assert identity.selected.deal_matches == ["d1"] and provider.resolved_with == "c1"


def test_a_known_contact_without_deals_still_gets_the_name_matches():
    provider = _Provider(_identity([]), deals=["fuzzy"])
    matches, _ = _run(provider, "c1")
    assert matches == ["fuzzy"] and provider.searched == 1


def test_no_contact_searches_both_ways():
    provider = _Provider(_identity([]), deals=["fuzzy"])
    matches, identity = _run(provider, None)
    assert matches == ["fuzzy"] and provider.searched == 1 and identity is not None


def test_a_crm_without_identity_falls_back_to_the_name_matches():
    provider = _Provider(None, deals=["fuzzy"])
    matches, identity = _run(provider, "c1")
    assert matches == ["fuzzy"] and identity is None
