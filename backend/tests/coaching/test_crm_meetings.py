"""Meetings the rep marked in the CRM count as their declaration, credited to the call that booked them."""

from datetime import datetime, timezone

from app.services.coaching.crm_meetings import booked_deals_from_hubspot, credit_calls

AT = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc)  # noqa: E731


def test_the_deal_is_credited_to_the_last_call_before_it_entered_the_stage():
    deals = [{"deal_id": "d1", "entered_at": AT("2026-09-22T12:00:00"), "contact_ids": ["c1"]}]
    memos = [
        {"id": "old", "hubspot_contact_id": "c1", "capture_started_at": "2026-09-01T10:00:00Z"},
        {"id": "first", "hubspot_contact_id": "c1", "capture_started_at": "2026-09-20T10:00:00Z"},
        {"id": "booking", "hubspot_contact_id": "c1", "capture_started_at": "2026-09-22T10:36:00Z"},
        {"id": "after", "hubspot_contact_id": "c1", "capture_started_at": "2026-09-25T10:00:00Z"},
        {"id": "other", "hubspot_contact_id": "c2", "capture_started_at": "2026-09-22T10:00:00Z"},
    ]
    assert list(credit_calls(deals, memos)) == ["booking"]


def test_a_deal_with_no_call_in_the_days_before_credits_nothing():
    deals = [{"deal_id": "d1", "entered_at": AT("2026-09-22T12:00:00"), "contact_ids": ["c1"]}]
    memos = [{"id": "old", "hubspot_contact_id": "c1", "capture_started_at": "2026-08-01T10:00:00Z"}]
    assert credit_calls(deals, memos) == {}


def test_booked_deals_are_read_with_their_contacts():
    calls = []

    def post(path, body):
        calls.append(path)
        if path.endswith("/search"):
            return {"results": [{"id": "d1", "properties": {"hs_v2_date_entered_s1": "2026-09-22T12:00:00Z"}}]}
        return {"results": [{"from": {"id": "d1"}, "to": [{"toObjectId": 77}]}]}

    [deal] = booked_deals_from_hubspot(lambda *a, **k: {}, post, "s1")
    assert deal["contact_ids"] == ["77"] and deal["entered_at"] == AT("2026-09-22T12:00:00")
    assert all("search" in p or "batch/read" in p for p in calls)  # read endpoints only
