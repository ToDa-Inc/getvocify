"""Tests for meeting attendee extraction and enrichment."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.meetings.attendees import (
    extract_attendees,
    enrich_attendees_with_hubspot,
    _is_room,
)


class TestAttendeeExtraction:
    """Test attendee extraction from calendar events."""

    def test_extract_attendees_from_google_event(self):
        """Extract attendees from Google Calendar event."""
        raw_event = {
            "attendees": [
                {"email": "alice@company.com", "displayName": "Alice Smith", "resource": False},
                {"email": "bob@company.com", "displayName": "Bob Jones", "resource": False},
                {"email": "room.calendar@calendar.google.com", "resource": True},  # Should be filtered
            ],
            "organizer": {"email": "charlie@company.com", "displayName": "Charlie Brown"},
        }
        attendees = extract_attendees(raw_event, rep_email="charlie@company.com")
        assert len(attendees) == 2
        emails = {a["email"] for a in attendees}
        assert emails == {"alice@company.com", "bob@company.com"}
        assert attendees[0]["name"] == "Alice Smith"

    def test_extract_attendees_from_graph_event(self):
        """Extract attendees from Microsoft Graph event (different format)."""
        raw_event = {
            "attendees": [
                {"emailAddress": {"address": "alice@company.com"}, "displayName": "Alice"},
                {"type": "resource"},  # Resource, should be filtered
            ],
            "organizer": {"emailAddress": {"address": "bob@company.com"}},
        }
        attendees = extract_attendees(raw_event)
        assert len(attendees) == 2
        emails = {a["email"] for a in attendees}
        assert emails == {"alice@company.com", "bob@company.com"}

    def test_filter_rep_themselves(self):
        """Rep's own email should not be in attendee list."""
        raw_event = {
            "attendees": [
                {"email": "alice@company.com", "displayName": "Alice"},
                {"email": "rep@company.com", "displayName": "Rep"},
            ],
            "organizer": {"email": "rep@company.com"},
        }
        attendees = extract_attendees(raw_event, rep_email="rep@company.com")
        assert len(attendees) == 1
        assert attendees[0]["email"] == "alice@company.com"

    def test_filter_rooms_and_resources(self):
        """Rooms and resources should be filtered out."""
        raw_event = {
            "attendees": [
                {"email": "alice@company.com", "displayName": "Alice"},
                {"email": "room.calendar@calendar.google.com", "displayName": "Conference Room", "resource": True},
                {"email": "resource@company.com", "type": "resource", "displayName": "Resource"},
            ],
        }
        attendees = extract_attendees(raw_event)
        assert len(attendees) == 1
        assert attendees[0]["email"] == "alice@company.com"

    def test_dedupe_by_email(self):
        """Duplicate emails should be deduplicated (case-insensitive)."""
        raw_event = {
            "attendees": [
                {"email": "alice@company.com", "displayName": "Alice"},
                {"email": "ALICE@COMPANY.COM", "displayName": "Alice Upper"},  # Duplicate
                {"email": "bob@company.com", "displayName": "Bob"},
            ],
        }
        attendees = extract_attendees(raw_event)
        assert len(attendees) == 2
        emails = {a["email"] for a in attendees}
        assert emails == {"alice@company.com", "bob@company.com"}

    def test_cap_at_max_attendees(self):
        """Attendee list should be capped at MAX_ATTENDEES (12)."""
        attendees_data = [
            {"email": f"attendee{i}@company.com", "displayName": f"Person {i}"}
            for i in range(15)
        ]
        raw_event = {"attendees": attendees_data}
        attendees = extract_attendees(raw_event)
        assert len(attendees) == 12

    def test_missing_displayname_ok(self):
        """Attendees without displayName should have name=None."""
        raw_event = {
            "attendees": [
                {"email": "alice@company.com"},
                {"email": "bob@company.com", "displayName": "Bob"},
            ],
        }
        attendees = extract_attendees(raw_event)
        alice = next(a for a in attendees if a["email"] == "alice@company.com")
        bob = next(a for a in attendees if a["email"] == "bob@company.com")
        assert alice["name"] is None
        assert bob["name"] == "Bob"

    def test_empty_event(self):
        """Empty or None event should return empty list."""
        assert extract_attendees({}) == []
        assert extract_attendees(None) == []
        assert extract_attendees({"attendees": []}) == []

    def test_organizer_included(self):
        """Organizer should be included in attendee list."""
        raw_event = {
            "attendees": [
                {"email": "alice@company.com", "displayName": "Alice"},
            ],
            "organizer": {"email": "organizer@company.com", "displayName": "Organizer"},
        }
        attendees = extract_attendees(raw_event)
        assert len(attendees) == 2
        emails = {a["email"] for a in attendees}
        assert emails == {"alice@company.com", "organizer@company.com"}

    def test_organizer_not_duplicated(self):
        """If organizer is in attendees, should not be duplicated."""
        raw_event = {
            "attendees": [
                {"email": "alice@company.com", "displayName": "Alice"},
                {"email": "org@company.com", "displayName": "Organizer"},
            ],
            "organizer": {"email": "org@company.com"},
        }
        attendees = extract_attendees(raw_event)
        assert len(attendees) == 2
        emails = [a["email"] for a in attendees]
        assert emails.count("org@company.com") == 1


class TestRoomDetection:
    """Test room/resource detection."""

    def test_google_room_by_resource_flag(self):
        """Google rooms marked with resource=true should be detected."""
        assert _is_room({"resource": True}, "room@company.com")

    def test_google_room_by_domain(self):
        """Google rooms with .calendar.google.com domain should be detected."""
        # Note: matching email.endswith(".calendar.google.com") - email format like 'uuid.calendar.google.com'
        assert _is_room({}, "uuid123.calendar.google.com")

    def test_graph_room_by_type(self):
        """Microsoft Graph rooms marked with type='resource' should be detected."""
        assert _is_room({"type": "resource"}, "resource@company.com")

    def test_regular_attendee_not_room(self):
        """Regular attendees should not be detected as rooms."""
        assert not _is_room({}, "alice@company.com")
        assert not _is_room({"resource": False}, "alice@company.com")


@pytest.mark.asyncio
async def test_enrich_attendees_no_hubspot_connection():
    """When company has no HubSpot connection, return calendar data as-is."""
    supabase = MagicMock()
    supabase.table().select().eq().limit().execute().data = []

    attendees = [{"email": "alice@company.com", "name": "Alice"}]
    result = await enrich_attendees_with_hubspot(
        supabase,
        attendees,
        company_id="company123",
    )

    assert result == attendees


@pytest.mark.asyncio
async def test_enrich_attendees_no_company_id():
    """Without company_id, should return calendar data as-is."""
    supabase = MagicMock()
    attendees = [{"email": "alice@company.com", "name": "Alice"}]

    result = await enrich_attendees_with_hubspot(
        supabase,
        attendees,
        company_id=None,
    )

    assert result == attendees


@pytest.mark.asyncio
async def test_enrich_attendees_hubspot_lookup_failure_keeps_calendar_data():
    """HubSpot lookup failure should keep calendar data, not raise."""
    supabase = MagicMock()
    connection = {"access_token": "token123"}
    supabase.table().select().eq().limit().execute().data = [connection]

    # Mock HubSpotSearchService to raise exception
    mock_search_service = MagicMock()
    mock_search_service.find_contact_by_email = AsyncMock(side_effect=Exception("API error"))

    with patch("app.services.meetings.attendees.HubSpotClient"):
        with patch("app.services.meetings.attendees.HubSpotSearchService", return_value=mock_search_service):
            attendees = [{"email": "alice@company.com", "name": "Alice"}]
            result = await enrich_attendees_with_hubspot(
                supabase,
                attendees,
                company_id="company123",
            )

    # Should return original calendar data despite the error
    assert result == attendees


@pytest.mark.asyncio
async def test_enrich_attendees_with_hubspot_name():
    """HubSpot contact name should take precedence over calendar displayName."""
    supabase = MagicMock()
    connection = {"access_token": "token123"}
    supabase.table().select().eq().limit().execute().data = [connection]

    # Mock HubSpotSearchService to return a contact
    mock_contact = MagicMock()
    mock_contact.properties = {
        "firstname": "Alice",
        "lastname": "Smith",
        "email": "alice@company.com",
    }

    mock_search_service = MagicMock()
    mock_search_service.find_contact_by_email = AsyncMock(return_value=mock_contact)

    with patch("app.services.meetings.attendees.HubSpotClient"):
        with patch("app.services.meetings.attendees.HubSpotSearchService", return_value=mock_search_service):
            attendees = [{"email": "alice@company.com", "name": "Alice From Calendar"}]
            result = await enrich_attendees_with_hubspot(
                supabase,
                attendees,
                company_id="company123",
            )

    # Should use HubSpot name instead of calendar name
    assert len(result) == 1
    assert result[0]["email"] == "alice@company.com"
    assert result[0]["name"] == "Alice Smith"
