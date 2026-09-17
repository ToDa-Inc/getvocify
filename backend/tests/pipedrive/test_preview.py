from uuid import uuid4

import pytest

from app.models.memo import MemoExtraction
from app.services.pipedrive.preview import PipedrivePreviewService


class _Schema:
    async def resolve_stage_id(self, *a, **k):
        return "5"

    async def map_extraction_to_deal_fields(self, extraction, **k):
        out = {"title": extraction.companyName or "Deal"}
        if k.get("stage_id"):
            out["stage_id"] = int(k["stage_id"])
        return out

    async def get_curated_field_specs(self, names, object_type="deals"):
        return [{"name": n, "label": n, "type": "string"} for n in names]


class _Search:
    async def get_deal(self, deal_id):
        return {"id": int(deal_id), "title": "Existing"}


@pytest.mark.asyncio
async def test_skip_deal_preview_has_no_deal_fields():
    svc = PipedrivePreviewService(_Search(), _Schema())
    preview = await svc.build_preview(
        memo_id=uuid4(),
        transcript="hello",
        extraction=MemoExtraction(contactName="Ada", companyName="Acme", dealAmount=10),
        matched_deals=[],
        selected_deal_id=None,
        allowed_fields=["title", "value", "stage_id"],
        skip_deal=True,
    )
    assert preview.skip_deal is True
    assert preview.is_new_deal is False
    assert all(u.object_type != "deals" for u in preview.proposed_updates)
    assert any(u.object_type == "contacts" for u in preview.proposed_updates)
