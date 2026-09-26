"""What Vocify heard on a call reaches the priority list: confirmed pain, agreed meetings, a real conversation."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.hoy.memo_facts import apply_memo_facts, memo_facts_by_contact
from app.services.hoy.priority import rank_candidates

NOW = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)


def memo(memo_id, contact, created_at, *, pain=None, agreed=None, starts_at=None, legacy_pain=None):
    intelligence = {"pain_confirmed": pain, "meeting": {"agreed": agreed, "starts_at": starts_at}}
    extraction = {"intelligence": intelligence}
    if legacy_pain is not None:
        extraction["pain_confirmed"] = legacy_pain
    return {"id": memo_id, "hubspot_contact_id": contact, "created_at": created_at, "extraction": extraction}


def candidate(contact, **extra):
    return {"connection_id": "c1", "contact_id": contact, "deal_id": None, "coverage": "complete", "contacted": False, **extra}


def test_recent_confirmed_pain_ranks_first_with_its_evidence():
    facts = memo_facts_by_contact([memo("m1", "42", "2026-09-24T09:00:00Z", pain=True)], now=NOW)
    ranked = rank_candidates(apply_memo_facts([candidate("7"), candidate("42")], facts), NOW)
    assert ranked[0]["contact_id"] == "42"
    assert ranked[0]["tier"] == 1
    assert ranked[0]["evidence_refs"] == ["m1"]


def test_pain_stored_on_the_extraction_itself_also_counts():
    facts = memo_facts_by_contact([memo("m1", "42", "2026-09-24T09:00:00Z", legacy_pain=True)], now=NOW)
    assert facts["42"]["pain_confirmed"] is True


def test_an_agreed_meeting_without_date_stops_another_prospecting_call():
    facts = memo_facts_by_contact(
        [
            memo("m2", "42", "2026-09-25T09:00:00Z", agreed=True),
            memo("m1", "42", "2026-09-24T09:00:00Z", pain=True),
        ],
        now=NOW,
    )
    assert rank_candidates(apply_memo_facts([candidate("42")], facts), NOW) == []


def test_a_future_meeting_shows_as_scheduled():
    facts = memo_facts_by_contact(
        [memo("m1", "42", "2026-09-25T09:00:00Z", pain=True, agreed=True, starts_at="2026-09-30T10:00:00Z")],
        now=NOW,
    )
    [row] = rank_candidates(apply_memo_facts([candidate("42")], facts), NOW)
    assert row["tier"] == 4
    assert row["scheduled_at"] == "2026-09-30T10:00:00Z"


def test_a_meeting_that_already_happened_no_longer_hides_the_contact():
    facts = memo_facts_by_contact(
        [memo("m1", "42", "2026-09-10T09:00:00Z", agreed=True, starts_at="2026-09-15T10:00:00Z")],
        now=NOW,
    )
    [row] = rank_candidates(apply_memo_facts([candidate("42")], facts), NOW)
    assert row["reason"] == "followup_pending"


def test_a_captured_conversation_means_the_contact_was_called():
    facts = memo_facts_by_contact([memo("m1", "42", "2026-09-01T09:00:00Z")], now=NOW)
    [row] = rank_candidates(apply_memo_facts([candidate("42")], facts), NOW)
    assert row["never_called"] is False


def test_old_pain_does_not_jump_the_queue():
    facts = memo_facts_by_contact([memo("m1", "42", "2026-08-01T09:00:00Z", pain=True)], now=NOW)
    [row] = rank_candidates(apply_memo_facts([candidate("42")], facts), NOW)
    assert row["tier"] == 3


def test_contacts_without_memos_are_untouched():
    rows = [candidate("7")]
    assert apply_memo_facts(rows, {}) == rows
