"""Skipping a follow-up draft: only the author, only a ready draft, reversible, never regenerated."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import followup as followup_api
from app.models.followup import FollowupSkipRequest
from app.services.followup import read_followup_preference
from app.services.followup_logic import LISTABLE_STATUSES, should_generate, skip_followup, unskip_followup

NOW = datetime(2026, 10, 1, 21, 16, tzinfo=timezone.utc)
READY = {"status": "ready", "subject": "Caso", "body": "Hola Marta"}


def test_a_skipped_draft_keeps_its_text_and_can_come_back():
    skipped = skip_followup(READY, NOW)
    assert skipped["status"] == "skipped" and skipped["body"] == "Hola Marta"
    assert unskip_followup(skipped) == READY


def test_a_skipped_draft_is_never_regenerated_nor_listed_as_pending():
    assert should_generate(skip_followup(READY, NOW), NOW) is False
    assert "skipped" not in LISTABLE_STATUSES


@pytest.mark.parametrize("status", ["generating", "sent", "unavailable"])
def test_only_a_ready_draft_can_be_skipped(status):
    with pytest.raises(ValueError):
        skip_followup({"status": status}, NOW)


def _skip(memo, user_id="rep-1", undo=False):
    supabase = MagicMock()
    with patch.object(followup_api, "_require_readable_memo", return_value=memo):
        view = asyncio.run(
            followup_api.skip_followup_draft(uuid4(), FollowupSkipRequest(undo=undo), supabase=supabase, user_id=user_id)
        )
    return view, supabase.table.return_value.update.call_args


def test_the_author_skips_and_restores():
    memo = {"user_id": "rep-1", "followup": READY, "extraction": {"contactName": "Marta"}}
    view, update = _skip(memo)
    assert view["status"] == "skipped" and update.args[0]["followup"]["status"] == "skipped"
    view, _ = _skip({**memo, "followup": skip_followup(READY, NOW)}, undo=True)
    assert view["status"] == "ready"


def test_a_manager_cannot_skip_a_reps_draft():
    with pytest.raises(HTTPException) as error:
        _skip({"user_id": "rep-1", "followup": READY}, user_id="manager-2")
    assert error.value.status_code == 403


def test_skipping_twice_is_a_conflict():
    with pytest.raises(HTTPException) as error:
        _skip({"user_id": "rep-1", "followup": skip_followup(READY, NOW)})
    assert error.value.status_code == 409


def test_drafts_stay_on_unless_the_rep_turned_them_off():
    def client(rows=None, error=None):
        supabase = MagicMock()
        query = supabase.table.return_value.select.return_value.eq.return_value.limit.return_value
        if error:
            query.execute.side_effect = error
        else:
            query.execute.return_value.data = rows
        return supabase

    assert read_followup_preference(client([{"followup_suggestions": False}]), "u") is False
    assert read_followup_preference(client([{"followup_suggestions": True}]), "u") is True
    assert read_followup_preference(client([]), "u") is True
    assert read_followup_preference(client(error=Exception("column missing")), "u") is True
