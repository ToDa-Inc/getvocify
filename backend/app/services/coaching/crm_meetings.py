"""Meetings the rep marked in the CRM, read back for coaching.

A rep who books a meeting often says so in the CRM rather than in Vocify: they move the deal to
the stage the company set as "meeting booked" (crm_configurations.meeting_booked_stage_id), or,
an SDR with no deal yet, set the contact's lead status to converted (lost / not qualified for a
loss). That is the rep's own declaration, never a model's reading, so it counts like
`memos.rep_outcome`.

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
_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}  # (company, stage) -> deals that entered it
_lock = threading.Lock()


def _instant(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


_stage_cache: dict[str, tuple[float, Optional[dict]]] = {}


def meeting_stage(supabase: Any, company_id: str) -> Optional[dict]:
    """The company's configured meeting-booked stage (any member's CRM settings carry it).
    Settings rarely change: cached per company for CACHE_SECONDS."""
    with _lock:
        hit = _stage_cache.get(company_id)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
    stage = _read_meeting_stage(supabase, company_id)
    with _lock:
        _stage_cache[company_id] = (time.monotonic(), stage)
    return stage


def _read_meeting_stage(supabase: Any, company_id: str) -> Optional[dict]:
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


def _hubspot_read(supabase: Any, company_id: str, read: Callable[[Callable, Callable], Any]) -> Any:
    """Run `read(get, post)` against the company's HubSpot, or None when it has no HubSpot."""
    import httpx

    from app.services.hubspot.oauth import ensure_fresh_hubspot_connection
    from app.services.playbooks.routing import crm_connection

    connection = crm_connection(supabase, company_id)
    if not connection or connection.get("provider") != "hubspot":
        return None
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

        return read(get, post)


def _hubspot_deals(supabase: Any, company_id: str, stage_id: str) -> list[dict]:
    with _lock:
        hit = _cache.get((company_id, stage_id))
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
    deals = _hubspot_read(supabase, company_id, lambda get, post: booked_deals_from_hubspot(get, post, stage_id)) or []
    with _lock:
        _cache[(company_id, stage_id)] = (time.monotonic(), deals)
    return deals


# Lead status (the contact's hs_lead_status): where an SDR marks how a cold call ended, often with
# no deal yet. Read by the option's label or internal value, so a portal's own options match too.
LOST = "lost"
_LEAD_STATUS_OUTCOMES = {
    "converted": MEETING_BOOKED, "convertido": MEETING_BOOKED,
    "lost": LOST, "perdido": LOST,
    "not qualified": LOST, "not_qualified": LOST, "unqualified": LOST, "no cualificado": LOST,
}
_LEAD_STATUS_BATCH = 50
_status_cache: dict[str, tuple[float, dict[str, str], dict[str, list[dict]]]] = {}  # company -> (at, outcomes, contact -> changes)


def lead_status_outcomes(options: list[dict]) -> dict[str, str]:
    """hs_lead_status internal value -> MEETING_BOOKED or LOST, from the property's options."""
    out: dict[str, str] = {}
    for option in options or []:
        value = str(option.get("value") or "").strip()
        for name in (option.get("label"), value):
            outcome = _LEAD_STATUS_OUTCOMES.get(" ".join(str(name or "").replace("_", " ").lower().split()))
            if outcome and value:
                out[value] = outcome
                break
    return out


def lead_status_changes_from_hubspot(post: Callable, contact_ids: list[str], outcomes: dict[str, str]) -> dict[str, list[dict]]:
    """contact_id -> every time its lead status was set to a value in `outcomes`: {outcome, at}."""
    changes: dict[str, list[dict]] = {contact_id: [] for contact_id in contact_ids}
    for start in range(0, len(contact_ids), _LEAD_STATUS_BATCH):
        page = post("/crm/v3/objects/contacts/batch/read", {
            "inputs": [{"id": contact_id} for contact_id in contact_ids[start:start + _LEAD_STATUS_BATCH]],
            "properties": ["hs_lead_status"],
            "propertiesWithHistory": ["hs_lead_status"],
        }) or {}
        for row in page.get("results") or []:
            history = (row.get("propertiesWithHistory") or {}).get("hs_lead_status") or []
            found = changes.setdefault(str(row.get("id")), [])
            for entry in history:
                outcome = outcomes.get(str(entry.get("value") or "").strip())
                at = _instant(entry.get("timestamp"))
                if outcome and at:
                    found.append({"outcome": outcome, "at": at})
    return changes


def credit_status_changes(changes: dict[str, list[dict]], memos: list[dict], outcome: str) -> dict[str, datetime]:
    """memo_id -> when the contact's lead status was set to `outcome`, credited to the last call on
    the contact before it. A meeting must follow its call within CREDIT_WINDOW; a loss closes the
    last interaction however long before it was."""
    by_contact: dict[str, list[tuple[datetime, str]]] = {}
    for memo in memos:
        at = _instant(memo.get("capture_started_at")) or _instant(memo.get("created_at"))
        if at and memo.get("id") and memo.get("hubspot_contact_id"):
            by_contact.setdefault(str(memo["hubspot_contact_id"]), []).append((at, str(memo["id"])))
    credited: dict[str, datetime] = {}
    for contact_id, found in changes.items():
        for change in found:
            if change["outcome"] != outcome:
                continue
            set_at = change["at"]
            candidates = [
                (at, memo_id) for at, memo_id in by_contact.get(contact_id, [])
                if at <= set_at + timedelta(hours=1)
                and (outcome != MEETING_BOOKED or set_at - CREDIT_WINDOW <= at)
            ]
            if candidates:
                credited[max(candidates)[1]] = set_at
    return credited


def _lead_status_changes(supabase: Any, company_id: str, memos: list[dict]) -> dict[str, list[dict]]:
    """The lead status changes of the memos' contacts, cached per company for CACHE_SECONDS."""
    contact_ids = sorted({str(memo["hubspot_contact_id"]) for memo in memos if memo.get("hubspot_contact_id")})
    if not contact_ids:
        return {}
    with _lock:
        hit = _status_cache.get(company_id)
        if hit and time.monotonic() - hit[0] >= CACHE_SECONDS:
            hit = None
    cached_at, outcomes, known = hit if hit else (time.monotonic(), {}, {})
    missing = [contact_id for contact_id in contact_ids if contact_id not in known]
    if missing:
        def read(get: Callable, post: Callable) -> tuple[dict[str, str], dict[str, list[dict]]]:
            found = outcomes or lead_status_outcomes((get("/crm/v3/properties/contacts/hs_lead_status") or {}).get("options") or [])
            return found, (lead_status_changes_from_hubspot(post, missing, found) if found else {cid: [] for cid in missing})

        result = _hubspot_read(supabase, company_id, read)
        if result is None:
            return {}
        outcomes, fetched = result
        known = {**known, **fetched}
        with _lock:
            _status_cache[company_id] = (cached_at, outcomes, known)
    return {contact_id: known.get(contact_id, []) for contact_id in contact_ids}


def lead_status_calls(supabase: Any, company_id: Optional[str], memos: list[dict], outcome: str) -> dict[str, datetime]:
    """The calls whose contact's lead status the rep set to `outcome` (MEETING_BOOKED or LOST)
    afterwards. Empty for another CRM or on any failure. Never raises."""
    if not company_id or not memos:
        return {}
    try:
        return credit_status_changes(_lead_status_changes(supabase, str(company_id), memos), memos, outcome)
    except Exception:
        logger.warning("crm lead status: read failed; coaching keeps the other outcomes", exc_info=True)
        return {}


def apply_crm_meetings(supabase: Any, company_id: Optional[str], memos: list[dict]) -> list[dict]:
    """Memos whose call booked a meeting the rep marked in the CRM (the deal moved to the meeting
    stage, or the contact's lead status set to converted) get rep_outcome "meeting_booked" (an
    outcome the rep already set in Vocify always wins). Never raises."""
    if not company_id or not memos:
        return memos
    credited: dict[str, datetime] = {}
    try:
        stage = meeting_stage(supabase, str(company_id))
        if stage:
            credited.update(credit_calls(_hubspot_deals(supabase, str(company_id), stage["stage_id"]), memos))
    except Exception:
        logger.warning("crm meetings: read failed; coaching keeps the rep's Vocify outcomes only", exc_info=True)
    credited.update(lead_status_calls(supabase, company_id, memos, MEETING_BOOKED))
    if not credited:
        return memos
    return [
        {**memo, "rep_outcome": MEETING_BOOKED} if str(memo.get("id")) in credited and not memo.get("rep_outcome") else memo
        for memo in memos
    ]


# HubSpot's lost stage in the default pipeline. A custom pipeline's own lost stage is not read yet.
HUBSPOT_LOST_STAGE = "closedlost"


def lost_calls(deals: list[dict], memos: list[dict]) -> dict[str, datetime]:
    """memo_id -> when its deal was lost: per lost deal, the last call on the deal or one of its
    contacts before it was lost (however long before: the last interaction is the one to read)."""
    by_key: dict[str, list[tuple[datetime, str]]] = {}
    for memo in memos:
        at = _instant(memo.get("capture_started_at")) or _instant(memo.get("created_at"))
        memo_id = str(memo.get("id") or "")
        if not at or not memo_id:
            continue
        for key in (memo.get("hubspot_contact_id"), memo.get("hubspot_deal_id")):
            if key:
                by_key.setdefault(str(key), []).append((at, memo_id))
    lost: dict[str, datetime] = {}
    for deal in deals:
        entered = deal["entered_at"]
        candidates = [
            (at, memo_id)
            for key in [deal["deal_id"], *deal["contact_ids"]]
            for at, memo_id in by_key.get(key, [])
            if at <= entered + timedelta(hours=1)
        ]
        if candidates:
            lost[max(candidates)[1]] = entered
    return lost


def crm_lost_calls(supabase: Any, company_id: Optional[str], memos: list[dict]) -> dict[str, datetime]:
    """The calls the rep marked lost in HubSpot (read only): the deal in the lost stage, or the
    contact's lead status set to lost / not qualified. Empty for another CRM or on any failure:
    the Head of Sales then sees the losses declared in Vocify only. Never raises."""
    if not company_id or not memos:
        return {}
    lost: dict[str, datetime] = {}
    try:
        lost.update(lost_calls(_hubspot_deals(supabase, str(company_id), HUBSPOT_LOST_STAGE), memos))
    except Exception:
        logger.warning("crm lost deals: read failed; losses come from Vocify outcomes only", exc_info=True)
    lost.update(lead_status_calls(supabase, company_id, memos, LOST))
    return lost


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
