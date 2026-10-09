"""The rep's upcoming meetings, kept from the Recall calendar sync: who each meeting is with,
matched to HubSpot contacts by email. Feeds the island ("Call with Marta in 1 min" with her
brief) and links a desktop recording to the meeting it belongs to, so the memo knows the
attendees and the contact even when no HubSpot tab was open.

Rows are written on every calendar sync (`calendar_bots.sync_calendar`); the bot rules there
are unchanged. Stored from 1 day back; older rows are dropped on each full sync."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from supabase import Client

from app.services.meetings.calendar_bots import _cancelled, _declined_by_rep, _domain, _is_room, _parse_time

logger = logging.getLogger(__name__)

TABLE = "calendar_events"
CONNECTIONS = "calendar_connections"
KEEP_PAST = timedelta(days=1)
# A sync older than this is refreshed when the island asks (Recall's webhook may be late or off).
STALE_AFTER = timedelta(minutes=5)
# A recording belongs to a meeting that started up to this long before or after it
# (Granola links a call starting within 15 minutes of a scheduled meeting).
LINK_WINDOW = timedelta(minutes=15)
# A full sync also lists meetings that began this long ago, so one still running is known.
LOOK_BACK = timedelta(hours=2)
# HubSpot lookups per sync; the rest are matched on the next sync.
MAX_LOOKUPS = 25

PLATFORM_HOSTS = {
    "zoom": ("zoom.us", "zoom.com"),
    "meet": ("meet.google.com",),
    "teams": ("teams.microsoft.com", "teams.live.com"),
}


def _email(attendee: dict[str, Any]) -> str:
    return str(attendee.get("email") or (attendee.get("emailAddress") or {}).get("address") or "").strip().lower()


def _display_name(attendee: dict[str, Any]) -> Optional[str]:
    name = attendee.get("displayName") or (attendee.get("emailAddress") or {}).get("name")
    name = str(name or "").strip()
    return name or None


def platform_of(url: Optional[str]) -> Optional[str]:
    host = (url or "").lower()
    for platform, hosts in PLATFORM_HOSTS.items():
        if any(h in host for h in hosts):
            return platform
    return None


def attendees_of(raw: dict[str, Any], rep_email: Optional[str]) -> list[dict[str, Any]]:
    """Everyone on the invite but the rep and rooms (Google or Graph `raw`), organizer included.
    `external` = another email domain than the rep's calendar."""
    rep = (rep_email or "").strip().lower()
    own_domain = _domain(rep)
    people: list[dict[str, Any]] = []
    seen: set[str] = set()
    organizer = raw.get("organizer") or {}
    for attendee in [*(raw.get("attendees") or []), organizer]:
        email = _email(attendee)
        if not email or email in seen or _is_room(attendee, email):
            continue
        seen.add(email)
        if email == rep or attendee.get("self"):
            continue
        people.append({
            "email": email,
            "name": _display_name(attendee),
            "external": bool(own_domain) and _domain(email) != own_domain,
        })
    return people


def event_row(event: dict[str, Any], connection: dict[str, Any]) -> Optional[dict[str, Any]]:
    """A Recall calendar event as stored; None without an ID or a start."""
    start = _parse_time(event.get("start_time"))
    if not event.get("id") or not start:
        return None
    raw = event.get("raw") or {}
    end = _parse_time(event.get("end_time"))
    title = str(raw.get("summary") or raw.get("subject") or "").strip() or None
    return {
        "recall_event_id": str(event["id"]),
        "user_id": connection["user_id"],
        "company_id": connection["company_id"],
        "start_time": start.isoformat(),
        "end_time": end.isoformat() if end else None,
        "title": title,
        "meeting_url": event.get("meeting_url") or None,
        "attendees": attendees_of(raw, connection.get("email")),
        "is_deleted": bool(event.get("is_deleted")) or _cancelled(raw) or _declined_by_rep(raw),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _known_matches(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Email -> what HubSpot said last time (a contact, or `matched` with none)."""
    known: dict[str, dict[str, Any]] = {}
    for row in rows:
        for person in row.get("attendees") or []:
            if person.get("matched") and person.get("email"):
                known[person["email"]] = person
    return known


async def _hubspot_search(supabase: Client, company_id: str):
    """The company's HubSpot search, with a fresh token; None without HubSpot."""
    from app.services.crm_providers.resolve import resolve_sync_connection_for_company
    from app.services.hubspot.client import HubSpotClient
    from app.services.hubspot.search import HubSpotSearchService
    from app.services.hubspot.token_refresh import ensure_hubspot_connection_tokens_fresh

    connection = resolve_sync_connection_for_company(supabase, company_id)
    if not connection or (connection.get("provider") or "").lower() != "hubspot":
        return None
    connection = await ensure_hubspot_connection_tokens_fresh(supabase, connection)
    token = (connection.get("access_token") or "").strip()
    return HubSpotSearchService(HubSpotClient(token)) if token else None


async def match_contacts(rows: list[dict[str, Any]], known: dict[str, dict[str, Any]], search) -> None:
    """Puts the HubSpot contact on each external attendee, reusing earlier answers; at most
    MAX_LOOKUPS new lookups. A failed lookup is left unmatched and retried on a later sync."""
    lookups = 0
    for row in rows:
        for person in row["attendees"]:
            if not person.get("external"):
                continue
            previous = known.get(person["email"])
            if previous:
                person.update(matched=True, hubspot_contact_id=previous.get("hubspot_contact_id"))
                if previous.get("hubspot_name"):
                    person["hubspot_name"] = previous["hubspot_name"]
                continue
            if search is None or lookups >= MAX_LOOKUPS:
                continue
            lookups += 1
            try:
                contact = await search.find_contact_by_email(person["email"])
            except Exception as exc:
                logger.debug("HubSpot lookup failed for a calendar attendee: %s", exc)
                continue
            props = (getattr(contact, "properties", None) or {}) if contact else {}
            name = f"{(props.get('firstname') or '').strip()} {(props.get('lastname') or '').strip()}".strip()
            person.update(matched=True, hubspot_contact_id=str(contact.id) if contact else None)
            if name:
                person["hubspot_name"] = name
            known[person["email"]] = person


def _team_names(supabase: Client, company_id: str) -> dict[str, str]:
    """Teammates' emails -> their names in Vocify, so a colleague on the invite reads "Toni García",
    not an address (calendars often give no display name). Empty when it can't be read."""
    from app.services.company import CompanyService

    try:
        members = CompanyService(supabase).list_members(company_id)
    except Exception:
        logger.warning("Teammates' names unavailable for calendar attendees", exc_info=True)
        return {}
    return {
        str(m["email"]).strip().lower(): str(m["full_name"]).strip()
        for m in members
        if m.get("email") and (m.get("full_name") or "").strip()
    }


def name_teammates(rows: list[dict[str, Any]], names: dict[str, str]) -> None:
    """Colleagues without a name on the invite get their Vocify name."""
    for row in rows:
        for person in row["attendees"]:
            if not person.get("external") and not person.get("name") and person["email"] in names:
                person["name"] = names[person["email"]]


async def store_events(
    supabase: Client, connection: dict[str, Any], events: list[dict[str, Any]], *, full: bool
) -> None:
    """Saves the synced events with their HubSpot contacts. `full` (every upcoming event was
    listed) also drops rows older than a day and marks the sync time. Never raises."""
    try:
        rows = [row for row in (event_row(e, connection) for e in events) if row]
        existing = (
            supabase.table(TABLE).select("recall_event_id,attendees").eq("user_id", connection["user_id"]).execute().data
            or []
        )
        known = _known_matches(existing)
        needs_lookup = any(
            p.get("external") and p["email"] not in known for row in rows for p in row["attendees"]
        )
        search = None
        if needs_lookup:
            try:
                search = await _hubspot_search(supabase, connection["company_id"])
            except Exception:
                # HubSpot unreachable or its login expired: the meetings are kept, matched on a later sync.
                logger.warning("HubSpot search unavailable for calendar attendees", exc_info=True)
        await match_contacts(rows, known, search)
        if any(not p.get("external") and not p.get("name") for row in rows for p in row["attendees"]):
            name_teammates(rows, _team_names(supabase, connection["company_id"]))
        if rows:
            supabase.table(TABLE).upsert(rows, on_conflict="recall_event_id").execute()
        if full:
            cutoff = (datetime.now(timezone.utc) - KEEP_PAST).isoformat()
            supabase.table(TABLE).delete().eq("user_id", connection["user_id"]).lt("start_time", cutoff).execute()
            supabase.table(CONNECTIONS).update(
                {"events_synced_at": datetime.now(timezone.utc).isoformat()}
            ).eq("id", connection["id"]).execute()
    except Exception:
        logger.exception("Storing calendar events failed for %s", connection.get("user_id"))


def is_stale(connection: dict[str, Any], now: datetime) -> bool:
    synced = _parse_time(connection.get("events_synced_at"))
    return synced is None or now - synced > STALE_AFTER


def external_people(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for p in row.get("attendees") or [] if p.get("external")]


def people_outside_first(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Everyone on the invite but the rep: people from outside first (the ones a brief is about)."""
    people = row.get("attendees") or []
    return [p for p in people if p.get("external")] + [p for p in people if not p.get("external")]


def person_name(person: dict[str, Any]) -> Optional[str]:
    return person.get("hubspot_name") or person.get("name")


def upcoming(rows: list[dict[str, Any]], now: datetime, horizon: timedelta) -> list[dict[str, Any]]:
    """Meetings worth a heads-up: not cancelled, a call link, someone besides the rep (inside or
    outside the company: an internal meeting is typed "internal" on its memo), and not over yet,
    starting before `now + horizon`; soonest first."""
    picked = []
    for row in rows:
        start, end = _parse_time(row.get("start_time")), _parse_time(row.get("end_time"))
        if row.get("is_deleted") or not row.get("meeting_url") or not row.get("attendees") or not start:
            continue
        if (end or start) <= now or start > now + horizon:
            continue
        picked.append(row)
    return sorted(picked, key=lambda r: r["start_time"])


def for_recording(
    rows: list[dict[str, Any]], started_at: datetime, call_source: Optional[str]
) -> Optional[dict[str, Any]]:
    """The meeting a recording that began at `started_at` belongs to: one starting within
    LINK_WINDOW of it, or already running. Several: the one on the same platform as the call
    app, then the closest start."""
    source = (call_source or "").lower()
    wanted = next((p for p in PLATFORM_HOSTS if p in source), None)
    candidates = []
    for row in rows:
        start, end = _parse_time(row.get("start_time")), _parse_time(row.get("end_time"))
        if row.get("is_deleted") or not start:
            continue
        near = abs(start - started_at) <= LINK_WINDOW
        running = start <= started_at and end is not None and started_at < end
        if near or running:
            candidates.append(row)
    if not candidates:
        return None

    def rank(row: dict[str, Any]) -> tuple[int, float]:
        same_app = wanted is not None and platform_of(row.get("meeting_url")) == wanted
        return (0 if same_app else 1, abs((_parse_time(row["start_time"]) - started_at).total_seconds()))

    return min(candidates, key=rank)


def memo_attendees(row: dict[str, Any], speaker_names: list[str]) -> list[dict[str, Any]]:
    """The memo's attendees: the invite (HubSpot names first), then anyone the call app showed
    speaking who isn't on it."""
    people = [
        {"name": person_name(p), "email": p["email"], **({"hubspot_contact_id": p["hubspot_contact_id"]} if p.get("hubspot_contact_id") else {})}
        for p in row.get("attendees") or []
    ]
    names = {(p["name"] or "").casefold() for p in people}
    people += [{"name": n, "email": None} for n in speaker_names if n.casefold() not in names]
    return people


def single_contact(row: dict[str, Any]) -> Optional[str]:
    """The HubSpot contact the meeting is with, only when exactly one outside attendee matched
    (with several, the rep picks in the review rather than Vocify guessing)."""
    ids = {p["hubspot_contact_id"] for p in external_people(row) if p.get("hubspot_contact_id")}
    return ids.pop() if len(ids) == 1 else None


def rows_for_user(supabase: Client, user_id: str, since: datetime, until: datetime) -> list[dict[str, Any]]:
    return (
        supabase.table(TABLE).select("*").eq("user_id", user_id)
        .gte("start_time", since.isoformat()).lte("start_time", until.isoformat())
        .order("start_time").execute().data
        or []
    )
