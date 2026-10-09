"""GET /contacts/{contact_id}/recent-activity: what has happened with a contact lately, and with other people at its
company, from HubSpot and Vocify, and a short summary of each that only says what those interactions say (see
services/contacts/recent_activity.py).
"""

from __future__ import annotations

import asyncio

import hashlib
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import settings
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.contacts.recent_activity import (
    COLLEAGUES_LIMIT,
    memo_interactions,
    newest_first,
    read_company_activity,
    read_hubspot_activity,
    read_hubspot_company,
    read_people,
    summarize,
    with_people,
    without_pushed,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["contacts"])

SUMMARY_TIMEOUT_S = 12
_CACHE_TTL_S = 15 * 60
_CACHE_MAX = 500
_cache: dict[str, tuple[float, Any]] = {}


def hubspot_client_for(supabase, user_id: str):
    """The company's HubSpot connection (raises when there is none)."""
    from app.api.crm import get_hubspot_client_from_connection

    return get_hubspot_client_from_connection(user_id, supabase)


def read_contact_memos(supabase, membership: Membership, contact_id: str) -> list[dict]:
    """The contact's Vocify memos this rep may see (the same scope as the contact brief)."""
    from app.api.briefs import _handoff_restricted_user_ids, _read_memos

    allowed = _handoff_restricted_user_ids(supabase, membership, connection_id="hubspot", contact_id=contact_id)
    rows, coverage = _read_memos(supabase, membership.company_id, contact_id, allowed_user_ids=allowed)
    if coverage == "unavailable":
        raise RuntimeError("memos unavailable")
    return rows


def read_colleague_memos(supabase, membership: Membership, contact_ids: list[str]) -> list[dict]:
    """Vocify conversations with other contacts at the company. A rep without company-wide visibility (handoff on)
    sees only their own: what a colleague recorded with someone else is not theirs to read."""
    from app.api.briefs import _handoff_restricted_user_ids

    restricted = _handoff_restricted_user_ids(supabase, membership, connection_id="hubspot", contact_id="") is not None
    rows: list[dict] = []
    for start in range(0, len(contact_ids), 100):
        query = (
            supabase.table("memos")
            .select("id,created_at,capture_started_at,extraction,hubspot_contact_id,user_id")
            .eq("company_id", membership.company_id)
            .in_("hubspot_contact_id", contact_ids[start:start + 100])
            .order("created_at", desc=True)
            .limit(50)
        )
        if restricted:
            query = query.eq("user_id", membership.user_id)
        rows += query.execute().data or []
    return rows


def vocify_pushed_ids(supabase, company_id: str, memo_ids: list[str]) -> set[str]:
    """The HubSpot calls and notes that are these Vocify conversations: the call a memo was recorded from (or Vocify
    dialed), and the note Vocify wrote for it."""
    if not memo_ids:
        return set()
    pushed: set[str] = set()
    memos = supabase.table("memos").select("hubspot_engagement_id").eq("company_id", company_id).in_("id", memo_ids).execute()
    pushed |= {f"hubspot:call:{row['hubspot_engagement_id']}" for row in memos.data or [] if row.get("hubspot_engagement_id")}
    dialed = supabase.table("outbound_calls").select("hubspot_engagement_id").in_("memo_id", memo_ids).execute()
    pushed |= {f"hubspot:call:{row['hubspot_engagement_id']}" for row in dialed.data or [] if row.get("hubspot_engagement_id")}
    notes = (
        supabase.table("crm_updates")
        .select("resource_id")
        .in_("memo_id", memo_ids)
        .eq("action_type", "create_note")
        .execute()
    )
    pushed |= {f"hubspot:note:{row['resource_id']}" for row in notes.data or [] if row.get("resource_id")}
    return pushed


async def summarize_json(messages: list[dict]) -> Any:
    from app.services.llm import LLMClient

    model = settings.EXTRACTION_MODEL
    return await LLMClient(model=model).chat_json(messages, model=model, temperature=0.0, timeout=SUMMARY_TIMEOUT_S, max_retries=1)


def clear_cache() -> None:
    _cache.clear()


def _cache_key(company_id: str, contact_id: str, interactions: list[dict], company: dict | None, company_interactions: list[dict]) -> str:
    material = json.dumps([company_id, contact_id, interactions, company, company_interactions], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(material.encode()).hexdigest()


async def _cached_summary(key: str, interactions: list[dict], company: dict | None, company_interactions: list[dict]):
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < _CACHE_TTL_S:
        return hit[1]
    summary = await summarize(interactions, company, summarize_json, company_interactions)
    # A failed answer, or one left with no grounded line, is not kept: the next look asks again.
    if summary is not None and (summary.get("lines") or summary.get("company_lines")):
        if len(_cache) >= _CACHE_MAX:
            _cache.pop(next(iter(_cache)))
        _cache[key] = (now, summary)
    return summary


@router.get("/contacts/{contact_id}/recent-activity")
async def get_recent_activity(
    contact_id: str,
    connection_id: str = "hubspot",
    summary: bool = True,
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    if connection_id != "hubspot":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only HubSpot contacts for now")

    hubspot_sources: dict[str, str]
    company = None
    try:
        client = hubspot_client_for(supabase, membership.user_id)
    except Exception:
        client = None
    if client is None:
        hubspot_interactions, hubspot_sources = [], {k: "failed" for k in ("emails", "notes", "calls", "meetings", "tasks")}
        company_source = "failed"
    else:
        (hubspot_interactions, hubspot_sources), (company, company_source) = await asyncio.gather(
            read_hubspot_activity(client, contact_id), read_hubspot_company(client, contact_id)
        )

    try:
        vocify = memo_interactions(read_contact_memos(supabase, membership, contact_id))
        vocify_source = "read"
    except Exception:
        logger.warning("Recent activity: memos for contact %s could not be read", contact_id, exc_info=True)
        vocify, vocify_source = [], "failed"

    # Others at the company: HubSpot activity filed under it, and Vocify conversations with its other contacts.
    company_hubspot: list[dict] = []
    company_sources: dict[str, str] = {"company": company_source}
    colleague_memos: list[dict] = []
    if client is not None and company is not None:
        own = {item["id"] for item in hubspot_interactions}
        company_hubspot, colleagues, kind_sources = await read_company_activity(client, company, contact_id, own)
        company_sources.update(kind_sources)
        try:
            colleague_memos = memo_interactions(read_colleague_memos(supabase, membership, colleagues[:COLLEAGUES_LIMIT]), colleagues=True) if colleagues else []
            company_sources["vocify"] = "read"
        except Exception:
            logger.warning("Recent activity: memos with others at %s could not be read", company["id"], exc_info=True)
            company_sources["vocify"] = "failed"

    try:
        memo_ids = [item["id"].split(":")[-1] for item in vocify + colleague_memos]
        pushed = vocify_pushed_ids(supabase, membership.company_id, memo_ids)
    except Exception:
        logger.warning("Recent activity: could not tell which HubSpot items Vocify logged", exc_info=True)
        pushed = set()

    interactions = newest_first(without_pushed(hubspot_interactions, pushed) + vocify)
    others = without_pushed(company_hubspot, pushed) + colleague_memos
    people_ids = sorted({item["with_id"] for item in others if item.get("with_id")})
    people = await read_people(client, people_ids) if client is not None and people_ids else {}
    company_interactions = newest_first(with_people(others, people))

    brief = None
    if summary:
        key = _cache_key(membership.company_id, contact_id, interactions, company, company_interactions)
        brief = await _cached_summary(key, interactions, company, company_interactions)
        if brief is not None:
            brief = {**brief, "model": settings.EXTRACTION_MODEL}

    return {
        "contact_id": contact_id,
        "interactions": interactions,
        "company": company,
        "company_interactions": company_interactions,
        "summary": brief,
        "sources": {
            "hubspot": {**hubspot_sources, "company": company_source},
            "hubspot_company": company_sources,
            "vocify": vocify_source,
        },
    }
