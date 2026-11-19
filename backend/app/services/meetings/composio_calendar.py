"""Google Calendar through Composio: the rep signs in on Composio's Google app (verified by
Google, so no "unverified app" screen and no user cap), and Vocify reads the primary calendar
through Composio's proxy. Recall's calendar sync needs our own OAuth client, so here Vocify
schedules the Recall bots itself: one bot per meeting, created with `join_at`.

Same rules as Calendar V2 (`calendar_bots.should_join`, one bot per company per meeting via
`deduplication_key`, events stored in `calendar_events`). Google sends no webhooks here: the
meetings are synced when the rep connects, flips the switch, when the island asks for them
(5 minutes stale), and every 5 minutes for every connected rep (`sync_all`).

The `calendar_connections` row needs a `recall_calendar_id`: a Composio connection gets a
fixed UUID made from the user ID (`marker_id`), which is how it is told apart. The Composio
account is found by Vocify user ID. A scheduled bot carries its event (`calendar_event_id`)
and key (`calendar_key`) in its Recall metadata, so Recall itself says which bots exist.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from supabase import Client

from app.config import settings
from app.integrations.composio_client import ComposioClient, ComposioError
from app.integrations.recall_client import RecallClient, RecallClientError, is_allowed_meeting_url
from app.services.meetings import calendar_events
from app.services.meetings.calendar_bots import (
    TABLE,
    CalendarOAuthError,
    _parse_time,
    deduplication_key,
    should_join,
)

logger = logging.getLogger(__name__)

PLATFORM = "google_calendar"
EVENT_PREFIX = "gcal:"
# Recall Calendar V2 syncs 28 days ahead; same here.
LOOK_AHEAD = timedelta(days=28)
GOOGLE_API = "https://www.googleapis.com/calendar/v3"
_MARKER_NAMESPACE = uuid.UUID("0b8f6a52-3d4e-4c0e-9a51-7a8f2f1c6d10")
_URL = re.compile(r"https://[^\s<>\"')]+")


def configured() -> bool:
    return bool(settings.COMPOSIO_API_KEY and settings.COMPOSIO_GOOGLE_CALENDAR_AUTH_CONFIG_ID)


def marker_id(user_id: str) -> str:
    return str(uuid.uuid5(_MARKER_NAMESPACE, str(user_id)))


def is_composio(connection: dict[str, Any]) -> bool:
    return str(connection.get("recall_calendar_id")) == marker_id(connection["user_id"])


def callback_url(state: str) -> str:
    return f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}/api/v1/calendar/google/callback?state={state}"


async def build_authorize_url(state: str, user_id: str) -> str:
    try:
        link = await ComposioClient().create_link(
            auth_config_id=settings.COMPOSIO_GOOGLE_CALENDAR_AUTH_CONFIG_ID or "",
            user_id=user_id,
            callback_url=callback_url(state),
        )
    except ComposioError as exc:
        logger.warning("Composio link failed for %s: %s", user_id, exc)
        raise
    return str(link["redirect_url"])


async def _account_id(client: ComposioClient, user_id: str) -> Optional[str]:
    accounts = await client.active_accounts(
        auth_config_id=settings.COMPOSIO_GOOGLE_CALENDAR_AUTH_CONFIG_ID or "", user_id=user_id
    )
    return str(accounts[0]["id"]) if accounts else None


# --- Google events as Recall Calendar V2 events -------------------------------------


def _event_time(value: Optional[dict[str, Any]]) -> Optional[str]:
    value = value or {}
    if value.get("dateTime"):
        return str(value["dateTime"])
    if value.get("date"):
        return f"{value['date']}T00:00:00+00:00"
    return None


def meeting_url(event: dict[str, Any]) -> Optional[str]:
    """Meet link, else the conference's video entry, else a Zoom/Meet/Teams link in the
    location or description."""
    if event.get("hangoutLink"):
        return str(event["hangoutLink"])
    for entry in (event.get("conferenceData") or {}).get("entryPoints") or []:
        if entry.get("entryPointType") == "video" and is_allowed_meeting_url(str(entry.get("uri") or "")):
            return str(entry["uri"])
    for text in (event.get("location"), event.get("description")):
        for url in _URL.findall(str(text or "")):
            if is_allowed_meeting_url(url):
                return url
    return None


def to_event(google_event: dict[str, Any], user_id: str) -> Optional[dict[str, Any]]:
    """A Google event in the shape `calendar_bots` and `calendar_events` read (Recall's)."""
    if not google_event.get("id"):
        return None
    return {
        "id": f"{EVENT_PREFIX}{user_id}:{google_event['id']}",
        "start_time": _event_time(google_event.get("start")),
        "end_time": _event_time(google_event.get("end")),
        "meeting_url": meeting_url(google_event),
        "is_deleted": google_event.get("status") == "cancelled",
        "raw": google_event,
    }


async def list_events(client: ComposioClient, account_id: str, user_id: str, since: datetime, until: datetime) -> list[dict[str, Any]]:
    params = {
        "timeMin": since.isoformat(),
        "timeMax": until.isoformat(),
        "singleEvents": "true",
        "showDeleted": "true",
        "maxResults": "250",
    }
    events: list[dict[str, Any]] = []
    while True:
        data = await client.proxy_get(account_id, f"{GOOGLE_API}/calendars/primary/events", params)
        events.extend(e for e in (to_event(item, user_id) for item in data.get("items") or []) if e)
        token = data.get("nextPageToken")
        if not token:
            return events
        params = {**params, "pageToken": str(token)}


# --- connect / sync / disconnect -----------------------------------------------------


async def connect(
    supabase: Client, recall: RecallClient, *, user_id: str, company_id: str, account_id: Optional[str]
) -> dict[str, Any]:
    """After Composio sends the rep back: the account must be this rep's and active. Replaces
    the rep's previous calendar (a Recall one, or older Composio accounts)."""
    composio = ComposioClient()
    try:
        accounts = await composio.active_accounts(
            auth_config_id=settings.COMPOSIO_GOOGLE_CALENDAR_AUTH_CONFIG_ID or "", user_id=user_id
        )
        if not accounts or (account_id and account_id not in {str(a["id"]) for a in accounts}):
            raise CalendarOAuthError("not_connected")
        current = account_id or str(accounts[0]["id"])
        primary = await composio.proxy_get(current, f"{GOOGLE_API}/calendars/primary", {})
    except ComposioError as exc:
        logger.warning("Composio connect failed for %s: %s", user_id, exc)
        raise CalendarOAuthError("composio_failed") from exc

    from app.services.meetings.calendar_bots import connection_for_user

    previous = connection_for_user(supabase, user_id)
    row = {
        "user_id": user_id,
        "company_id": company_id,
        "platform": PLATFORM,
        "recall_calendar_id": marker_id(user_id),
        "email": str(primary.get("id") or "").strip().lower() or None,
        "status": "connected",
        "auto_join": previous["auto_join"] if previous else False,
        "events_synced_at": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    saved = supabase.table(TABLE).upsert(row, on_conflict="user_id").execute().data or [row]

    if previous and not is_composio(previous):
        try:
            await recall.delete_calendar(str(previous["recall_calendar_id"]))
        except RecallClientError:
            logger.warning("Recall delete of replaced calendar %s failed", previous["recall_calendar_id"], exc_info=True)
    for account in accounts:
        if str(account["id"]) != current:
            try:
                await composio.delete_account(str(account["id"]))
            except ComposioError:
                logger.warning("Composio delete of replaced account failed for %s", user_id, exc_info=True)
    return saved[0]


def _meta(bot: dict[str, Any]) -> dict[str, Any]:
    return bot.get("metadata") or {}


def _not_started(event: dict[str, Any], now: datetime) -> bool:
    start = _parse_time(event.get("start_time"))
    return start is not None and start > now


async def _company_bots(recall: RecallClient, company_id: str, now: datetime) -> list[dict[str, Any]]:
    bots = await recall.list_bots({
        "metadata__company_id": company_id,
        "metadata__source": "calendar",
        "join_at_after": (now - calendar_events.LOOK_BACK).isoformat(),
    })
    return [b for b in bots if str(_meta(b).get("calendar_event_id") or "").startswith(EVENT_PREFIX)]


async def apply_bots(recall: RecallClient, connection: dict[str, Any], events: list[dict[str, Any]], now: datetime) -> None:
    """Schedules a bot for each meeting that should get one and has none in the company yet;
    removes this rep's bots from meetings that no longer should (or moved) before they start."""
    from app.services.meetings.calendar_bots import calendar_bot_config

    company_id, user_id = str(connection["company_id"]), str(connection["user_id"])
    bots = await _company_bots(recall, company_id, now)
    for event in events:
        wanted = (
            bool(connection.get("auto_join"))
            and connection.get("status") != "disconnected"
            and should_join(event, calendar_email=connection.get("email"), now=now)
        )
        key = deduplication_key(event, company_id)
        mine = [b for b in bots if _meta(b).get("calendar_event_id") == event["id"] and _meta(b).get("user_id") == user_id]
        covered = any(_meta(b).get("calendar_key") == key for b in bots)
        try:
            if wanted and not covered:
                for bot in mine:  # the meeting moved: its old bot goes
                    await recall.delete_bot(str(bot["id"]))
                config = calendar_bot_config(connection, event)
                start = _parse_time(event.get("start_time"))
                created = await recall.create_bot(
                    str(event["meeting_url"]),
                    metadata={**config["metadata"], "calendar_key": key},
                    join_at=start.isoformat() if start and start > now else None,
                )
                bots.append({**created, "metadata": {**config["metadata"], "calendar_key": key}})
            elif not wanted and _not_started(event, now):
                for bot in mine:
                    await recall.delete_bot(str(bot["id"]))
        except RecallClientError as exc:
            # One meeting failing must not stop the rest; the next sync retries it.
            logger.warning("Calendar bot update failed for event %s: %s", event.get("id"), exc)


async def sync(supabase: Client, recall: RecallClient, connection: dict[str, Any]) -> None:
    """Every meeting from a while back to 28 days ahead: stored, then bots applied. A rep
    whose Composio account is gone (revoked access) is marked disconnected."""
    user_id = str(connection["user_id"])
    composio = ComposioClient()
    account_id = await _account_id(composio, user_id)
    if not account_id:
        if connection.get("status") != "disconnected":
            supabase.table(TABLE).update({"status": "disconnected"}).eq("id", connection["id"]).execute()
        return
    now = datetime.now(timezone.utc)
    events = await list_events(composio, account_id, user_id, now - calendar_events.LOOK_BACK, now + LOOK_AHEAD)
    await calendar_events.store_events(supabase, connection, events, full=True)
    await apply_bots(recall, connection, events, now)


async def disconnect(supabase: Client, recall: RecallClient, connection: dict[str, Any]) -> None:
    """Removes the rep's upcoming bots and their Composio accounts, then the row."""
    user_id = str(connection["user_id"])
    now = datetime.now(timezone.utc)
    bots = await recall.list_bots({
        "metadata__user_id": user_id,
        "metadata__source": "calendar",
        "join_at_after": now.isoformat(),
    })
    for bot in bots:
        if str(_meta(bot).get("calendar_event_id") or "").startswith(EVENT_PREFIX):
            await recall.delete_bot(str(bot["id"]))
    composio = ComposioClient()
    for account in await composio.active_accounts(
        auth_config_id=settings.COMPOSIO_GOOGLE_CALENDAR_AUTH_CONFIG_ID or "", user_id=user_id
    ):
        await composio.delete_account(str(account["id"]))
    supabase.table(TABLE).delete().eq("id", connection["id"]).execute()


async def sync_all(supabase: Client) -> None:
    """The periodic sync: every Google Calendar connected through Composio."""
    if not configured() or not settings.RECALL_API_KEY:
        return
    rows = supabase.table(TABLE).select("*").eq("platform", PLATFORM).neq("status", "disconnected").execute().data or []
    recall = RecallClient()
    for connection in rows:
        if not is_composio(connection):
            continue
        try:
            await sync(supabase, recall, connection)
        except Exception:
            logger.exception("Calendar sync failed for %s", connection.get("user_id"))
