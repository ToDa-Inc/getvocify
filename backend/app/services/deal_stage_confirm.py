"""The rep confirms the deal stage on memo review; Vocify never moves it on its own.

Company flag DEAL_STAGE_CONFIRM_ENABLED (F14 addendum 2026-09-26). Off = previous behaviour.
"""

from __future__ import annotations

from typing import Any, Optional

from app.services.feature_flags import is_enabled
from app.services.meetings.proposals import latest_proposal

FLAG = "DEAL_STAGE_CONFIRM_ENABLED"
STAGE_FIELD = {"hubspot": "dealstage", "pipedrive": "stage_id"}
_DEFAULT_DEAL_FIELDS = {
    "hubspot": ["dealname", "amount", "description", "closedate"],
    "pipedrive": ["title", "value", "currency", "expected_close_date", "stage_id"],
}


def stage_confirm_enabled(supabase: Any, company_id: Optional[str], provider: Optional[str]) -> bool:
    return (provider or "").lower() in STAGE_FIELD and is_enabled(supabase, company_id, FLAG)


def meeting_booked_stage(supabase: Any, *, memo_id: str, config: Any) -> Optional[dict[str, str]]:
    """The configured meeting-booked stage when the memo's latest meeting is agreed and not omitted."""
    pipeline_id = str(getattr(config, "meeting_booked_pipeline_id", None) or "").strip()
    stage_id = str(getattr(config, "meeting_booked_stage_id", None) or "").strip()
    if not pipeline_id or not stage_id:
        return None
    rows = (
        supabase.table("meeting_proposals")
        .select("*")
        .eq("memo_id", str(memo_id))
        .execute()
    ).data or []
    proposal = latest_proposal(rows)
    if not proposal or proposal["agreement"] != "agreed" or proposal["decision"] == "omitted":
        return None
    return {"pipeline_id": pipeline_id, "stage_id": stage_id}


def suggested_stage(
    *,
    pipeline_id: Optional[str],
    stage_ids: list[str],
    meeting_booked: Optional[dict[str, str]],
    inferred: Optional[str],
    fallback: Optional[str],
) -> Optional[str]:
    """Meeting-booked stage (same pipeline only), else the inferred stage, else the fallback."""
    if (
        meeting_booked
        and pipeline_id is not None
        and str(meeting_booked.get("pipeline_id")) == str(pipeline_id)
        and str(meeting_booked.get("stage_id")) in stage_ids
    ):
        return str(meeting_booked["stage_id"])
    for candidate in (inferred, fallback):
        if candidate not in (None, ""):
            return str(candidate)
    return None


def preview_stage_kwargs(supabase: Any, *, memo: dict, connection: dict, config: Any) -> dict[str, Any]:
    provider = (connection.get("provider") or "").lower()
    company_id = memo.get("company_id") or connection.get("company_id")
    if not stage_confirm_enabled(supabase, company_id, provider):
        return {}
    return {
        "stage_confirm": True,
        "meeting_booked_stage": meeting_booked_stage(supabase, memo_id=str(memo.get("id")), config=config),
    }


def sync_allowed_fields(allowed_fields: Optional[list[str]], *, provider: str, reviewed: bool) -> list[str]:
    """A reviewed approval lets the confirmed stage through; an unattended one never moves it."""
    field = STAGE_FIELD[provider]
    base = list(allowed_fields) if allowed_fields is not None else list(_DEFAULT_DEAL_FIELDS[provider])
    if not reviewed:
        return [f for f in base if f != field]
    return base if field in base else [*base, field]
