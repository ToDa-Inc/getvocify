from uuid import uuid4

import pytest
from app.models.approval import ApprovalPreview
from app.services.preview_targets import resolve_preview_deal_selection


def test_skip_deal_wins_over_existing_deal_id():
    selected, create_new = resolve_preview_deal_selection(
        deal_id="123",
        create_new_deal=False,
        has_selected_contact=True,
        has_contact_candidates=False,
        skip_deal=True,
    )
    assert selected is None
    assert create_new is False


def test_omit_deal_with_contact_still_skips():
    selected, create_new = resolve_preview_deal_selection(
        deal_id=None,
        create_new_deal=False,
        has_selected_contact=True,
        has_contact_candidates=False,
        skip_deal=False,
    )
    assert selected is None
    assert create_new is False


@pytest.mark.asyncio
async def test_build_preview_for_selection_forwards_skip_deal(monkeypatch):
    captured = {}

    class FakeProvider:
        async def find_matching_deals(self, *a, **k):
            return []

        async def resolve_identity(self, *a, **k):
            return None

        async def build_preview(self, **k):
            captured.update(k)
            skip = bool(k.get("skip_deal"))
            return ApprovalPreview(
                memo_id=k["memo_id"],
                transcript_summary="summary",
                selected_contact=None,
                selected_deal=None,
                skip_deal=skip,
                is_new_deal=not skip,
            )

    async def fake_ctx(*a, **k):
        return FakeProvider(), {"id": "c", "provider": "hubspot"}, None, [], [], [], [], None

    async def fake_load(*a, **k):
        return {"contactName": "Ana", "companyName": "Acme", "summary": "Visited Ana"}, "t"

    monkeypatch.setattr("app.services.whatsapp.processor._crm_context", fake_ctx)
    monkeypatch.setattr("app.services.whatsapp.processor._load_memo_extraction", fake_load)

    from app.services.whatsapp.processor import _build_preview_for_selection

    preview, *_rest = await _build_preview_for_selection(
        None, "user-1", str(uuid4()), skip_deal=True
    )
    assert captured.get("skip_deal") is True
    assert captured.get("create_new_deal") is False
    assert preview.skip_deal is True
    assert preview.is_new_deal is False
