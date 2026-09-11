"""
Opt-in auto-approve after extraction (the dangerous path).

When crm_configurations.auto_sync_hubspot_calls is on, a finished memo with
a locked contact or deal is approved without waiting for the rep. HubSpot
recordings also start transcribe on the webhook. Lead status is never
written. New deals are never created. Off by default.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from supabase import Client

from app.logging_config import DOMAIN_MEMO, log_domain
from app.models.memo import ApproveMemoRequest

logger = logging.getLogger(__name__)


def recording_ready_jobs(events: list) -> list[tuple[str, str]]:
    """Return (portal_id, call_id) for webhook events with a recording URL."""
    jobs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for ev in events:
        if not isinstance(ev, dict):
            continue
        sub = ev.get("subscriptionType") or ev.get("subscription_type")
        if sub not in ("engagement.propertyChange", "object.propertyChange"):
            continue
        if ev.get("propertyName") != "hs_call_recording_url":
            continue
        val = (ev.get("propertyValue") or ev.get("property_value") or "").strip()
        if not val:
            continue
        portal = ev.get("portalId") if ev.get("portalId") is not None else ev.get("portal_id")
        call_id = ev.get("objectId") if ev.get("objectId") is not None else ev.get("object_id")
        if portal is None or call_id is None:
            continue
        key = (str(portal), str(call_id))
        if key in seen:
            continue
        seen.add(key)
        jobs.append(key)
    return jobs


def connection_matches_portal(metadata: Optional[dict], portal_id: str) -> bool:
    if not portal_id:
        return False
    stored = (metadata or {}).get("portal_id")
    return stored is not None and str(stored) == str(portal_id)


def should_start_auto_sync(enabled: Optional[bool]) -> bool:
    return bool(enabled)


def resolve_auto_sync_user_id(
    call_owner_id: Optional[str],
    owner_to_user: dict[str, str],
    fallback_user_id: Optional[str],
    *,
    team_size: int = 1,
) -> Optional[str]:
    if call_owner_id:
        mapped = owner_to_user.get(str(call_owner_id))
        if mapped:
            return str(mapped)
        if team_size > 1:
            return None
    return str(fallback_user_id) if fallback_user_id else None


def should_auto_approve(
    *,
    auto_sync_enabled: bool,
    contact_id: Optional[str],
    deal_id: Optional[str],
    screening_outcome: Optional[str] = None,
) -> bool:
    if not auto_sync_enabled:
        return False
    outcome = (screening_outcome or "").strip()
    if outcome and outcome != "connected":
        return False
    return bool((contact_id or "").strip() or (deal_id or "").strip())


def approval_payload_for_auto_sync(
    *,
    contact_id: Optional[str],
    deal_id: Optional[str],
) -> ApproveMemoRequest:
    deal = (deal_id or "").strip() or None
    contact = (contact_id or "").strip() or None
    return ApproveMemoRequest(
        deal_id=deal,
        is_new_deal=False,
        contact_id=contact,
        skip_deal=not bool(deal),
        create_note=True,
        call_outcome=None,
    )


def find_hubspot_connection_for_portal(
    supabase: Client,
    portal_id: str,
) -> Optional[dict[str, Any]]:
    result = (
        supabase.table("crm_connections")
        .select("*")
        .eq("provider", "hubspot")
        .eq("status", "connected")
        .execute()
    )
    for row in result.data or []:
        if connection_matches_portal(row.get("metadata"), portal_id):
            return row
    return None


def auto_sync_enabled_for_connection(supabase: Client, connection_id: str) -> bool:
    try:
        result = (
            supabase.table("crm_configurations")
            .select("auto_sync_hubspot_calls")
            .eq("connection_id", connection_id)
            .limit(1)
            .execute()
        )
    except Exception:
        return False
    rows = result.data or []
    if not rows:
        return False
    return should_start_auto_sync(rows[0].get("auto_sync_hubspot_calls"))


async def resolve_user_for_hubspot_call(
    supabase: Client,
    connection: dict[str, Any],
    access_token: str,
    call_id: str,
) -> Optional[str]:
    from app.services.activity_scope import invert_hubspot_owners
    from app.services.company import CompanyService
    from app.services.hubspot.calls import get_call_engagement
    from app.services.hubspot.client import HubSpotClient
    from app.services.hubspot.sync import cache_owners_for_members

    fallback = str(connection.get("user_id") or "") or None
    client = HubSpotClient(access_token)
    engagement = await get_call_engagement(client, str(call_id))
    props = (engagement or {}).get("properties") or {}
    owner_id = str(props.get("hubspot_owner_id") or "").strip() or None
    owner_to_user = invert_hubspot_owners(connection.get("metadata") or {})
    members: list[dict] = []
    company_id = connection.get("company_id")
    if company_id:
        members = CompanyService(supabase).list_members(str(company_id))
        matched = await cache_owners_for_members(
            client, supabase, connection["id"], members
        )
        owner_to_user = {hid: uid for uid, hid in matched.items()}
    team_size = len(members) if members else 1
    return resolve_auto_sync_user_id(
        owner_id, owner_to_user, fallback, team_size=team_size
    )


async def handle_hubspot_recording_events(
    supabase: Client,
    events: list,
) -> tuple[int, int]:
    """Start auto-sync for recording-ready webhook events. Returns (started, skipped)."""
    from app.services.hubspot.call_processor import enqueue_hubspot_call_process
    from app.services.hubspot.token_refresh import ensure_hubspot_connection_tokens_fresh

    started = 0
    skipped = 0
    for portal_id, call_id in recording_ready_jobs(events):
        conn = find_hubspot_connection_for_portal(supabase, portal_id)
        if not conn or not auto_sync_enabled_for_connection(supabase, str(conn["id"])):
            skipped += 1
            continue
        try:
            conn = await ensure_hubspot_connection_tokens_fresh(supabase, conn)
        except Exception as exc:
            logger.warning("HubSpot auto-sync token refresh failed: %s", exc)
            skipped += 1
            continue
        access_token = (conn.get("access_token") or "").strip()
        if not access_token:
            skipped += 1
            continue
        user_id = await resolve_user_for_hubspot_call(
            supabase, conn, access_token, call_id
        )
        if not user_id:
            skipped += 1
            continue
        try:
            result = await enqueue_hubspot_call_process(
                supabase, user_id, call_id, access_token
            )
        except Exception:
            logger.exception(
                "HubSpot auto-sync enqueue failed",
                extra=log_domain(
                    DOMAIN_MEMO, "hubspot_auto_sync_enqueue_failed", call_id=call_id
                ),
            )
            skipped += 1
            continue
        if not result.get("memo_id"):
            skipped += 1
            continue
        if result.get("status") == "pending_review":
            await maybe_auto_approve_hubspot_call(
                supabase, str(result["memo_id"]), user_id
            )
        started += 1
    return started, skipped


async def maybe_auto_approve_hubspot_call(
    supabase: Client,
    memo_id: str,
    user_id: str,
) -> bool:
    """Approve a finished memo when the workspace auto-accept toggle is on."""
    from app.services.crm_config import CRMConfigurationService
    from app.services.memo_approval import approve_memo_core

    fetched = (
        supabase.table("memos")
        .select(
            "id,status,source,hubspot_contact_id,hubspot_deal_id,"
            "matched_deal_id,screening_outcome"
        )
        .eq("id", memo_id)
        .limit(1)
        .execute()
    )
    data = (fetched.data or [None])[0]
    if not data:
        return False
    if data.get("status") != "pending_review":
        return False

    config = await CRMConfigurationService(supabase).get_configuration(user_id)
    enabled = bool(config and getattr(config, "auto_sync_hubspot_calls", False))
    contact_id = data.get("hubspot_contact_id")
    deal_id = data.get("hubspot_deal_id") or data.get("matched_deal_id")
    if not should_auto_approve(
        auto_sync_enabled=enabled,
        contact_id=contact_id,
        deal_id=deal_id,
        screening_outcome=data.get("screening_outcome"),
    ):
        return False

    payload = approval_payload_for_auto_sync(contact_id=contact_id, deal_id=deal_id)
    try:
        await approve_memo_core(supabase, memo_id, user_id, payload)
    except Exception:
        logger.exception(
            "CRM auto-approve failed",
            extra=log_domain(DOMAIN_MEMO, "crm_auto_approve_failed", memo_id=memo_id),
        )
        return False
    logger.info(
        "CRM auto-approved",
        extra=log_domain(DOMAIN_MEMO, "crm_auto_approved", memo_id=memo_id),
    )
    return True
