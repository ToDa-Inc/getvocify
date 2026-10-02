"""Meetings the rep marked in the CRM, read back for coaching.

A rep who books a meeting often says so in the CRM rather than in Vocify: they move the deal to
the stage the company set as "meeting booked" (crm_configurations.meeting_booked_stage_id). That
is the rep's own declaration, never a model's reading, so it counts like `memos.rep_outcome`.

Each deal that ever entered that stage is credited to the call that booked it: the company's
latest call to one of the deal's contacts (or on the deal itself) in the days before the deal
entered the stage. Read-only: GETs and HubSpot's read endpoints (search, batch read). A failed
or slow read gives nothing, never a guess; results are cached per company for a few minutes.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

MEETING_BOOKED = "meeting_booked"
# The rep moves the deal after the call: the same day, or a few days later at the latest.
CREDIT_WINDOW = timedelta(days=7)
CACHE_SECONDS = 600
TIMEOUT_SECONDS = 8.0
_cache: dict[str, tuple[float, list[dict]]] = {}
_lock = threading.Lock()


def _instant(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def meeting_stage(supabase: Any, company_id: str) -> Optional[dict]:
    """The company's configured meeting-booked stage (any member's CRM settings carry it)."""
    try:
        members = (
            supabase.table("company_members").select("user_id").eq("company_id", company_id)
            .eq("status", "active").execute()
        ).data or []
        ids = [str(row["user_id"]) for row in members if row.get("user_id")]
        if not ids:
            return None
        rows = (
            supabase.table("crm_configurations").select("meeting_booked_pipeline_id,meeting_booked_stage_id")
            .in_("user_id", ids).execute()
        ).data or []
    except Exception:
        logger.warning("crm meetings: settings read failed", exc_info=True)
        return None
    for row in rows:
        stage = str(row.get("meeting_booked_stage_id") or "").strip()
        if stage:
            return {"pipeline_id": str(row.get("meeting_booked_pipeline_id") or "").strip() or None, "stage_id": stage}
    return None


def booked_deals_from_hubspot(get: Callable, post: Callable, stage_id: str) -> list[dict]:
    """Every deal that entered `stage_id` at some point: {deal_id, entered_at, contact_ids}."""
    entered = f"hs_v2_date_entered_{stage_id}"
    deals: list[dict] = []
    after = None
    while True:
        body: dict = {
            "filterGroups": [{"filters": [{"propertyName": entered, "operator": "HAS_PROPERTY"}]}],
            "properties": [entered], "limit": 100,
        }
        if after:
            body["after"] = after
        page = post("/crm/v3/objects/deals/search", body) or {}
        for row in page.get("results") or []:
            at = _instant((row.get("properties") or {}).get(entered))
            if at:
                deals.append({"deal_id": str(row["id"]), "entered_at": at, "contact_ids": []})
        after = ((page.get("paging") or {}).get("next") or {}).get("after")
        if not after or len(deals) >= 5000:
            break
    by_id = {deal["deal_id"]: deal for deal in deals}
    ids = list(by_id)
    for start in range(0, len(ids), 100):
        links = post(
            "/crm/v4/associations/deals/contacts/batch/read",
            {"inputs": [{"id": deal_id} for deal_id in ids[start:start + 100]]},
        ) or {}
        for result in links.get("results") or []:
            deal = by_id.get(str((result.get("from") or {}).get("id")))
            if deal is not None:
                deal["contact_ids"] = [str(link["toObjectId"]) for link in result.get("to") or [] if link.get("toObjectId")]
    return deals


def credit_calls(deals: list[dict], memos: list[dict]) -> dict[str, datetime]:
    """memo_id -> when the meeting it booked was marked: per deal, the latest call on one of its
    contacts (or on the deal) up to CREDIT_WINDOW before the deal entered the stage."""
    by_key: dict[str, list[tuple[datetime, str]]] = {}
    for memo in memos:
        at = _instant(memo.get("capture_started_at")) or _instant(memo.get("created_at"))
        memo_id = str(memo.get("id") or "")
        if not at or not memo_id:
            continue
        for key in (memo.get("hubspot_contact_id"), memo.get("hubspot_deal_id")):
            if key:
                by_key.setdefault(str(key), []).append((at, memo_id))
    credited: dict[str, datetime] = {}
    for deal in deals:
        entered = deal["entered_at"]
        candidates = [
            (at, memo_id)
            for key in [deal["deal_id"], *deal["contact_ids"]]
            for at, memo_id in by_key.get(key, [])
            if entered - CREDIT_WINDOW <= at <= entered + timedelta(hours=1)
        ]
        if candidates:
            at, memo_id = max(candidates)
            credited[memo_id] = entered
    return credited


def _hubspot_deals(supabase: Any, company_id: str, stage_id: str) -> list[dict]:
    with _lock:
        hit = _cache.get(company_id)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
    import httpx

    from app.services.hubspot.oauth import ensure_fresh_hubspot_connection
    from app.services.playbooks.routing import crm_connection

    connection = crm_connection(supabase, company_id)
    if not connection or connection.get("provider") != "hubspot":
        return []
    connection = ensure_fresh_hubspot_connection(supabase, connection)
    headers = {"Authorization": f"Bearer {connection.get('access_token')}"}
    with httpx.Client(base_url="https://api.hubapi.com", headers=headers, timeout=TIMEOUT_SECONDS) as client:
        def get(path: str, params: dict | None = None) -> dict:
            response = client.get(path, params=params or {})
            response.raise_for_status()
            return response.json()

        def post(path: str, body: dict) -> dict:  # HubSpot's search and batch-read endpoints: reads only
            response = client.post(path, json=body)
            response.raise_for_status()
            return response.json()

        deals = booked_deals_from_hubspot(get, post, stage_id)
    with _lock:
        _cache[company_id] = (time.monotonic(), deals)
    return deals


def apply_crm_meetings(supabase: Any, company_id: Optional[str], memos: list[dict]) -> list[dict]:
    """Memos whose call booked a meeting the rep marked in the CRM get rep_outcome
    "meeting_booked" (an outcome the rep already set in Vocify always wins). Never raises."""
    if not company_id or not memos:
        return memos
    try:
        stage = meeting_stage(supabase, str(company_id))
        if not stage:
            return memos
        credited = credit_calls(_hubspot_deals(supabase, str(company_id), stage["stage_id"]), memos)
    except Exception:
        logger.warning("crm meetings: read failed; coaching keeps the rep's Vocify outcomes only", exc_info=True)
        return memos
    if not credited:
        return memos
    return [
        {**memo, "rep_outcome": MEETING_BOOKED} if str(memo.get("id")) in credited and not memo.get("rep_outcome") else memo
        for memo in memos
    ]


# Proposal decisions where the rep confirmed the meeting in Vocify (meetings/accept.py).
_ACCEPTED_PROPOSALS = ("accepted", "corrected")


def _accepted_proposal_memo_ids(supabase: Any, memo_ids: list[str], batch: int) -> set[str]:
    found: set[str] = set()
    for start in range(0, len(memo_ids), batch):
        try:
            rows = (
                supabase.table("meeting_proposals").select("memo_id,decision")
                .in_("memo_id", memo_ids[start:start + batch]).execute()
            ).data or []
        except Exception:
            logger.warning("rep meetings: proposals read failed", exc_info=True)
            return found
        found.update(str(row["memo_id"]) for row in rows if row.get("memo_id") and row.get("decision") in _ACCEPTED_PROPOSALS)
    return found


def apply_rep_meetings(supabase: Any, memos: list[dict], *, batch: int = 100) -> list[dict]:
    """Every way a rep declares a booked meeting, in one place: their outcome after the call
    (rep_outcome), the meeting proposal they accepted in Vocify, or the deal they moved to the
    company's meeting-booked stage in the CRM. Never what a model read in the call. Never raises."""
    if not memos:
        return memos
    ids = [str(memo["id"]) for memo in memos if memo.get("id") and not memo.get("rep_outcome")]
    accepted = _accepted_proposal_memo_ids(supabase, ids, batch) if ids else set()
    marked = [
        {**memo, "rep_outcome": MEETING_BOOKED} if str(memo.get("id")) in accepted and not memo.get("rep_outcome") else memo
        for memo in memos
    ]
    by_company: dict[str, list[int]] = {}
    for index, memo in enumerate(marked):
        if memo.get("company_id"):
            by_company.setdefault(str(memo["company_id"]), []).append(index)
    for company_id, indexes in by_company.items():
        updated = apply_crm_meetings(supabase, company_id, [marked[i] for i in indexes])
        for index, memo in zip(indexes, updated):
            marked[index] = memo
    return marked


def rep_declared_meeting(memo: dict) -> bool:
    return memo.get("rep_outcome") == MEETING_BOOKED
