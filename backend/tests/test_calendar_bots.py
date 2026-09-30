"""Recall Calendar V2 scheduling rules: which calendar events get the Vocify bot, the
deduplication key, and schedule/unschedule against Recall's calendar-event bot endpoint."""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-recall-3232b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-recall-3232b")

import pytest

from app.config import settings
from app.integrations import recall_client as rc
from app.services.meetings import calendar_bots as cb

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
REP = "ana@acme.es"


def _google_event(**overrides):
    raw = {
        "status": "confirmed",
        "organizer": {"email": REP},
        "attendees": [
            {"email": REP, "self": True, "organizer": True, "responseStatus": "accepted"},
            {"email": "lucia@cliente.com", "responseStatus": "needsAction"},
        ],
    }
    raw.update(overrides.pop("raw", {}))
    event = {
        "id": "ev-1",
        "start_time": "2026-10-01T10:00:00Z",
        "end_time": "2026-10-01T10:30:00Z",
        "meeting_url": "https://meet.google.com/abc-defg-hij",
        "is_deleted": False,
        "bots": [],
        "raw": raw,
    }
    event.update(overrides)
    return event


def _outlook_event(**raw_overrides):
    raw = {
        "isCancelled": False,
        "organizer": {"emailAddress": {"address": REP}},
        "responseStatus": {"response": "organizer"},
        "attendees": [
            {"type": "required", "status": {"response": "none"}, "emailAddress": {"address": "jon@cliente.com"}},
        ],
    }
    raw.update(raw_overrides)
    return _google_event(raw=raw) | {"raw": raw}


def test_external_google_meeting_gets_a_bot():
    assert cb.should_join(_google_event(), calendar_email=REP, now=NOW)


def test_external_outlook_meeting_gets_a_bot():
    assert cb.should_join(_outlook_event(), calendar_email=REP, now=NOW)


def test_internal_meeting_gets_no_bot():
    event = _google_event(raw={"attendees": [{"email": REP, "self": True}, {"email": "pepe@acme.es"}]})
    assert not cb.should_join(event, calendar_email=REP, now=NOW)


def test_a_meeting_room_is_not_an_external_attendee():
    event = _google_event(
        raw={
            "attendees": [
                {"email": REP, "self": True},
                {"email": "c_1889@resource.calendar.google.com", "resource": True},
            ]
        }
    )
    assert not cb.should_join(event, calendar_email=REP, now=NOW)


@pytest.mark.parametrize(
    "event",
    [
        _google_event(meeting_url=None),
        _google_event(is_deleted=True),
        _google_event(end_time="2026-10-01T08:30:00Z"),
        _google_event(raw={"status": "cancelled"}),
        _google_event(raw={"attendees": [{"email": REP, "self": True, "responseStatus": "declined"}, {"email": "x@cliente.com"}]}),
        _outlook_event(isCancelled=True),
        _outlook_event(responseStatus={"response": "declined"}),
    ],
    ids=["no-link", "deleted", "ended", "cancelled", "declined-google", "cancelled-outlook", "declined-outlook"],
)
def test_events_that_get_no_bot(event):
    assert not cb.should_join(event, calendar_email=REP, now=NOW)


def test_without_the_reps_email_no_bot_rather_than_a_guess():
    assert not cb.should_join(_google_event(), calendar_email=None, now=NOW)


def test_deduplication_key_is_per_company_and_moves_with_the_event():
    event = _google_event()
    key = cb.deduplication_key(event, "co-1")
    assert key == "2026-10-01T10:00:00Z-https://meet.google.com/abc-defg-hij-co-1"
    assert cb.deduplication_key(event, "co-2") != key
    assert cb.deduplication_key(_google_event(start_time="2026-10-01T11:00:00Z"), "co-1") != key


class _FakeRecall:
    def __init__(self):
        self.scheduled = []
        self.unscheduled = []

    async def schedule_event_bot(self, event_id, *, deduplication_key, config):
        self.scheduled.append((event_id, deduplication_key, config))
        return {}

    async def unschedule_event_bot(self, event_id):
        self.unscheduled.append(event_id)
        return {}


def _connection(**overrides):
    row = {
        "id": "conn-1",
        "user_id": "rep-1",
        "company_id": "co-1",
        "recall_calendar_id": "cal-1",
        "email": REP,
        "status": "connected",
        "auto_join": True,
    }
    row.update(overrides)
    return row


def test_apply_event_schedules_with_calendar_metadata():
    recall = _FakeRecall()
    asyncio.run(cb.apply_event(recall, _connection(), _google_event(), NOW))
    [(event_id, key, config)] = recall.scheduled
    assert event_id == "ev-1"
    assert key.endswith("-co-1")
    assert config["metadata"] == {
        "source": "calendar",
        "environment": settings.ENVIRONMENT,
        "user_id": "rep-1",
        "company_id": "co-1",
        "calendar_event_id": "ev-1",
    }
    assert config["recording_config"]["transcript"]["provider"] == {"recallai_streaming": {}}


def test_apply_event_skips_an_event_already_scheduled_with_the_same_key():
    recall = _FakeRecall()
    event = _google_event()
    event["bots"] = [{"bot_id": "b1", "deduplication_key": cb.deduplication_key(event, "co-1")}]
    asyncio.run(cb.apply_event(recall, _connection(), event, NOW))
    assert recall.scheduled == [] and recall.unscheduled == []


def test_switch_off_unschedules_upcoming_bots():
    recall = _FakeRecall()
    event = _google_event(bots=[{"bot_id": "b1", "deduplication_key": "old"}])
    asyncio.run(cb.apply_event(recall, _connection(auto_join=False), event, NOW))
    assert recall.unscheduled == ["ev-1"] and recall.scheduled == []


def test_finished_or_deleted_events_are_left_alone():
    recall = _FakeRecall()
    bots = [{"bot_id": "b1", "deduplication_key": "old"}]
    asyncio.run(cb.apply_event(recall, _connection(auto_join=False), _google_event(bots=bots, end_time="2026-10-01T08:00:00Z"), NOW))
    asyncio.run(cb.apply_event(recall, _connection(), _google_event(bots=bots, is_deleted=True), NOW))
    assert recall.unscheduled == [] and recall.scheduled == []


def test_a_recall_error_on_one_event_does_not_raise():
    class _Failing(_FakeRecall):
        async def schedule_event_bot(self, *_a, **_k):
            raise rc.RecallClientError("Recall schedule bot error 507: no bots")

    asyncio.run(cb.apply_event(_Failing(), _connection(), _google_event(), NOW))


def test_authorize_url_and_state_round_trip():
    settings.GOOGLE_CALENDAR_CLIENT_ID = "gid"
    settings.GOOGLE_CALENDAR_CLIENT_SECRET = "gsecret"
    try:
        provider = cb.PROVIDERS["google"]
        url = cb.build_authorize_url(provider, user_id="rep-1", company_id="co-1")
        query = parse_qs(urlparse(url).query)
        assert query["client_id"] == ["gid"]
        assert query["access_type"] == ["offline"] and query["prompt"] == ["consent"]
        assert "calendar.events.readonly" in query["scope"][0]
        assert query["redirect_uri"] == [f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}/api/v1/calendar/google/callback"]
        assert cb.decode_state(query["state"][0], provider) == ("rep-1", "co-1")
        with pytest.raises(cb.CalendarOAuthError):
            cb.decode_state(query["state"][0], cb.PROVIDERS["microsoft"])
        with pytest.raises(cb.CalendarOAuthError):
            cb.decode_state("not-a-jwt", provider)
    finally:
        settings.GOOGLE_CALENDAR_CLIENT_ID = None
        settings.GOOGLE_CALENDAR_CLIENT_SECRET = None


def test_available_providers_need_recall_and_the_oauth_app():
    settings.RECALL_API_KEY = None
    settings.MICROSOFT_CALENDAR_CLIENT_ID = "mid"
    settings.MICROSOFT_CALENDAR_CLIENT_SECRET = "msecret"
    try:
        assert cb.available_providers() == []
        settings.RECALL_API_KEY = "key-1"
        assert cb.available_providers() == ["microsoft"]
    finally:
        settings.RECALL_API_KEY = None
        settings.MICROSOFT_CALENDAR_CLIENT_ID = None
        settings.MICROSOFT_CALENDAR_CLIENT_SECRET = None


def test_rep_email_decides_the_speaker_before_the_name():
    segments = [
        {"participant": {"name": "Ana", "email": REP}, "words": [{"text": "Hola"}]},
        {"participant": {"name": "Ana", "email": "ana@cliente.com"}, "words": [{"text": "Buenas"}]},
        {"participant": {"name": "Ana Ruiz", "email": None}, "words": [{"text": "¿Precio?"}]},
    ]
    _, turns = rc.turns_from_recall_transcript(segments, rep_name="Ana Ruiz", rep_email=REP.upper())
    assert [t["speaker_role"] for t in turns] == ["rep", "prospect", "rep"]
