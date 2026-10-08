"""Meeting context from the rep's calendar: events stored with their outside attendees matched
to HubSpot contacts, the heads-up list, and which meeting a desktop recording belongs to."""

import asyncio
import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-recall-3232b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-recall-3232b")

from app.services.meetings import calendar_events as ce

NOW = datetime(2026, 10, 8, 9, 0, tzinfo=timezone.utc)
REP = "ana@acme.es"
CONNECTION = {"id": "conn-1", "user_id": "rep-1", "company_id": "co-1", "email": REP}


def _event(**overrides):
    raw = {
        "summary": "Demo Vocify",
        "status": "confirmed",
        "organizer": {"email": REP},
        "attendees": [
            {"email": REP, "self": True, "responseStatus": "accepted"},
            {"email": "marta@cliente.com", "displayName": "Marta G."},
            {"email": "pepe@acme.es", "displayName": "Pepe"},
            {"email": "c_1@resource.calendar.google.com", "resource": True},
        ],
    }
    raw.update(overrides.pop("raw", {}))
    event = {
        "id": "ev-1",
        "start_time": "2026-10-08T09:30:00Z",
        "end_time": "2026-10-08T10:00:00Z",
        "meeting_url": "https://meet.google.com/abc-defg-hij",
        "is_deleted": False,
        "raw": raw,
    }
    event.update(overrides)
    return event


def test_event_row_keeps_people_but_not_the_rep_or_rooms():
    row = ce.event_row(_event(), CONNECTION)
    assert row["title"] == "Demo Vocify"
    assert row["is_deleted"] is False
    assert row["attendees"] == [
        {"email": "marta@cliente.com", "name": "Marta G.", "external": True},
        {"email": "pepe@acme.es", "name": "Pepe", "external": False},
    ]


def test_outlook_event_row():
    raw = {
        "subject": "Kickoff",
        "organizer": {"emailAddress": {"address": "jon@cliente.com", "name": "Jon"}},
        "attendees": [{"type": "required", "emailAddress": {"address": REP}}],
        "responseStatus": {"response": "accepted"},
    }
    row = ce.event_row(_event(raw=raw) | {"raw": raw}, CONNECTION)
    assert row["title"] == "Kickoff"
    assert row["attendees"] == [{"email": "jon@cliente.com", "name": "Jon", "external": True}]


def test_declined_or_cancelled_is_deleted():
    declined = _event(raw={"attendees": [{"email": REP, "self": True, "responseStatus": "declined"}]})
    assert ce.event_row(declined, CONNECTION)["is_deleted"] is True
    assert ce.event_row(_event(raw={"status": "cancelled"}), CONNECTION)["is_deleted"] is True


class _Contact:
    def __init__(self, cid, first, last):
        self.id = cid
        self.properties = {"firstname": first, "lastname": last}


class _Search:
    def __init__(self, contacts):
        self.contacts = contacts
        self.asked = []

    async def find_contact_by_email(self, email):
        self.asked.append(email)
        if email == "boom@cliente.com":
            raise RuntimeError("HubSpot down")
        return self.contacts.get(email)


def test_match_contacts_looks_up_outside_people_once():
    rows = [ce.event_row(_event(), CONNECTION)]
    search = _Search({"marta@cliente.com": _Contact("901", "Marta", "García")})
    asyncio.run(ce.match_contacts(rows, {}, search))
    marta, pepe = rows[0]["attendees"]
    assert marta["hubspot_contact_id"] == "901" and marta["hubspot_name"] == "Marta García" and marta["matched"]
    assert "matched" not in pepe
    assert search.asked == ["marta@cliente.com"]

    again = [ce.event_row(_event(id="ev-2"), CONNECTION)]
    search2 = _Search({})
    asyncio.run(ce.match_contacts(again, ce._known_matches(rows), search2))
    assert search2.asked == []
    assert again[0]["attendees"][0]["hubspot_contact_id"] == "901"


def test_no_hubspot_contact_is_remembered_and_a_failure_is_retried():
    rows = [ce.event_row(_event(raw={"attendees": [
        {"email": "nadie@cliente.com"}, {"email": "boom@cliente.com"},
    ]}), CONNECTION)]
    asyncio.run(ce.match_contacts(rows, {}, _Search({})))
    nadie, boom = rows[0]["attendees"]
    assert nadie["matched"] and nadie["hubspot_contact_id"] is None
    assert "matched" not in boom


def _stored(**overrides):
    row = ce.event_row(_event(), CONNECTION)
    row["attendees"][0].update(matched=True, hubspot_contact_id="901", hubspot_name="Marta García")
    row.update(overrides)
    return row


def test_upcoming_meetings_with_someone_and_a_link_not_over():
    soon = _stored()
    internal = _stored(recall_event_id="ev-int", start_time="2026-10-08T09:45:00+00:00", attendees=[{"email": "pepe@acme.es", "external": False}])
    alone = _stored(recall_event_id="ev-alone", attendees=[])
    no_link = _stored(recall_event_id="ev-nolink", meeting_url=None)
    over = _stored(recall_event_id="ev-over", start_time="2026-10-08T07:00:00+00:00", end_time="2026-10-08T08:00:00+00:00")
    cancelled = _stored(recall_event_id="ev-x", is_deleted=True)
    far = _stored(recall_event_id="ev-far", start_time="2026-10-09T09:00:00+00:00", end_time="2026-10-09T10:00:00+00:00")
    rows = [far, cancelled, over, no_link, internal, alone, soon]
    # An internal meeting gets its heads-up too (its memo is typed "internal"); a meeting with nobody else doesn't.
    assert [r["recall_event_id"] for r in ce.upcoming(rows, NOW, timedelta(hours=12))] == ["ev-1", "ev-int"]
    assert [p["email"] for p in ce.people_outside_first(soon)] == ["marta@cliente.com", "pepe@acme.es"]


def test_recording_links_to_the_meeting_it_belongs_to():
    meet = _stored()
    zoom = _stored(recall_event_id="ev-zoom", meeting_url="https://acme.zoom.us/j/1")
    started = NOW + timedelta(minutes=29)
    assert ce.for_recording([meet, zoom], started, "Zoom")["recall_event_id"] == "ev-zoom"
    assert ce.for_recording([meet, zoom], started, "Google Meet")["recall_event_id"] == "ev-1"
    # Joined 20 minutes late: the meeting is still running.
    assert ce.for_recording([meet], NOW + timedelta(minutes=50), None)["recall_event_id"] == "ev-1"
    # An hour after it ended: no meeting.
    assert ce.for_recording([meet], NOW + timedelta(hours=2), None) is None
    assert ce.for_recording([_stored(is_deleted=True)], started, None) is None


def test_memo_attendees_and_the_single_contact():
    meeting = _stored()
    people = ce.memo_attendees(meeting, ["Marta García", "Luis"])
    assert people == [
        {"name": "Marta García", "email": "marta@cliente.com", "hubspot_contact_id": "901"},
        {"name": "Pepe", "email": "pepe@acme.es"},
        {"name": "Luis", "email": None},
    ]
    assert ce.single_contact(meeting) == "901"
    two = _stored()
    two["attendees"].append({"email": "jon@cliente.com", "external": True, "matched": True, "hubspot_contact_id": "902"})
    assert ce.single_contact(two) is None


def test_stale_after_five_minutes():
    assert ce.is_stale({}, NOW)
    assert not ce.is_stale({"events_synced_at": (NOW - timedelta(minutes=4)).isoformat()}, NOW)
    assert ce.is_stale({"events_synced_at": (NOW - timedelta(minutes=6)).isoformat()}, NOW)


def test_platform_of():
    assert ce.platform_of("https://acme.zoom.us/j/1") == "zoom"
    assert ce.platform_of("https://meet.google.com/abc-defg-hij") == "meet"
    assert ce.platform_of("https://teams.microsoft.com/l/meetup-join/x") == "teams"
    assert ce.platform_of("https://whereby.com/x") is None


# --- storing, the endpoint and the memo link, against an in-memory Supabase ---------------


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self.rows = db.tables.setdefault(table, [])
        self.filters = []
        self.mode, self.payload = "select", None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self.filters.append(lambda r: r.get(column) == value)
        return self

    def lt(self, column, value):
        self.filters.append(lambda r: str(r.get(column)) < value)
        return self

    def gte(self, column, value):
        self.filters.append(lambda r: str(r.get(column)) >= value)
        return self

    def lte(self, column, value):
        self.filters.append(lambda r: str(r.get(column)) <= value)
        return self

    def order(self, column):
        self.order_by = column
        return self

    def limit(self, _n):
        return self

    def upsert(self, payload, on_conflict):
        self.mode, self.payload, self.conflict = "upsert", payload, on_conflict
        return self

    def update(self, payload):
        self.mode, self.payload = "update", payload
        return self

    def delete(self):
        self.mode = "delete"
        return self

    def execute(self):
        match = lambda r: all(f(r) for f in self.filters)  # noqa: E731
        if self.mode == "upsert":
            for item in self.payload if isinstance(self.payload, list) else [self.payload]:
                existing = next((r for r in self.rows if r.get(self.conflict) == item.get(self.conflict)), None)
                if existing:
                    existing.update(item)
                else:
                    self.rows.append(dict(item))
            return _Result([])
        if self.mode == "update":
            for row in self.rows:
                if match(row):
                    row.update(self.payload)
            return _Result([])
        if self.mode == "delete":
            self.rows[:] = [r for r in self.rows if not match(r)]
            return _Result([])
        found = [dict(r) for r in self.rows if match(r)]
        return _Result(sorted(found, key=lambda r: str(r.get(getattr(self, "order_by", "id"), ""))))


class _Db:
    def __init__(self, **tables):
        self.tables = {k: list(v) for k, v in tables.items()}

    def table(self, name):
        return _Query(self, name)


def test_store_events_saves_matches_prunes_and_marks_the_sync(monkeypatch):
    old = _stored(recall_event_id="ev-old", start_time="2020-01-01T09:00:00+00:00")
    db = _Db(calendar_events=[old], calendar_connections=[dict(CONNECTION)])
    search = _Search({"marta@cliente.com": _Contact("901", "Marta", "García")})

    async def fake_search(_supabase, _company):
        return search

    monkeypatch.setattr(ce, "_hubspot_search", fake_search)
    asyncio.run(ce.store_events(db, CONNECTION, [_event(), {"id": None}], full=True))
    rows = db.tables["calendar_events"]
    assert [r["recall_event_id"] for r in rows] == ["ev-1"]
    assert rows[0]["attendees"][0]["hubspot_contact_id"] == "901"
    assert db.tables["calendar_connections"][0]["events_synced_at"]
    # Already matched: a later sync of the same people asks HubSpot nothing.
    search.asked.clear()
    asyncio.run(ce.store_events(db, CONNECTION, [_event()], full=False))
    assert search.asked == []


def test_colleagues_get_their_vocify_name():
    rows = [ce.event_row(_event(raw={"attendees": [
        {"email": "toni@acme.es"}, {"email": "pepe@acme.es", "displayName": "Pepe"}, {"email": "jon@cliente.com"},
    ]}), CONNECTION)]
    ce.name_teammates(rows, {"toni@acme.es": "Toni García", "pepe@acme.es": "José Pérez", "jon@cliente.com": "No"})
    assert [p.get("name") for p in rows[0]["attendees"]] == ["Toni García", "Pepe", None]


def test_without_hubspot_the_meetings_are_still_kept(monkeypatch):
    async def broken(_supabase, _company):
        raise ValueError("HubSpot authorization expired")

    monkeypatch.setattr(ce, "_hubspot_search", broken)
    db = _Db()
    asyncio.run(ce.store_events(db, CONNECTION, [_event()], full=True))
    rows = db.tables["calendar_events"]
    assert [r["recall_event_id"] for r in rows] == ["ev-1"]
    assert "matched" not in rows[0]["attendees"][0]


def test_memo_is_linked_to_its_meeting():
    from app.api.memos import _link_calendar_meeting

    db = _Db(calendar_events=[_stored(user_id="rep-1")])
    payload = {"attendees": [{"name": "Marta García", "email": None}]}
    _link_calendar_meeting(db, "rep-1", payload, NOW + timedelta(minutes=31), "Google Meet", ["Marta García"])
    assert payload["hubspot_contact_id"] == "901"
    assert payload["attendees"][0] == {"name": "Marta García", "email": "marta@cliente.com", "hubspot_contact_id": "901"}
    assert payload["pipeline_meta"]["calendar_event"] == {"id": "ev-1", "title": "Demo Vocify"}


def test_the_contact_on_screen_wins_and_no_meeting_changes_nothing():
    from app.api.memos import _link_calendar_meeting

    db = _Db(calendar_events=[_stored(user_id="rep-1")])
    payload = {"hubspot_contact_id": "555"}
    _link_calendar_meeting(db, "rep-1", payload, NOW + timedelta(minutes=31), "Google Meet", [])
    assert payload["hubspot_contact_id"] == "555"
    untouched = {"attendees": []}
    _link_calendar_meeting(db, "rep-1", untouched, NOW + timedelta(days=3), "Zoom", [])
    assert untouched == {"attendees": []}


def test_upcoming_endpoint(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import calendar as api
    from app.deps import get_membership, get_supabase
    from app.services.company import Membership

    start = datetime.now(timezone.utc) + timedelta(minutes=30)
    row = _stored(
        user_id="rep-1",
        start_time=start.isoformat(),
        end_time=(start + timedelta(minutes=30)).isoformat(),
    )
    fresh = {**CONNECTION, "status": "connected", "events_synced_at": datetime.now(timezone.utc).isoformat()}
    db = _Db(calendar_events=[row], calendar_connections=[fresh])
    monkeypatch.setattr(api, "is_enabled", lambda *_a: True)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_supabase] = lambda: db
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m-1", company_id="co-1", user_id="rep-1", role="member", status="active"
    )
    body = TestClient(app).get("/api/v1/calendar/upcoming").json()
    assert body == [{
        "id": "ev-1",
        "title": "Demo Vocify",
        "start_time": row["start_time"],
        "end_time": row["end_time"],
        "meeting_url": "https://meet.google.com/abc-defg-hij",
        "platform": "meet",
        "people": [
            {"name": "Marta García", "email": "marta@cliente.com", "external": True, "hubspot_contact_id": "901"},
            {"name": "Pepe", "email": "pepe@acme.es", "external": False, "hubspot_contact_id": None},
        ],
    }]

    db.tables["calendar_connections"] = []
    assert TestClient(app).get("/api/v1/calendar/upcoming").json() == []
