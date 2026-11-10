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
        extraction=MemoExtraction(
            contactName="Ada",
            companyName="Acme",
            dealAmount=10,
            raw_extraction={"contact_properties": {"job_title": "Director"}},
        ),
        matched_deals=[],
        selected_deal_id=None,
        allowed_fields=["title", "value", "stage_id"],
        allowed_contact_fields=["name", "job_title"],
        skip_deal=True,
    )
    assert preview.skip_deal is True
    assert preview.is_new_deal is False
    assert all(u.object_type != "deals" for u in preview.proposed_updates)
    assert any(u.object_type == "contacts" for u in preview.proposed_updates)


@pytest.mark.asyncio
async def test_deal_preview_still_lists_contact_fields():
    class _SchemaWithContact(_Schema):
        def map_extraction_to_deal_fields(self, extraction, **k):
            return {"title": extraction.companyName or "Deal"}

    svc = PipedrivePreviewService(_Search(), _SchemaWithContact())
    preview = await svc.build_preview(
        memo_id=uuid4(),
        transcript="hello",
        extraction=MemoExtraction(
            companyName="Acme",
            raw_extraction={"contact_properties": {"job_title": "Director"}},
        ),
        matched_deals=[],
        selected_deal_id="1",
        allowed_fields=["title"],
        allowed_contact_fields=["name", "job_title"],
    )
    assert any(u.object_type == "contacts" and u.field_name == "job_title" for u in preview.proposed_updates)
    assert any(f.object_type == "contacts" for f in preview.available_fields)


@pytest.mark.asyncio
async def test_a_stage_row_shows_the_stage_name_not_its_number():
    class _StageSchema(_Schema):
        def map_extraction_to_deal_fields(self, extraction, **k):
            return {"title": "Existing", "stage_id": 196}

        async def list_stages(self, pipeline_id=None):
            assert pipeline_id == "7"
            return [{"id": 195, "name": "Contactado"}, {"id": 196, "name": "Demo"}]

    class _StageSearch:
        async def get_deal(self, deal_id):
            return {"id": int(deal_id), "title": "Existing", "stage_id": 195, "pipeline_id": 7}

    svc = PipedrivePreviewService(_StageSearch(), _StageSchema())
    preview = await svc.build_preview(
        memo_id=uuid4(),
        transcript="hello",
        extraction=MemoExtraction(companyName="Acme"),
        matched_deals=[],
        selected_deal_id="58848",
        allowed_fields=["title", "stage_id"],
        allowed_contact_fields=[],
    )
    row = next(u for u in preview.proposed_updates if u.field_name == "stage_id")
    assert (row.current_value, row.new_value) == ("Contactado", "Demo")
    assert {"value": "196", "label": "Demo"} in row.options
