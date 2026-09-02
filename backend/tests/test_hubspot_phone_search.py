from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.hubspot.search import (
    HubSpotSearchService,
    phone_digits_match,
    phone_search_variants,
)
from app.services.hubspot.types import Filter


def _contact(cid: str, **props) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "id": cid,
        "properties": props,
        "createdAt": now,
        "updatedAt": now,
        "archived": False,
    }


class TestPhoneSearchVariants:
    def test_includes_e164_national_and_international_digits(self):
        variants = phone_search_variants("+34648739267")
        assert "+34648739267" in variants
        assert "34648739267" in variants
        assert "0034648739267" in variants
        assert "648739267" in variants
        assert "0648739267" in variants

    def test_includes_spaced_forms_hubspot_commonly_stores(self):
        variants = phone_search_variants("+34648739267")
        assert "+34 648 73 92 67" in variants
        assert "648 73 92 67" in variants
        assert "+34 648 739 267" in variants

    def test_strips_separators_before_expanding(self):
        spaced = phone_search_variants("+34 648-73.92 67")
        compact = phone_search_variants("+34648739267")
        assert set(spaced) == set(compact)

    def test_empty_or_too_short_is_empty(self):
        assert phone_search_variants("") == []
        assert phone_search_variants("12345") == []


class TestPhoneDigitsMatch:
    def test_matches_despite_spaces_dashes_and_missing_plus(self):
        assert phone_digits_match("+34648739267", "+34 648 73 92 67")
        assert phone_digits_match("+34648739267", "648739267")
        assert phone_digits_match("+34648739267", "0648739267")

    def test_rejects_a_different_number(self):
        assert not phone_digits_match("+34648739267", "+34600111222")


class TestFindContactsByPhone:
    @pytest.mark.asyncio
    async def test_eq_searches_e164_and_national_not_only_contains_token(self):
        svc = HubSpotSearchService(client=MagicMock())
        svc.search = AsyncMock(return_value=[])

        await svc.find_contacts_by_phone("+34648739267")

        needles = []
        for call in svc.search.await_args_list:
            for filt in call.args[1]:
                assert isinstance(filt, Filter)
                needles.append((filt.operator, filt.value))
        eq_values = {v for op, v in needles if op == "EQ"}
        assert "+34648739267" in eq_values
        assert "648739267" in eq_values
        assert any(op == "CONTAINS_TOKEN" for op, _ in needles)

    @pytest.mark.asyncio
    async def test_keeps_spaced_hubspot_number_and_drops_unrelated(self):
        svc = HubSpotSearchService(client=MagicMock())
        svc.search = AsyncMock(
            return_value=[
                _contact("keep", phone="+34 648 73 92 67"),
                _contact("drop", phone="+34 600 111 222"),
            ]
        )

        hits = await svc.find_contacts_by_phone("+34648739267")

        assert [c.id for c in hits] == ["keep"]
