from uuid import uuid4

import pytest

from app.models.approval import ContactMatch
from app.models.memo import MemoExtraction
from app.services.pipedrive.preview import PipedrivePreviewService


class _Schema:
    async def resolve_stage_id(self, *a, **k):
        return "5"

    def map_extraction_to_deal_fields(self, extraction, **k):
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
    assert "deals" not in {f.object_type for f in preview.available_fields}
    assert {f.name for f in preview.available_fields if f.object_type == "contacts"} >= {"emails", "phones"}


@pytest.mark.asyncio
async def test_person_page_lists_contact_and_company_fields():
    """Same allowlist rule as HubSpot: skip_deal shows people and the linked org, not deals."""
    org_field = "ad74fad4499ad8e6347dc8cb6b86cd0b6998cab6"
    svc = PipedrivePreviewService(_Search(), _Schema())
    preview = await svc.build_preview(
        memo_id=uuid4(),
        transcript="hello",
        extraction=MemoExtraction(
            contactName="Ada",
            raw_extraction={"company_properties": {org_field: "1339"}},
        ),
        matched_deals=[],
        selected_deal_id=None,
        allowed_fields=["title", "value"],
        allowed_contact_fields=["name", "emails", "phones"],
        allowed_company_fields=["name", org_field],
        selected_contact=ContactMatch(contact_id="13", company_id="9", email=""),
        skip_deal=True,
    )
    assert "deals" not in {f.object_type for f in preview.available_fields}
    assert {f.name for f in preview.available_fields if f.object_type == "contacts"} >= {"emails", "phones"}
    assert any(
        u.object_type == "companies" and u.field_name == org_field and u.new_value == "1339"
        for u in preview.proposed_updates
    )
    assert not any(f.object_type == "companies" and f.name == org_field for f in preview.available_fields)


@pytest.mark.asyncio
async def test_deal_preview_still_lists_contact_fields():
    svc = PipedrivePreviewService(_Search(), _Schema())
    preview = await svc.build_preview(
        memo_id=uuid4(),
        transcript="hello",
        extraction=MemoExtraction(contactName="Ada", companyName="Acme"),
        matched_deals=[],
        selected_deal_id="2",
        allowed_fields=["title", "value"],
        allowed_contact_fields=["name", "emails"],
        allowed_company_fields=["name"],
        skip_deal=False,
    )
    assert {f.object_type for f in preview.available_fields} >= {"deals", "contacts"}
