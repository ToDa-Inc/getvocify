"""Hoy confirm_pending signals after CRM auto-approve. One signal per memo."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.services.deal_stage_confirm import (
    FLAG as DEAL_STAGE_FLAG,
    STAGE_FIELD,
    meeting_booked_stage,
    stage_confirm_enabled,
    suggested_stage,
    write_confirmed_stage,
)
from app.services.feature_flags import is_enabled
from app.services.hoy.signals import Signal
from app.services.meetings.accept import accept_meeting_proposal
from app.services.meetings.proposals import latest_proposal
from app.services.rep_timezone import rep_timezone

logger = logging.getLogger(__name__)

CONFIRM_FLAG = "HOY_CONFIRMATIONS_ENABLED"
CONFIRM_TYPE = "confirm_pending"

MONTH = {
    "es": ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"),
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
}
WEEKDAY = {
    "es": ("lun", "mar", "mié", "jue", "vie", "sáb", "dom"),
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
}


@dataclass(frozen=True)
class DealSnapshot:
    provider: str
    pipeline_id: Optional[str] = None
    stage_id: Optional[str] = None


@dataclass(frozen=True)
class PendingConfirm:
    memo_id: str
    contact_id: Optional[str]
    contact_name: Optional[str]
    deal_id: Optional[str]
    connection_id: str
    meeting: Optional[dict[str, Any]]
    stage: Optional[dict[str, Any]]


def confirm_dedupe_key(memo_id: str) -> str:
    return f"confirm:{memo_id}"


def _lang(lang: str) -> str:
    return "en" if (lang or "").lower().startswith("en") else "es"


def _meeting_booked_from_rows(proposal_rows: list[dict], config: Any) -> Optional[dict[str, str]]:
    proposal = latest_proposal(proposal_rows)
    if not proposal or proposal["agreement"] != "agreed" or proposal["decision"] == "omitted":
        return None
    pipeline_id = str(getattr(config, "meeting_booked_pipeline_id", None) or "").strip()
    stage_id = str(getattr(config, "meeting_booked_stage_id", None) or "").strip()
    if not pipeline_id or not stage_id:
        return None
    return {"pipeline_id": pipeline_id, "stage_id": stage_id}


def _meeting_pending(proposal_rows: list[dict]) -> Optional[dict[str, Any]]:
    proposal = latest_proposal(proposal_rows)
    if not proposal:
        return None
    if proposal["agreement"] != "agreed" or proposal["decision"] in {"accepted", "omitted", "corrected"}:
        return None
    if proposal.get("needs_review") or not proposal.get("starts_at"):
        return None
    return {"proposal_id": proposal["proposal_id"]}


def _stage_pending(
    *,
    provider: str,
    pipeline_id: Optional[str],
    current_stage_id: Optional[str],
    meeting_booked: Optional[dict[str, str]],
    inferred: Optional[str],
) -> Optional[dict[str, Any]]:
    if provider not in STAGE_FIELD:
        return None
    stage_ids = [str(x) for x in (current_stage_id, (meeting_booked or {}).get("stage_id")) if x]
    suggested_id = suggested_stage(
        pipeline_id=pipeline_id,
        stage_ids=stage_ids,
        meeting_booked=meeting_booked,
        inferred=inferred,
        fallback=current_stage_id,
    )
    if not suggested_id or str(suggested_id) == str(current_stage_id or ""):
        return None
    label = _stage_label_for(str(suggested_id), meeting_booked=meeting_booked, inferred=inferred)
    return {
        "field": STAGE_FIELD[provider],
        "stage_id": str(suggested_id),
        "stage_label": label,
        "current_stage_id": str(current_stage_id) if current_stage_id else None,
    }


def pending_confirm_parts(
    *,
    memo: dict,
    proposal_rows: list[dict],
    config: Any,
    deal: Optional[DealSnapshot],
    supabase: Any,
    company_id: Optional[str],
) -> Optional[PendingConfirm]:
    """Pure decision: whether a confirm_pending signal applies. No I/O except flags lookup."""
    if not is_enabled(supabase, company_id, CONFIRM_FLAG):
        return None
    meeting = _meeting_pending(proposal_rows)
    stage = None
    provider = (deal.provider if deal else "") or ""
    if deal and stage_confirm_enabled(supabase, company_id, provider):
        extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
        inferred = extraction.get("dealStage")
        if isinstance(inferred, str):
            inferred = inferred.strip() or None
        booked = _meeting_booked_from_rows(proposal_rows, config)
        if booked is None:
            booked = meeting_booked_stage(supabase, memo_id=str(memo.get("id") or ""), config=config)
        stage = _stage_pending(
            provider=provider,
            pipeline_id=deal.pipeline_id,
            current_stage_id=deal.stage_id,
            meeting_booked=booked,
            inferred=inferred,
        )
    if not meeting and not stage:
        return None
    extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
    contact_name = extraction.get("contactName")
    return PendingConfirm(
        memo_id=str(memo.get("id") or ""),
        contact_id=str(memo.get("hubspot_contact_id") or "") or None,
        contact_name=str(contact_name).strip() if contact_name else None,
        deal_id=str(memo.get("hubspot_deal_id") or memo.get("matched_deal_id") or "") or None,
        connection_id=str(memo.get("connection_id") or ""),
        meeting=meeting,
        stage=stage,
    )


def _format_meeting_line(
    starts_at: str,
    contact_name: Optional[str],
    *,
    lang: str,
    tz_name: str,
) -> str:
    lang = _lang(lang)
    parsed = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
    local = parsed.astimezone(ZoneInfo(tz_name or "Europe/Madrid"))
    day = WEEKDAY[lang][local.weekday()]
    month = MONTH[lang][local.month - 1]
    date_part = f"{day} {local.day} {month}"
    time_part = local.strftime("%H:%M")
    who = contact_name or ("them" if lang == "en" else "contacto")
    if lang == "en":
        return f"meeting {day} {local.day} {month}, {time_part} with {who}"
    return f"reunión {date_part}, {time_part} con {who}"


def confirm_copy(
    pending: PendingConfirm,
    proposal_rows: list[dict],
    *,
    lang: str = "es",
    tz_name: str = "Europe/Madrid",
) -> tuple[str, Optional[str]]:
    """reason + detail for GET /today (F16 contract)."""
    lang = _lang(lang)
    parts: list[str] = []
    detail = None
    if pending.meeting:
        row = max(proposal_rows, key=lambda item: str(item.get("created_at") or ""))
        starts_at = row.get("starts_at")
        if isinstance(starts_at, str) and starts_at:
            parts.append(_format_meeting_line(starts_at, pending.contact_name, lang=lang, tz_name=tz_name))
    if pending.stage:
        label = pending.stage.get("stage_label") or pending.stage.get("stage_id") or ""
        detail = f"Etapa → {label}" if lang == "es" else f"Stage → {label}"
    prefix = "Confirma:" if lang == "es" else "Confirm:"
    if parts and detail:
        reason = f"{prefix} {' · '.join(parts)}"
    elif parts:
        reason = f"{prefix} {parts[0]}"
    elif detail:
        reason = f"{prefix} {detail.lower() if lang == 'es' else detail}"
        detail = None
    else:
        reason = prefix
    return reason, detail


def confirm_payload(pending: PendingConfirm, *, reason: str, detail: Optional[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {"reason": reason}
    if detail:
        payload["detail"] = detail
    if pending.contact_name:
        payload["contact_name"] = pending.contact_name
    if pending.meeting:
        payload["meeting"] = dict(pending.meeting)
    if pending.stage:
        payload["stage"] = dict(pending.stage)
    return payload


def build_confirm_signal(
    pending: PendingConfirm,
    proposal_rows: list[dict],
    *,
    lang: str = "es",
    tz_name: str = "Europe/Madrid",
) -> Signal:
    reason, detail = confirm_copy(pending, proposal_rows, lang=lang, tz_name=tz_name)
    payload = confirm_payload(pending, reason=reason, detail=detail)
    return Signal(
        CONFIRM_TYPE,
        contact_id=pending.contact_id,
        deal_id=pending.deal_id,
        source_memo_id=pending.memo_id,
        due_at=None,
        payload=payload,
        dedupe_key=confirm_dedupe_key(pending.memo_id),
        connection_id=pending.connection_id or None,
    )


async def fetch_deal_snapshot(
    supabase,
    *,
    memo: dict,
    company_id: str,
) -> Optional[DealSnapshot]:
    """Best-effort current deal stage for confirm materialization. HubSpot and Pipedrive only."""
    from app.services.crm_providers.resolve import resolve_sync_connection_for_company

    deal_id = memo.get("hubspot_deal_id") or memo.get("matched_deal_id")
    if not deal_id:
        return None
    try:
        connection = resolve_sync_connection_for_company(supabase, company_id)
    except Exception:
        return None
    if not connection:
        return None
    provider = (connection.get("provider") or "").lower()
    if provider == "hubspot":
        from app.services.hubspot.client import HubSpotClient
        from app.services.hubspot.deals import HubSpotDealsService
        from app.services.hubspot.token_refresh import ensure_hubspot_connection_tokens_fresh

        connection = await ensure_hubspot_connection_tokens_fresh(supabase, connection)
        token = (connection.get("access_token") or "").strip()
        if not token:
            return None
        client = HubSpotClient(token)
        deals = HubSpotDealsService(client)
        try:
            deal = await deals.get(str(deal_id), properties=["pipeline", "dealstage"])
        except Exception:
            return None
        props = deal.properties or {}
        return DealSnapshot(provider="hubspot", pipeline_id=props.get("pipeline"), stage_id=props.get("dealstage"))
    if provider == "pipedrive":
        from app.services.pipedrive.client import PipedriveClient

        domain = str((connection.get("metadata") or {}).get("api_domain") or "").rstrip("/")
        token = (connection.get("access_token") or "").strip()
        if not domain or not token:
            return None
        client = PipedriveClient(domain, token)
        try:
            response = await client.get(f"/deals/{deal_id}")
        except Exception:
            return None
        data = (response or {}).get("data") if isinstance(response, dict) else None
        if not isinstance(data, dict):
            return None
        return DealSnapshot(
            provider="pipedrive",
            pipeline_id=str(data.get("pipeline_id")) if data.get("pipeline_id") is not None else None,
            stage_id=str(data.get("stage_id")) if data.get("stage_id") is not None else None,
        )
    return None


def _stage_label_for(
    suggested_id: str,
    *,
    meeting_booked: Optional[dict[str, str]],
    inferred: Optional[str],
) -> str:
    if meeting_booked and str(meeting_booked.get("stage_id")) == str(suggested_id):
        return "Meeting booked"
    return inferred or str(suggested_id)


async def materialize_confirm_after_auto_approve(
    supabase,
    *,
    memo_id: str,
    user_id: str,
    company_id: str,
) -> bool:
    """Insert confirm_pending when stage or meeting still needs the rep. Best-effort."""
    if not is_enabled(supabase, company_id, CONFIRM_FLAG):
        return False
    try:
        memo_rows = (
            supabase.table("memos")
            .select("id,company_id,user_id,hubspot_contact_id,hubspot_deal_id,matched_deal_id,extraction,connection_id")
            .eq("id", memo_id)
            .limit(1)
            .execute()
        )
        memo = (memo_rows.data or [None])[0]
        if not memo or str(memo.get("user_id") or "") != str(user_id):
            return False
        proposals = (
            supabase.table("meeting_proposals").select("*").eq("memo_id", memo_id).execute()
        ).data or []
        deal = await fetch_deal_snapshot(supabase, memo=memo, company_id=company_id)
        from app.services.crm_config import CRMConfigurationService

        config = await CRMConfigurationService(supabase).get_configuration(
            user_id, connection_id=str(memo.get("connection_id") or "")
        )
        pending = pending_confirm_parts(
            memo=memo,
            proposal_rows=proposals,
            config=config,
            deal=deal,
            supabase=supabase,
            company_id=company_id,
        )
        if pending is None:
            return False
        tz_name = rep_timezone(user_id)
        signal = build_confirm_signal(pending, proposals, tz_name=tz_name)
        supabase.table("action_signals").upsert(
            {
                "company_id": company_id,
                "user_id": user_id,
                "connection_id": signal.connection_id or "",
                "contact_id": signal.contact_id,
                "deal_id": signal.deal_id,
                "memo_id": signal.source_memo_id,
                "type": signal.type,
                "dedupe_key": signal.dedupe_key,
                "payload": signal.payload,
                "status": "pending",
                "coverage": "complete",
            },
            on_conflict="company_id,user_id,connection_id,dedupe_key",
        ).execute()
        return True
    except Exception:
        logger.exception("confirm_pending materialize failed", extra={"memo_id": memo_id})
        return False


def mark_confirm_write_pending(payload: dict) -> dict:
    merged = dict(payload or {})
    merged["write_pending"] = True
    return merged


def clear_confirm_write_pending(payload: dict) -> dict:
    merged = dict(payload or {})
    merged.pop("write_pending", None)
    return merged


def confirm_write_due(row: dict, now: datetime) -> bool:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    if not payload.get("write_pending") or payload.get("write_applied"):
        return False
    if row.get("status") != "resolved":
        return False
    deadline = row.get("undo_deadline")
    if not deadline:
        return False
    parsed = datetime.fromisoformat(str(deadline).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        from datetime import timezone

        parsed = parsed.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        from datetime import timezone

        now = now.replace(tzinfo=timezone.utc)
    return now > parsed


async def apply_confirm_writes(
    supabase,
    *,
    row: dict,
    company_id: str,
    user_id: str,
) -> dict:
    """CRM writes for a confirm_pending signal. Idempotent."""
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    if payload.get("write_applied"):
        return {"replayed": True}
    memo_id = row.get("memo_id")
    if not memo_id:
        return {"replayed": False, "error": "missing_memo"}
    if meeting := payload.get("meeting"):
        proposal_id = meeting.get("proposal_id")
        if proposal_id:
            accept_meeting_proposal(
                supabase,
                company_id=company_id,
                memo_id=str(memo_id),
                decision="accept",
                proposal_id=str(proposal_id),
            )
    if stage := payload.get("stage"):
        await write_confirmed_stage(
            supabase,
            memo_id=str(memo_id),
            user_id=user_id,
            company_id=company_id,
            stage_id=str(stage.get("stage_id") or ""),
            stage_label=str(stage.get("stage_label") or ""),
            provider_field=str(stage.get("field") or ""),
        )
    return {"replayed": False}


async def flush_due_confirm_writes(
    supabase,
    *,
    company_id: str,
    user_id: str,
    now: datetime,
) -> int:
    """Apply CRM writes once the F06 undo window has passed."""
    if not is_enabled(supabase, company_id, CONFIRM_FLAG):
        return 0
    try:
        stored = (
            supabase.table("action_signals")
            .select("*")
            .eq("company_id", company_id)
            .eq("user_id", user_id)
            .eq("type", CONFIRM_TYPE)
            .execute()
        )
    except Exception:
        return 0
    written = 0
    for row in stored.data or []:
        if not confirm_write_due(row, now):
            continue
        result = await apply_confirm_writes(supabase, row=row, company_id=company_id, user_id=user_id)
        if result.get("error"):
            continue
        payload = dict(row.get("payload") or {})
        payload["write_applied"] = True
        payload.pop("write_pending", None)
        supabase.table("action_signals").update({"payload": payload}).eq("id", row["id"]).execute()
        written += 1
    return written
