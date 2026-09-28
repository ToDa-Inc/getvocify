"""T6: the AE's "deals en curso" section - active handoffs plus the AE's own deals that
carry a memo, minus whichever have already reached an end stage. Pure merge/filter here;
the CRM stage read and the lazy `close_handoff` effect are kept in the caller (api/today.py)
so this stays unit-testable without a client."""

from __future__ import annotations

from typing import Optional

from app.services.handoffs import stage_ends_deal

DEAL_TYPE = "deal_in_progress"

_REASON = {
    "es": {"handoff": "Traspasado a ti", "own": "Deal en curso"},
    "en": {"handoff": "Handed off to you", "own": "Deal in progress"},
}


def own_deal_candidates(memos: list[dict]) -> list[dict]:
    """One candidate per deal id the AE's own memos name, from the newest memo about it.
    A memo with no deal id contributes nothing here. memos carries no CRM connection
    column (same fact api/briefs.py's `_read_memos` notes), so connection_id is always
    None here - the company's single connected CRM is resolved elsewhere."""
    by_deal: dict[str, dict] = {}
    for memo in sorted(memos, key=lambda row: str(row.get("created_at") or "")):
        deal_id = memo.get("hubspot_deal_id")
        if not deal_id:
            continue
        by_deal[str(deal_id)] = {
            "deal_id": str(deal_id),
            "contact_id": str(memo.get("hubspot_contact_id") or "") or None,
            "connection_id": None,
            "memo_id": memo.get("id"),
            "created_at": memo.get("created_at"),
        }
    return list(by_deal.values())


def merge_deal_candidates(handoffs: list[dict], own: list[dict]) -> list[dict]:
    """Handoffs first (they carry the SDR), then the AE's own deals - a deal already
    covered by a handoff is not repeated as "own" even if the AE also captured a memo on
    it after taking over. Each candidate keeps its own created_at so a caller can sort by
    recency (T6 review: newest_first) before spending any CRM read on it."""
    by_key: dict[str, dict] = {}
    order: list[str] = []
    for row in handoffs:
        deal_id = row.get("deal_id")
        contact_id = row.get("contact_id")
        key = f"deal:{deal_id}" if deal_id else f"contact:{contact_id}"
        by_key[key] = {
            "deal_id": str(deal_id) if deal_id else None,
            "contact_id": str(contact_id) if contact_id else None,
            "connection_id": str(row.get("connection_id") or "") or None,
            "source": "handoff",
            "sdr_user_id": row.get("sdr_user_id"),
            "created_at": row.get("created_at"),
            "handoff_id": str(row.get("id")) if row.get("id") else None,
            "meeting_starts_at": row.get("meeting_starts_at"),
        }
        order.append(key)
    for row in own:
        deal_id = row.get("deal_id")
        key = f"deal:{deal_id}" if deal_id else f"contact:{row.get('contact_id')}"
        if key in by_key:
            continue
        by_key[key] = {**row, "source": "own"}
        order.append(key)
    return [by_key[key] for key in dict.fromkeys(order)]


def newest_first(candidates: list[dict], *, limit: int) -> list[dict]:
    """T6 review: sort by created_at descending (missing sorts last) and cap at `limit` -
    this MUST run before any CRM stage read, so a company with many deals never spends a
    read (or a HubSpot batch slot) on one that would be folded away anyway."""
    ordered = sorted(candidates, key=lambda row: str(row.get("created_at") or ""), reverse=True)
    return ordered[:limit]


def deal_reason(source: str, *, lang: str = "es") -> str:
    table = _REASON.get(lang) or _REASON["es"]
    return table.get(source, table["own"])


HUBSPOT_BATCH_LIMIT = 100


def deal_stages_by_provider(fetch, provider: str, deal_ids: list[str]) -> dict[str, dict]:
    """deal_id -> {"stage_id" | "status": ...}. Best-effort: a failed or empty read yields
    {} for the deals it could not verify, and a caller never excludes (or closes a handoff
    for) a deal it could not read - unknown stays open. Synchronous and possibly slow (one
    HTTP round trip per HubSpot batch of HUBSPOT_BATCH_LIMIT, or one per Pipedrive deal) -
    the caller (api/today.py) runs this in a threadpool under a total deadline."""
    ids = [str(deal_id) for deal_id in deal_ids if deal_id]
    if not ids:
        return {}
    name = str(provider or "").strip().lower()
    if name == "hubspot":
        stages: dict[str, dict] = {}
        for start in range(0, len(ids), HUBSPOT_BATCH_LIMIT):
            batch = ids[start:start + HUBSPOT_BATCH_LIMIT]
            try:
                payload = fetch({
                    "path": "/crm/v3/objects/deals/batch/read",
                    "json": {"properties": ["dealstage"], "inputs": [{"id": deal_id} for deal_id in batch]},
                }) or {}
            except (TimeoutError, OSError, ValueError):
                continue
            if not isinstance(payload, dict) or payload.get("error_kind"):
                continue
            for row in payload.get("results") or []:
                if row.get("id"):
                    stages[str(row["id"])] = {"stage_id": (row.get("properties") or {}).get("dealstage")}
        return stages
    if name == "pipedrive":
        out: dict[str, dict] = {}
        for deal_id in ids:
            try:
                payload = fetch({"path": f"/deals/{deal_id}", "params": {}}) or {}
            except (TimeoutError, OSError, ValueError):
                continue
            if not isinstance(payload, dict) or payload.get("error_kind"):
                continue
            data = payload.get("data") or {}
            if data:
                out[deal_id] = {"status": data.get("status")}
        return out
    return {}


def stage_known_ended(stages: dict[str, dict], deal_id: Optional[str], *, provider: str) -> bool:
    """True only when the stage was actually read and it is an end stage - a deal this
    company's CRM was never asked about (no connection, read failed, no deal id) stays in
    the section rather than being guessed closed.

    "End stage" here is exactly `handoffs.stage_ends_deal`'s definition: HubSpot's two
    well-known ids (closedwon/closedlost) or, when the caller already has it, the
    pipeline's own isClosed metadata; Pipedrive's won/lost status. It does NOT read a
    per-company configurable end-stage list from crm_configurations - there isn't one
    today. If this company's pipeline uses custom stage ids for "won"/"lost" instead of
    HubSpot's defaults, those deals are never detected as ended here."""
    if not deal_id:
        return False
    stage = stages.get(str(deal_id))
    if not stage:
        return False
    return bool(stage_ends_deal(provider, stage_id=stage.get("stage_id"), status=stage.get("status")))
