"""Recall.ai Calendar V2: a rep connects Google Calendar or Outlook, Recall keeps the
events synced (1 day back, 28 days ahead, primary calendar only), and this module decides
which events get the Vocify bot. Recall never schedules on its own in V2.

`should_join` is the rule: the rep's switch is on, the event has a meeting link, it isn't
cancelled, declined by the rep or over, and at least one attendee is outside the rep's
email domain - a sales meeting, not an internal stand-up. Meeting rooms don't count.

One bot per company per meeting: the deduplication key is start time + meeting URL +
company. Two reps of the same company on one call share a bot, and the capture goes to
whichever of them was scheduled last (Recall applies the latest bot_config). A moved
event gets a new key, and scheduling it again replaces the old bot.

OAuth is ours (our Google / Microsoft apps); the refresh token goes straight to Recall,
which refreshes access tokens itself. We never store it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
import jwt
from supabase import Client

from app.config import settings
from app.integrations.recall_client import RecallClient, RecallClientError, bot_config

logger = logging.getLogger(__name__)

TABLE = "calendar_connections"
_STATE_TTL = timedelta(minutes=10)
_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class Provider:
    key: str
    platform: str
    authorize_url: str
    token_url: str
    scope: str
    extra_params: tuple[tuple[str, str], ...]
    client_id_setting: str
    client_secret_setting: str

    @property
    def client_id(self) -> Optional[str]:
        return getattr(settings, self.client_id_setting, None)

    @property
    def client_secret(self) -> Optional[str]:
        return getattr(settings, self.client_secret_setting, None)

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and settings.JWT_SECRET)

    @property
    def redirect_uri(self) -> str:
        return f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}/api/v1/calendar/{self.key}/callback"


# Scopes are the ones Recall documents for Calendar V2. Google only returns a refresh token
# with access_type=offline, and again on reconnect only with prompt=consent.
PROVIDERS: dict[str, Provider] = {
    "google": Provider(
        key="google",
        platform="google_calendar",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scope="https://www.googleapis.com/auth/calendar.events.readonly https://www.googleapis.com/auth/userinfo.email",
        extra_params=(("access_type", "offline"), ("prompt", "consent")),
        client_id_setting="GOOGLE_CALENDAR_CLIENT_ID",
        client_secret_setting="GOOGLE_CALENDAR_CLIENT_SECRET",
    ),
    "microsoft": Provider(
        key="microsoft",
        platform="microsoft_outlook",
        authorize_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
        scope="offline_access openid email https://graph.microsoft.com/Calendars.Read",
        extra_params=(("response_mode", "query"),),
        client_id_setting="MICROSOFT_CALENDAR_CLIENT_ID",
        client_secret_setting="MICROSOFT_CALENDAR_CLIENT_SECRET",
    ),
}


class CalendarOAuthError(Exception):
    """`code` is what the callback puts in the redirect (?calendar=error&error=<code>)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def available_providers() -> list[str]:
    if not settings.RECALL_API_KEY:
        return []
    return [key for key, provider in PROVIDERS.items() if provider.configured]


def build_authorize_url(provider: Provider, *, user_id: str, company_id: str) -> str:
    state = jwt.encode(
        {
            "user_id": user_id,
            "company_id": company_id,
            "provider": provider.key,
            "exp": datetime.now(timezone.utc) + _STATE_TTL,
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    params = {
        "client_id": provider.client_id,
        "redirect_uri": provider.redirect_uri,
        "response_type": "code",
        "scope": provider.scope,
        "state": state,
        **dict(provider.extra_params),
    }
    return f"{provider.authorize_url}?{urlencode(params)}"


def decode_state(state: str, provider: Provider) -> tuple[str, str]:
    """(user_id, company_id). A state minted for the other provider is refused too."""
    try:
        payload = jwt.decode(state, settings.JWT_SECRET or "", algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise CalendarOAuthError("invalid_state") from exc
    user_id, company_id = payload.get("user_id"), payload.get("company_id")
    if payload.get("provider") != provider.key or not user_id or not company_id:
        raise CalendarOAuthError("invalid_state")
    return str(user_id), str(company_id)


async def exchange_code_for_refresh_token(provider: Provider, code: str) -> str:
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        response = await client.post(
            provider.token_url,
            data={
                "client_id": provider.client_id,
                "client_secret": provider.client_secret,
                "code": code,
                "redirect_uri": provider.redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if response.status_code >= 400:
        logger.warning("Calendar token exchange failed (%s): %s", provider.key, response.text[:300])
        raise CalendarOAuthError("token_exchange_failed")
    refresh_token = (response.json() or {}).get("refresh_token")
    if not refresh_token:
        raise CalendarOAuthError("no_refresh_token")
    return str(refresh_token)


# --- stored connection --------------------------------------------------------------


def connection_for_user(supabase: Client, user_id: str) -> Optional[dict[str, Any]]:
    rows = supabase.table(TABLE).select("*").eq("user_id", user_id).limit(1).execute().data or []
    return rows[0] if rows else None


def connection_for_calendar(supabase: Client, recall_calendar_id: str) -> Optional[dict[str, Any]]:
    rows = (
        supabase.table(TABLE).select("*").eq("recall_calendar_id", recall_calendar_id).limit(1).execute().data
        or []
    )
    return rows[0] if rows else None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def connect_calendar(
    supabase: Client, client: RecallClient, provider: Provider, *, user_id: str, company_id: str, refresh_token: str
) -> dict[str, Any]:
    """Creates the Recall calendar and replaces the rep's previous one, if any (one calendar
    per rep). The old Recall calendar is deleted after the new row is saved, so a failure
    in between never leaves the rep with nothing."""
    try:
        calendar = await client.create_calendar(
            platform=provider.platform,
            oauth_client_id=provider.client_id or "",
            oauth_client_secret=provider.client_secret or "",
            oauth_refresh_token=refresh_token,
            metadata={"user_id": user_id, "company_id": company_id},
        )
    except RecallClientError as exc:
        logger.warning("Recall create calendar failed for %s: %s", user_id, exc)
        raise CalendarOAuthError("recall_failed") from exc

    previous = connection_for_user(supabase, user_id)
    row = {
        "user_id": user_id,
        "company_id": company_id,
        "platform": provider.platform,
        "recall_calendar_id": calendar["id"],
        "email": calendar.get("platform_email") or calendar.get("oauth_email"),
        "status": _status(calendar.get("status")),
        # A new calendar gives meeting context; the bot joins only once the rep switches it on.
        "auto_join": previous["auto_join"] if previous else False,
        "updated_at": _now_iso(),
    }
    saved = supabase.table(TABLE).upsert(row, on_conflict="user_id").execute().data or [row]

    if previous and previous.get("recall_calendar_id") != calendar["id"]:
        try:
            await client.delete_calendar(str(previous["recall_calendar_id"]))
        except RecallClientError:
            logger.warning("Recall delete of replaced calendar %s failed", previous["recall_calendar_id"], exc_info=True)
    return saved[0]


async def disconnect_calendar(supabase: Client, client: RecallClient, connection: dict[str, Any]) -> None:
    """Recall removes the calendar's future bots when the calendar is deleted."""
    await client.delete_calendar(str(connection["recall_calendar_id"]))
    supabase.table(TABLE).delete().eq("id", connection["id"]).execute()


def _status(value: Any) -> str:
    return value if value in ("connecting", "connected", "disconnected") else "connecting"


async def refresh_connection(supabase: Client, client: RecallClient, connection: dict[str, Any]) -> dict[str, Any]:
    """Status and email as Recall sees them now (the email is only known once connected)."""
    calendar = await client.get_calendar(str(connection["recall_calendar_id"]))
    changes = {
        "status": _status(calendar.get("status")),
        "email": calendar.get("platform_email") or calendar.get("oauth_email") or connection.get("email"),
        "updated_at": _now_iso(),
    }
    supabase.table(TABLE).update(changes).eq("id", connection["id"]).execute()
    return {**connection, **changes}


# --- which events get a bot ----------------------------------------------------------


def _parse_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _domain(email: Optional[str]) -> str:
    return (email or "").strip().lower().rpartition("@")[2]


def _is_room(attendee: dict[str, Any], email: str) -> bool:
    # Google marks rooms `resource: true` (and gives them *.calendar.google.com addresses);
    # Graph marks them `type: "resource"`.
    return bool(attendee.get("resource")) or attendee.get("type") == "resource" or email.endswith(".calendar.google.com")


def attendee_emails(raw: dict[str, Any]) -> list[str]:
    """People on the invite (organizer included, rooms excluded), from the Google or Graph
    event Recall passes through in `raw`."""
    emails: list[str] = []
    for attendee in raw.get("attendees") or []:
        email = str(attendee.get("email") or (attendee.get("emailAddress") or {}).get("address") or "").strip().lower()
        if email and not _is_room(attendee, email) and email not in emails:
            emails.append(email)
    organizer = raw.get("organizer") or {}
    organizer_email = str(organizer.get("email") or (organizer.get("emailAddress") or {}).get("address") or "")
    organizer_email = organizer_email.strip().lower()
    if organizer_email and organizer_email not in emails:
        emails.append(organizer_email)
    return emails


def _cancelled(raw: dict[str, Any]) -> bool:
    return raw.get("status") == "cancelled" or bool(raw.get("isCancelled"))


def _declined_by_rep(raw: dict[str, Any]) -> bool:
    for attendee in raw.get("attendees") or []:
        if attendee.get("self") and attendee.get("responseStatus") == "declined":
            return True
    return (raw.get("responseStatus") or {}).get("response") == "declined"


def should_join(event: dict[str, Any], *, calendar_email: Optional[str], now: datetime) -> bool:
    if event.get("is_deleted") or not event.get("meeting_url"):
        return False
    end = _parse_time(event.get("end_time"))
    if end and end <= now:
        return False
    raw = event.get("raw") or {}
    if _cancelled(raw) or _declined_by_rep(raw):
        return False
    own_domain = _domain(calendar_email)
    if not own_domain:
        # Without the rep's own address "external" can't be told apart from internal:
        # better no bot than a bot in the team stand-up.
        return False
    return any(_domain(email) != own_domain for email in attendee_emails(raw))


def deduplication_key(event: dict[str, Any], company_id: str) -> str:
    return f"{event.get('start_time')}-{event.get('meeting_url')}-{company_id}"


def calendar_bot_config(connection: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    # `environment`: staging and production share one Recall workspace, so both receive
    # every bot webhook; only the environment that scheduled the bot completes it.
    return bot_config(
        metadata={
            "source": "calendar",
            "environment": settings.ENVIRONMENT,
            "user_id": connection["user_id"],
            "company_id": connection["company_id"],
            "calendar_event_id": event.get("id"),
        }
    )


async def apply_event(client: RecallClient, connection: dict[str, Any], event: dict[str, Any], now: datetime) -> None:
    """Schedules or unschedules the bot for one event. Recall already unschedules bots of
    deleted events, and a finished event is left alone."""
    wanted = (
        bool(connection.get("auto_join"))
        and connection.get("status") != "disconnected"
        and should_join(event, calendar_email=connection.get("email"), now=now)
    )
    key = deduplication_key(event, connection["company_id"])
    bots = event.get("bots") or []
    end = _parse_time(event.get("end_time"))
    try:
        if wanted and not any(bot.get("deduplication_key") == key for bot in bots):
            await client.schedule_event_bot(
                str(event["id"]), deduplication_key=key, config=calendar_bot_config(connection, event)
            )
        elif not wanted and bots and not event.get("is_deleted") and (end is None or end > now):
            await client.unschedule_event_bot(str(event["id"]))
    except RecallClientError as exc:
        # One event failing (e.g. a 507 for a meeting moved to start within 10 minutes)
        # must not stop the rest of the sync; the next change to the event retries it.
        logger.warning("Calendar bot update failed for event %s: %s", event.get("id"), exc)


async def sync_calendar(
    supabase: Client,
    client: RecallClient,
    connection: dict[str, Any],
    *,
    updated_at_gte: Optional[str] = None,
) -> None:
    """With `updated_at_gte` (a calendar.sync_events webhook): only the events that changed.
    Without it (the switch, or the island asking for fresh meetings): every upcoming event.
    Events are stored for meeting context (`calendar_events`) whatever the switch says."""
    if not connection.get("email") or connection.get("status") != "connected":
        connection = await refresh_connection(supabase, client, connection)
    from app.services.meetings import calendar_events

    now = datetime.now(timezone.utc)
    calendar_id = str(connection["recall_calendar_id"])
    if updated_at_gte:
        events = await client.list_calendar_events(calendar_id, updated_at_gte=updated_at_gte)
    else:
        # From a while back too: a meeting already running is kept for linking its recording.
        since = now - calendar_events.LOOK_BACK
        events = await client.list_calendar_events(calendar_id, start_time_gte=since.isoformat())
    await calendar_events.store_events(supabase, connection, events, full=not updated_at_gte)
    for event in events:
        await apply_event(client, connection, event, now)


async def handle_calendar_webhook(
    supabase: Client, event: str, calendar_id: str, last_updated_ts: Optional[str]
) -> None:
    """Runs after the webhook has already answered 200 (Recall times out at 15s)."""
    connection = connection_for_calendar(supabase, calendar_id)
    if not connection:
        logger.info("Calendar webhook %s for unknown calendar %s", event, calendar_id)
        return
    client = RecallClient()
    try:
        if event == "calendar.update":
            await refresh_connection(supabase, client, connection)
        elif event == "calendar.sync_events":
            await sync_calendar(supabase, client, connection, updated_at_gte=last_updated_ts)
    except Exception:
        logger.exception("Calendar webhook %s failed for calendar %s", event, calendar_id)


def rep_calendar_email(supabase: Client, user_id: str) -> Optional[str]:
    """For telling the rep apart in a calendar bot's transcript. Never raises."""
    try:
        connection = connection_for_user(supabase, user_id)
    except Exception:
        logger.warning("Calendar connection lookup failed for %s", user_id, exc_info=True)
        return None
    return (connection or {}).get("email") or None
