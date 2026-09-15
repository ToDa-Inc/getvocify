from uuid import uuid4

import pytest
from app.models.memo import MemoExtraction
from app.services.hubspot.preview import HubSpotPreviewService
from app.services.whatsapp.copy import briefing_text


class _Boom:
    async def map_extraction_to_properties_with_stage(self, *a, **k):
        raise AssertionError("skip_deal must not map deal properties")

    async def get(self, *a, **k):
        raise AssertionError("skip_deal must not fetch a deal")

    async def get_multi_object_field_specs(self, **k):
        raise RuntimeError("no schema")

    async def get_deal_schema(self):
        raise RuntimeError("no schema")


@pytest.mark.asyncio
async def test_skip_deal_survives_without_locked_contact():
    svc = HubSpotPreviewService(client=None, deal_service=_Boom(), schema_service=_Boom())
    preview = await svc.build_preview(
        memo_id=uuid4(),
        transcript="Visited Ana at Acme about the renewal today",
        extraction=MemoExtraction(
            contactName="Ana",
            companyName="Acme",
            dealAmount=50000,
            summary="Visited Ana at Acme about the renewal today",
        ),
        matched_deals=[],
        selected_deal_id=None,
        create_new_deal=False,
        selected_contact=None,
        skip_deal=True,
    )
    assert preview.skip_deal is True
    assert preview.is_new_deal is False
    assert preview.selected_deal is None
    assert not any((u.object_type or "deals") == "deals" for u in preview.proposed_updates)
    text = briefing_text(preview)
    assert "Solo contacto" in text
    assert "Deal · Nuevo" not in text
