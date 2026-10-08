"""A rep's calendar (Recall.ai Calendar V2): connect Google Calendar or Outlook, see the
upcoming meetings with outside people (for the island's heads-up and brief), switch "the bot
joins my meetings" on or off, disconnect. Behind RECALL_BOT_ENABLED, like POST /meetings/bot.
Which events get a bot is decided in app.services.meetings.calendar_bots, on Recall's
calendar webhooks and when the switch flips; stored meetings live in calendar_events."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from supabase import Client

from app.config import settings
from app.deps import get_membership, get_supabase
from app.integrations.recall_client import RecallClient, RecallClientError
from app.services.company import Membership
from app.services.feature_flags import is_enabled
from app.services.meetings import calendar_bots, calendar_events

RECALL_BOT_FLAG = "RECALL_BOT_ENABLED"

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/calendar", tags=["calendar"])


class CalendarConnection(BaseModel):
    platform: str
    email: Optional[str] = None
    status: str
    auto_join: bool


class CalendarState(BaseModel):
    providers: list[str]
    connection: Optional[CalendarConnection] = None


class CalendarUpdate(BaseModel):
    auto_join: bool


class MeetingPerson(BaseModel):
    name: Optional[str] = None
    email: str
    # From another company than the rep (only they are looked up in HubSpot).
    external: bool = False
    hubspot_contact_id: Optional[str] = None


class UpcomingMeeting(BaseModel):
    id: str
    title: Optional[str] = None
    start_time: str
    end_time: Optional[str] = None
    meeting_url: str
    platform: Optional[str] = None
    # Everyone but the rep, people from outside first; HubSpot names when matched.
    people: list[MeetingPerson]


def _require_flag(supabase: Client, membership: Membership) -> None:
    if not is_enabled(supabase, membership.company_id, RECALL_BOT_FLAG):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def _state(connection: Optional[dict]) -> CalendarState:
    return CalendarState(
        providers=calendar_bots.available_providers(),
        connection=CalendarConnection(
            platform=connection["platform"],
            email=connection.get("email"),
            status=connection["status"],
            auto_join=bool(connection["auto_join"]),
        )
        if connection
        else None,
    )


def _provider(key: str) -> calendar_bots.Provider:
    provider = calendar_bots.PROVIDERS.get(key)
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    return provider


@router.get("", response_model=CalendarState)
async def get_calendar(
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
):
    _require_flag(supabase, membership)
    return _state(calendar_bots.connection_for_user(supabase, membership.user_id))


@router.get("/upcoming", response_model=list[UpcomingMeeting])
async def upcoming_meetings(
    hours: int = Query(12, ge=1, le=48),
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
):
    """The rep's next meetings with someone else and a call link (internal ones too), soonest
    first. Empty without a connected calendar. Refreshes from Recall when the last full sync is over 5 minutes old,
    so it stays current even when a calendar webhook is missed."""
    if not is_enabled(supabase, membership.company_id, RECALL_BOT_FLAG):
        return []
    connection = calendar_bots.connection_for_user(supabase, membership.user_id)
    if not connection or connection.get("status") == "disconnected":
        return []
    now = datetime.now(timezone.utc)
    if calendar_events.is_stale(connection, now):
        try:
            await calendar_bots.sync_calendar(supabase, RecallClient(), connection)
        except Exception:
            logger.warning("Calendar refresh failed for %s", membership.user_id, exc_info=True)
    horizon = timedelta(hours=hours)
    try:
        rows = calendar_events.rows_for_user(supabase, membership.user_id, now - calendar_events.LOOK_BACK, now + horizon)
    except Exception:
        # e.g. migration 077 not applied yet: no heads-up rather than an error on every poll.
        logger.warning("Reading upcoming meetings failed for %s", membership.user_id, exc_info=True)
        return []
    return [
        UpcomingMeeting(
            id=row["recall_event_id"],
            title=row.get("title"),
            start_time=row["start_time"],
            end_time=row.get("end_time"),
            meeting_url=row["meeting_url"],
            platform=calendar_events.platform_of(row["meeting_url"]),
            people=[
                MeetingPerson(
                    name=calendar_events.person_name(p),
                    email=p["email"],
                    external=bool(p.get("external")),
                    hubspot_contact_id=p.get("hubspot_contact_id"),
                )
                for p in calendar_events.people_outside_first(row)
            ],
        )
        for row in calendar_events.upcoming(rows, now, horizon)
    ]


@router.get("/{provider_key}/authorize")
async def authorize(
    provider_key: str,
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
):
    _require_flag(supabase, membership)
    provider = _provider(provider_key)
    if provider_key not in calendar_bots.available_providers():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Este calendario no está configurado",
        )
    url = calendar_bots.build_authorize_url(
        provider, user_id=membership.user_id, company_id=membership.company_id
    )
    return {"redirect_url": url}


@router.get("/{provider_key}/callback")
async def callback(
    provider_key: str,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    supabase: Client = Depends(get_supabase),
):
    """Google / Microsoft send the rep back here. No session: `state` says who they are."""
    back = f"{settings.FRONTEND_URL.rstrip('/')}/dashboard/settings/calling"

    def fail(code_: str) -> RedirectResponse:
        return RedirectResponse(f"{back}?{urlencode({'calendar': 'error', 'error': code_})}", status_code=302)

    provider = calendar_bots.PROVIDERS.get(provider_key)
    if not provider or provider_key not in calendar_bots.available_providers():
        return fail("not_configured")
    if error:
        return fail(error)
    if not code or not state:
        return fail("missing_params")
    try:
        user_id, company_id = calendar_bots.decode_state(state, provider)
        refresh_token = await calendar_bots.exchange_code_for_refresh_token(provider, code)
        await calendar_bots.connect_calendar(
            supabase,
            RecallClient(),
            provider,
            user_id=user_id,
            company_id=company_id,
            refresh_token=refresh_token,
        )
    except calendar_bots.CalendarOAuthError as exc:
        return fail(exc.code)
    except Exception:
        logger.exception("Calendar connect failed (%s)", provider_key)
        return fail("save_failed")
    return RedirectResponse(f"{back}?calendar=connected", status_code=302)


@router.patch("", response_model=CalendarState)
async def update_calendar(
    body: CalendarUpdate,
    background_tasks: BackgroundTasks,
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
):
    """The switch. Upcoming meetings are scheduled or unscheduled right after the answer."""
    _require_flag(supabase, membership)
    connection = calendar_bots.connection_for_user(supabase, membership.user_id)
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hay calendario conectado")
    supabase.table(calendar_bots.TABLE).update({"auto_join": body.auto_join}).eq("id", connection["id"]).execute()
    connection = {**connection, "auto_join": body.auto_join}
    background_tasks.add_task(_sync_upcoming, supabase, connection)
    return _state(connection)


async def _sync_upcoming(supabase: Client, connection: dict) -> None:
    try:
        await calendar_bots.sync_calendar(supabase, RecallClient(), connection)
    except Exception:
        logger.exception("Calendar resync after switch failed for %s", connection.get("user_id"))


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_calendar(
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
):
    _require_flag(supabase, membership)
    connection = calendar_bots.connection_for_user(supabase, membership.user_id)
    if not connection:
        return None
    try:
        await calendar_bots.disconnect_calendar(supabase, RecallClient(), connection)
    except RecallClientError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return None
