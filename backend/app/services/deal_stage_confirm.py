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


async def write_confirmed_stage(
    supabase: Any,
    *,
    memo_id: str,
    user_id: str,
    company_id: str,
    stage_id: str,
    stage_label: str,
    provider_field: str,
) -> None:
    """Write the rep-confirmed stage only (Hoy confirm or review). Idempotent when unchanged."""
    from app.models.memo import MemoExtraction
    from app.services.crm_config import CRMConfigurationService
    from app.services.crm_providers import AmbiguousPrimaryCRMError, build_crm_provider, resolve_sync_connection
    from app.services.hubspot.deal_field_names import normalize_hubspot_allowed_deal_fields
    from app.services.hubspot.token_refresh import ensure_hubspot_connection_tokens_fresh
    from app.services.memo_approval import CRMSyncError

    if not stage_id:
        return
    try:
        crm_connection = resolve_sync_connection(supabase, user_id)
    except AmbiguousPrimaryCRMError as exc:
        raise ValueError(str(exc)) from exc
    if not crm_connection:
        return
    provider = (crm_connection.get("provider") or "").lower()
    if provider_field and STAGE_FIELD.get(provider) != provider_field:
        return
    if provider not in STAGE_FIELD:
        return

    memo_rows = supabase.table("memos").select("*").eq("id", memo_id).limit(1).execute()
    memo_data = (memo_rows.data or [None])[0]
    if not memo_data:
        return

    if provider == "hubspot":
        crm_connection = await ensure_hubspot_connection_tokens_fresh(supabase, crm_connection)

    extraction_data = dict(memo_data.get("extraction") or {})
    if provider == "pipedrive":
        raw = dict(extraction_data.get("raw_extraction") or {})
        raw["stage_id"] = stage_id
        extraction_data["raw_extraction"] = raw
    else:
        extraction_data["dealStage"] = stage_label or stage_id
    extraction = MemoExtraction(**extraction_data)

    config = await CRMConfigurationService(supabase).get_configuration(
        user_id, connection_id=str(crm_connection["id"])
    )
    field = STAGE_FIELD[provider]
    allowed_fields = [field]
    if provider == "hubspot":
        allowed_fields = normalize_hubspot_allowed_deal_fields(allowed_fields)

    deal_id = memo_data.get("hubspot_deal_id") or memo_data.get("matched_deal_id")
    if not deal_id:
        return

    provider_client = build_crm_provider(supabase, crm_connection)
    sync_result = await provider_client.sync_memo(
        memo_id=memo_id,
        user_id=user_id,
        connection_id=str(crm_connection["id"]),
        extraction=extraction,
        deal_id=str(deal_id),
        is_new_deal=False,
        allowed_fields=allowed_fields,
        skip_deal=False,
        create_note=False,
        stage_confirm=True,
    )
    if not sync_result.success:
        raise CRMSyncError(sync_result.error or "Stage confirm failed", error_code=sync_result.error_code)


def sync_allowed_fields(allowed_fields: Optional[list[str]], *, provider: str, reviewed: bool) -> list[str]:
    """A reviewed approval lets the confirmed stage through; an unattended one never moves it."""
    field = STAGE_FIELD[provider]
    base = list(allowed_fields) if allowed_fields is not None else list(_DEFAULT_DEAL_FIELDS[provider])
    if not reviewed:
        return [f for f in base if f != field]
    return base if field in base else [*base, field]
