import pytest

from app.services.pipedrive.search import PipedriveSearchService, _term_or_empty, primary_phone


class _NoCallClient:
    async def get(self, *a, **k):
        raise AssertionError("search must not call Pipedrive for short terms")


def test_term_min_two_chars():
    assert _term_or_empty("a") == ""
    assert _term_or_empty("  x  ") == ""
    assert _term_or_empty("ab") == "ab"
    assert _term_or_empty("a", exact_match=True) == "a"


@pytest.mark.asyncio
async def test_search_deals_skips_short_term():
    svc = PipedriveSearchService(_NoCallClient())
    assert await svc.search_deals("x") == []
    assert await svc.search_persons(" ") == []


def test_primary_phone_from_v2_array():
    assert primary_phone({"phones": [{"value": "+34600", "primary": True}]}) == "+34600"
    assert primary_phone({"phone": [{"value": "600"}]}) == "600"
    assert primary_phone({}) is None
