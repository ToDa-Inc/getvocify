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


from app.services.coaching.crm_meetings import (  # noqa: E402
    LOST,
    MEETING_BOOKED,
    credit_status_changes,
    lead_status_changes_from_hubspot,
    lead_status_outcomes,
)


def test_lead_status_options_map_by_label_or_value():
    options = [
        {"label": "Converted", "value": "CONVERTED"},
        {"label": "Lost", "value": "lost_custom"},
        {"label": "Not Qualified", "value": "UNQUALIFIED"},
        {"label": "Attempted to contact", "value": "ATTEMPTED_TO_CONTACT"},
        {"label": "Otro", "value": "not_qualified"},
    ]
    assert lead_status_outcomes(options) == {
        "CONVERTED": MEETING_BOOKED, "lost_custom": LOST, "UNQUALIFIED": LOST, "not_qualified": LOST,
    }


def test_lead_status_history_is_read_with_batch_read_only():
    calls = []

    def post(path, body):
        calls.append((path, body))
        return {"results": [{"id": "c1", "propertiesWithHistory": {"hs_lead_status": [
            {"value": "CONVERTED", "timestamp": "2026-10-02T11:00:00Z"},
            {"value": "ATTEMPTED_TO_CONTACT", "timestamp": "2026-10-01T09:00:00Z"},
        ]}}]}

    changes = lead_status_changes_from_hubspot(post, ["c1", "c2"], {"CONVERTED": MEETING_BOOKED})
    assert changes == {"c1": [{"outcome": MEETING_BOOKED, "at": AT("2026-10-02T11:00:00")}], "c2": []}
    assert [path for path, _ in calls] == ["/crm/v3/objects/contacts/batch/read"]
    assert calls[0][1]["propertiesWithHistory"] == ["hs_lead_status"]


def test_converted_is_credited_to_the_last_call_before_it_within_the_window():
    changes = {"c1": [{"outcome": MEETING_BOOKED, "at": AT("2026-10-02T11:00:00")}]}
    memos = [
        {"id": "early", "hubspot_contact_id": "c1", "capture_started_at": "2026-10-01T10:00:00Z"},
        {"id": "booking", "hubspot_contact_id": "c1", "capture_started_at": "2026-10-02T10:40:00Z"},
        {"id": "later", "hubspot_contact_id": "c1", "capture_started_at": "2026-10-05T10:00:00Z"},
    ]
    assert list(credit_status_changes(changes, memos, MEETING_BOOKED)) == ["booking"]
    assert credit_status_changes(changes, memos, LOST) == {}


def test_a_meeting_long_after_the_last_call_credits_nothing_but_a_loss_still_does():
    memos = [{"id": "old", "hubspot_contact_id": "c1", "capture_started_at": "2026-08-01T10:00:00Z"}]
    meeting = {"c1": [{"outcome": MEETING_BOOKED, "at": AT("2026-10-02T11:00:00")}]}
    lost = {"c1": [{"outcome": LOST, "at": AT("2026-10-02T11:00:00")}]}
    assert credit_status_changes(meeting, memos, MEETING_BOOKED) == {}
    assert list(credit_status_changes(lost, memos, LOST)) == ["old"]
