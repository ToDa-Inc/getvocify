"""Load meeting grounding for /copilot/suggest from a capture the user owns."""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from supabase import Client

from app.services.copilot.context import SuggestContext, live_assist_kind_from_call_mode
from app.services.copilot.grounding import SuggestGrounding, resolve_suggest_grounding
from app.services.playbooks.live import live_snapshots
from app.services.playbooks.versions import published_snapshot


def load_company_suggest_grounding(
    supabase: Client,
    *,
    company_id: str,
    call_mode: str = "speakerphone",
    context: Optional[SuggestContext] = None,
) -> Optional[SuggestGrounding]:
    del context  # contact_id stays on SuggestContext only; no CRM load
    snapshots = live_snapshots(supabase, company_id)
    if len(snapshots) != 1:
        return None
    snapshot = snapshots[0]
    kind = live_assist_kind_from_call_mode(call_mode)
    return SuggestGrounding(
        interaction_kind=kind,
        playbook_version_id=snapshot["version_id"],
        evidence_ids=frozenset(),
        playbook_snapshot=snapshot,
    )


def load_owned_capture_memo(
    supabase: Client,
    *,
    user_id: str,
    company_id: str,
    capture_id: str,
) -> dict:
    result = (
        supabase.table("memos")
        .select("id,user_id,company_id,interaction_kind,playbook_version_id,sales_motion_key,extraction")
        .eq("id", capture_id)
        .limit(1)
        .execute()
    )
    rows = list(getattr(result, "data", None) or [])
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capture not found")
    row = rows[0]
    if str(row.get("user_id") or "") != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capture not found")
    row_company = str(row.get("company_id") or "").strip()
    if row_company and row_company != company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capture not found")
    return row


def suggest_grounding_from_memo_row(
    supabase: Client,
    *,
    company_id: str,
    row: dict,
) -> Optional[SuggestGrounding]:
    motion = str(row.get("sales_motion_key") or "").strip() or None
    playbook = None
    versions: list[dict] = []
    version_id = str(row.get("playbook_version_id") or "").strip() or None
    if motion and version_id:
        pb_result = (
            supabase.table("playbooks")
            .select("id,company_id,sales_motion_key")
            .eq("company_id", company_id)
            .eq("sales_motion_key", motion)
            .limit(1)
            .execute()
        )
        pb_rows = list(getattr(pb_result, "data", None) or [])
        if pb_rows:
            playbook = pb_rows[0]
            ver_result = (
                supabase.table("playbook_versions")
                .select("id,status,steps,entries")
                .eq("playbook_id", playbook["id"])
                .execute()
            )
            versions = list(getattr(ver_result, "data", None) or [])

    grounding = resolve_suggest_grounding(row, playbook=playbook, versions=versions)
    if grounding and grounding.playbook_version_id and playbook and versions:
        snapshot = published_snapshot(playbook, versions, grounding.playbook_version_id)
        if snapshot is None:
            return SuggestGrounding(
                interaction_kind=grounding.interaction_kind,
                playbook_version_id=None,
                evidence_ids=grounding.evidence_ids,
                playbook_snapshot=None,
            )
        return SuggestGrounding(
            interaction_kind=grounding.interaction_kind,
            playbook_version_id=snapshot["version_id"],
            evidence_ids=grounding.evidence_ids,
            playbook_snapshot=snapshot,
        )
    return grounding


def load_suggest_grounding(
    supabase: Client,
    *,
    user_id: str,
    company_id: str,
    capture_id: str,
    context: Optional[SuggestContext] = None,
) -> Optional[SuggestGrounding]:
    del context  # reserved for capture-scoped CRM context; contact_id stays on SuggestContext only
    row = load_owned_capture_memo(
        supabase,
        user_id=user_id,
        company_id=company_id,
        capture_id=capture_id,
    )
    return suggest_grounding_from_memo_row(supabase, company_id=company_id, row=row)


def load_company_knowledge(supabase: Client, *, company_id: str) -> Optional[dict]:
    """The company's own sales knowledge («Vuestra empresa»: value, differentiators, customer
    proofs, competitors) for the live copilot's prompt. None when the company has none, the
    table is not there yet or the read fails: the copilot then works exactly as before."""
    try:
        result = (
            supabase.table("company_sales_knowledge")
            .select("data")
            .eq("company_id", company_id)
            .limit(1)
            .execute()
        )
        rows = list(getattr(result, "data", None) or [])
    except Exception:
        return None
    data = (rows[0] if rows else {}).get("data")
    return data if isinstance(data, dict) and data else None
