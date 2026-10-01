import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api import memos
from app.api.memos import UploadTranscriptRequest, approve_memo_for_contact, upload_transcript_and_extract


def _upload(**fields):
    supabase = MagicMock()
    insert = supabase.table.return_value.insert
    insert.return_value.execute.return_value.data = [{"id": "memo-1"}]
    with (
        patch("app.services.transcript_sanitize.sanitize_user_transcript", AsyncMock(side_effect=lambda t, *_, **__: t)),
        patch.object(memos, "_curated_field_specs_for_primary_crm", AsyncMock(return_value=None)),
        patch.object(memos, "start_extraction_from_transcript", AsyncMock()),
    ):
        asyncio.run(
            upload_transcript_and_extract(
                UploadTranscriptRequest(transcript="SPEAKER: S1\nhola", interaction_kind="call", **fields),
                supabase=supabase,
                user_id="user-1",
            )
        )
    return insert.call_args.args[0]


def test_a_call_upload_is_born_with_its_contact():
    row = _upload(hubspot_contact_id="879829962968")
    assert row["hubspot_contact_id"] == "879829962968"
    assert row["interaction_kind"] == "call"


def test_without_a_contact_the_column_is_left_alone():
    assert "hubspot_contact_id" not in _upload()


def test_only_hubspot_ids_are_accepted():
    with pytest.raises(ValidationError):
        UploadTranscriptRequest(transcript="x", hubspot_contact_id="https://evil")


def _approve(memo: dict, user_id: str = "user-1"):
    approve = AsyncMock(return_value={"ok": True})
    with (
        patch.object(memos, "_require_readable_memo", return_value=memo),
        patch.object(memos, "approve_memo", approve),
    ):
        result = asyncio.run(approve_memo_for_contact(uuid4(), supabase=MagicMock(), user_id=user_id))
    return result, approve


READY = {"user_id": "user-1", "status": "pending_review", "hubspot_contact_id": "879829962968"}


def test_one_click_approve_sends_exactly_what_auto_approve_sends():
    result, approve = _approve({**READY, "matched_deal_id": "55"})
    assert result == {"ok": True}
    payload = approve.call_args.args[1]
    assert (payload.contact_id, payload.deal_id, payload.skip_deal) == ("879829962968", "55", False)
    assert payload.create_company is False and payload.is_new_deal is False


def test_without_a_deal_it_updates_the_contact_only():
    _, approve = _approve(READY)
    payload = approve.call_args.args[1]
    assert payload.deal_id is None and payload.skip_deal is True


@pytest.mark.parametrize(
    "memo, user_id, code",
    [
        ({**READY, "hubspot_contact_id": None}, "user-1", 409),
        ({**READY, "status": "extracting"}, "user-1", 409),
        ({**READY, "sales_motion_key": "internal"}, "user-1", 409),
        (READY, "manager-2", 403),
    ],
)
def test_anything_that_needs_a_choice_goes_to_review(memo, user_id, code):
    with pytest.raises(HTTPException) as error:
        _approve(memo, user_id=user_id)
    assert error.value.status_code == code
