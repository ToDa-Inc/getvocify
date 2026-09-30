"""A rep's calendar for the Recall.ai meeting bot (Calendar V2): connect Google Calendar or
Outlook, switch "the bot joins my meetings" on or off, disconnect. Behind RECALL_BOT_ENABLED,
like POST /meetings/bot. Which events get a bot is decided in
app.services.meetings.calendar_bots, on Recall's calendar webhooks and when the switch flips."""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from supabase import Client

from app.config import settings
from app.deps import get_membership, get_supabase
from app.integrations.recall_client import RecallClient, RecallClientError
from app.services.company import Membership
from app.services.feature_flags import is_enabled
from app.services.meetings import calendar_bots

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
