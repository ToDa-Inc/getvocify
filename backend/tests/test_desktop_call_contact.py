import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api import memos
from app.api.memos import ApproveContactRequest, UploadTranscriptRequest, approve_memo_for_contact, upload_transcript_and_extract
from app.models.memo import MemoExtraction


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


def _approve(memo: dict, user_id: str = "user-1", body=None):
    approve = AsyncMock(return_value={"ok": True})
    with (
        patch.object(memos, "_require_readable_memo", return_value=memo),
        patch.object(memos, "approve_memo", approve),
    ):
        result = asyncio.run(approve_memo_for_contact(uuid4(), body, supabase=MagicMock(), user_id=user_id))
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


def test_the_fields_the_rep_kept_are_what_gets_written():
    kept = MemoExtraction(summary="Llamada", contactName="Zadarma test")
    _, approve = _approve(READY, body=ApproveContactRequest(extraction=kept))
    assert approve.call_args.args[1].extraction == kept


def test_without_choices_the_extraction_is_written_as_extracted():
    _, approve = _approve(READY, body=ApproveContactRequest())
    assert approve.call_args.args[1].extraction is None


def test_the_upload_keeps_the_app_the_call_happened_in():
    assert _upload(call_source="Google Meet")["pipeline_meta"] == {"call_source": "Google Meet"}
    assert "pipeline_meta" not in _upload()


def _picked(key: str, live, source=None, by_channel=False, types=None, kind="meeting", meta=None):
    supabase = MagicMock()
    update = supabase.table.return_value.update
    memo = {"id": "memo-1", "company_id": "co-1", "interaction_kind": kind, "pipeline_meta": meta or {"call_source": "Zoom"}}
    with patch("app.services.playbooks.live.live_version_id", return_value=live), \
            patch("app.services.playbooks.channel_types.live_version_id", return_value=live), \
            patch("app.services.playbooks.channel_types.enabled", return_value=by_channel), \
            patch("app.services.playbooks.channel_types._types", return_value=types or {}):
        memos._pin_picked_type(supabase, memo, key, *([source] if source else []))
    return update.call_args.args[0] if update.called else None


def test_a_type_picked_during_the_call_is_pinned_as_the_reps_own():
    row = _picked("discovery", "v-1")
    assert row["sales_motion_key"] == "discovery" and row["playbook_version_id"] == "v-1"
    assert row["pipeline_meta"]["playbook_pin"]["source"] == "manual"
    assert row["pipeline_meta"]["call_source"] == "Zoom"


def test_internal_needs_no_playbook_and_an_unpublished_pick_is_ignored():
    assert _picked("internal", None)["playbook_version_id"] is None
    assert _picked("negotiation", None) is None


def test_a_type_vocify_suggested_is_pinned_as_live_so_the_call_reading_can_still_correct_it():
    row = _picked("discovery", "v-1", source="vocify")
    assert row["pipeline_meta"]["playbook_pin"]["source"] == "live"
    assert row["playbook_version_id"] == "v-1"


def test_the_upload_says_who_chose_the_type_and_absent_means_the_rep():
    assert UploadTranscriptRequest(transcript="x").type_source == "rep"
    assert UploadTranscriptRequest(transcript="x", type_source="vocify").type_source == "vocify"
    with pytest.raises(ValidationError):
        UploadTranscriptRequest(transcript="x", type_source="ai")


MEETING_TYPES = {
    "demo": {"status": "missing", "applies_to": {"role": "any", "channels": ["meeting"], "contact": "any", "deal_stages": []}},
    "cold": {"status": "published", "applies_to": {"role": "any", "channels": ["call"], "contact": "any", "deal_stages": []}},
}


def test_by_channel_a_type_without_a_playbook_is_pinned_as_a_label():
    row = _picked("demo", None, source="rep", by_channel=True, types=MEETING_TYPES)
    assert row["sales_motion_key"] == "demo" and row["playbook_version_id"] is None
    assert row["pipeline_meta"]["playbook_pin"]["source"] == "manual"


def test_by_channel_a_type_of_another_channel_is_ignored():
    assert _picked("cold", "v-1", source="rep", by_channel=True, types=MEETING_TYPES) is None


def test_by_channel_vocifys_live_guess_never_replaces_a_crm_decision():
    crm = {"playbook_pin": {"source": "crm_rule"}}
    assert _picked("demo", None, source="vocify", by_channel=True, types=MEETING_TYPES, meta=crm) is None
    # The rep's own pick still wins over it.
    assert _picked("demo", None, source="rep", by_channel=True, types=MEETING_TYPES, meta=crm)["sales_motion_key"] == "demo"
