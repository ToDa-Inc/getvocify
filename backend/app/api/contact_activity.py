"""GET /contacts/{contact_id}/recent-activity: what has happened with a contact lately, from HubSpot and Vocify, and a
two-or-three-line summary of it that only says what those interactions say (see services/contacts/recent_activity.py).
"""

from __future__ import annotations

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
    memo_interactions,
    newest_first,
    read_hubspot_activity,
    read_hubspot_company,
    summarize,
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


async def summarize_json(messages: list[dict]) -> Any:
    from app.services.llm import LLMClient

    model = settings.EXTRACTION_MODEL
    return await LLMClient(model=model).chat_json(messages, model=model, temperature=0.0, timeout=SUMMARY_TIMEOUT_S, max_retries=1)


def clear_cache() -> None:
    _cache.clear()


def _cache_key(company_id: str, contact_id: str, interactions: list[dict], company: dict | None) -> str:
    material = json.dumps([company_id, contact_id, interactions, company], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(material.encode()).hexdigest()


async def _cached_summary(key: str, interactions: list[dict], company: dict | None):
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < _CACHE_TTL_S:
        return hit[1]
    summary = await summarize(interactions, company, summarize_json)
    # A failed answer, or one left with no grounded line, is not kept: the next look asks again.
    if summary is not None and summary.get("lines"):
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
        hubspot_interactions, hubspot_sources = await read_hubspot_activity(client, contact_id)
        company, company_source = await read_hubspot_company(client, contact_id)

    try:
        vocify = memo_interactions(read_contact_memos(supabase, membership, contact_id))
        vocify_source = "read"
    except Exception:
        logger.warning("Recent activity: memos for contact %s could not be read", contact_id, exc_info=True)
        vocify, vocify_source = [], "failed"

    interactions = newest_first(hubspot_interactions + vocify)
    brief = None
    if summary:
        brief = await _cached_summary(_cache_key(membership.company_id, contact_id, interactions, company), interactions, company)
        if brief is not None:
            brief = {**brief, "model": settings.EXTRACTION_MODEL}

    return {
        "contact_id": contact_id,
        "interactions": interactions,
        "company": company,
        "summary": brief,
        "sources": {"hubspot": {**hubspot_sources, "company": company_source}, "vocify": vocify_source},
    }
