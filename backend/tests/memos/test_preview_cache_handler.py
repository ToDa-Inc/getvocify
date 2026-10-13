"""The preview is built once per memo state and served from the cache after that, without ever
skipping the permission check or the memo write the request owes."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import HTTPException

from app.api import memos as api
from app.models.approval import ApprovalPreview, DealMatch

MEMO_ID = "11111111-1111-1111-1111-111111111111"
OWNER = "rep-1"


def _memo(**over):
    base = {
        "id": MEMO_ID, "user_id": OWNER, "status": "pending_review", "extraction": {"summary": "s"},
        "transcript": "t", "hubspot_contact_id": "c-1", "hubspot_deal_id": None,
    }
    return {**base, **over}


def _preview(deal_name=None):
    deal = DealMatch(deal_id="d1", deal_name=deal_name, last_updated="x", match_confidence=1.0, match_reason="r") if deal_name else None
    return ApprovalPreview(memo_id=UUID(MEMO_ID), transcript_summary="s", selected_deal=deal)


class Harness:
    def __init__(self, memo=None):
        self.memo = memo or _memo()
        self.builds = AsyncMock(side_effect=lambda *a, **k: _preview(k.get("deal_id") and "Deal"))
        self.writes = MagicMock()

    def read(self, _sb, _memo_id, user_id):
        if user_id != OWNER:
            raise HTTPException(status_code=404, detail="Memo not found")
        return dict(self.memo)

    def get(self, user_id=OWNER, **kwargs):
        with (
            patch.object(api, "_require_readable_memo", self.read),
            patch.object(api, "_build_approval_preview", self.builds),
            patch.object(api, "update_memo_row", self.writes),
        ):
            return asyncio.run(api.get_approval_preview(UUID(MEMO_ID), supabase=object(), user_id=user_id, **kwargs))


def test_the_same_memo_state_is_built_once():
    h = Harness()
    first, second = h.get(), h.get()
    assert h.builds.await_count == 1
    assert first == second


def test_what_a_caller_changes_in_its_copy_never_reaches_the_next():
    h = Harness()
    h.get().transcript_summary = "tampered"
    assert h.get().transcript_summary == "s"


def test_fresh_always_builds():
    h = Harness()
    h.get()
    h.get(fresh=True)
    assert h.builds.await_count == 2


def test_a_changed_memo_is_built_again():
    h = Harness()
    h.get()
    h.memo = _memo(extraction={"summary": "edited"})
    h.get()
    assert h.builds.await_count == 2


def test_another_deal_or_contact_is_its_own_preview():
    h = Harness()
    h.get()
    h.get(deal_id="d9")
    h.get(contact_id="c-9")
    assert h.builds.await_count == 3


def test_the_permission_check_runs_even_when_the_preview_is_cached():
    h = Harness()
    h.get()
    with pytest.raises(HTTPException) as denied:
        h.get(user_id="stranger")
    assert denied.value.status_code == 404
    assert h.builds.await_count == 1


def test_a_memo_with_a_deal_is_written_on_every_request_cached_or_not():
    h = Harness(_memo(hubspot_deal_id="d1"))
    h.get()
    h.get()
    assert h.builds.await_count == 1
    assert h.writes.call_count == 2
    assert h.writes.call_args.args[2] == {"matched_deal_id": "d1", "matched_deal_name": "Deal", "is_new_deal": False}


def test_creating_a_new_deal_is_written_too():
    h = Harness()
    h.get(create_new_deal=True)
    assert h.writes.call_args.args[2] == {"matched_deal_id": None, "matched_deal_name": None, "is_new_deal": True}


class TestPrewarm:
    def _run(self, h, memo_id=MEMO_ID, user_id=OWNER):
        with (
            patch.object(api, "_require_readable_memo", h.read),
            patch.object(api, "_build_approval_preview", h.builds),
        ):
            asyncio.run(api.prewarm_approval_preview(object(), memo_id, user_id))

    def test_a_ready_memo_with_a_contact_is_built_ahead_and_the_request_finds_it(self):
        h = Harness()
        self._run(h)
        assert h.builds.await_count == 1
        # The prewarm and a later request share the cache only if they are built the same way.
        api._PREVIEW_CACHE._items  # noqa: B018
        with (
            patch.object(api, "_require_readable_memo", h.read),
            patch.object(api, "_build_approval_preview", h.builds),
            patch.object(api, "update_memo_row", h.writes),
        ):
            asyncio.run(api.get_approval_preview(UUID(MEMO_ID), contact_id="c-1", supabase=object(), user_id=OWNER))
        assert h.builds.await_count == 1

    @pytest.mark.parametrize(
        "memo",
        [
            _memo(hubspot_contact_id=None),
            _memo(status="approved"),
            _memo(status="extracting"),
            _memo(extraction=None),
        ],
    )
    def test_it_does_not_build_for_a_memo_the_review_would_not_open(self, memo):
        h = Harness(memo)
        self._run(h)
        h.builds.assert_not_awaited()

    def test_a_failure_is_swallowed_and_leaves_the_request_to_build_it(self):
        h = Harness()
        h.builds = AsyncMock(side_effect=RuntimeError("crm down"))
        self._run(h)  # does not raise
        h.builds = AsyncMock(side_effect=lambda *a, **k: _preview())
        h.get()
        assert h.builds.await_count == 1
