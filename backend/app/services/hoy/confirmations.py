"""Hoy confirm_pending signals after CRM auto-approve, and their deferred CRM write. One signal per memo.

The write waits for the F06 undo window. It runs from a task scheduled at confirm time and
from a periodic sweep (restarts, lost tasks, retries); both go through run_confirm_write,
which claims the row with a version-conditional update so a write happens at most once.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.logging_config import log_domain
from app.services.deal_stage_confirm import STAGE_FIELD, stage_confirm_enabled, suggested_stage
from app.services.feature_flags import is_enabled
from app.services.hoy.confirm_copy import confirm_reason, failed_detail
from app.services.hoy.signals import Signal
from app.services.meetings.accept import accept_meeting_proposal
from app.services.meetings.proposals import latest_proposal
from app.services.memo_approval import write_confirmed_stage
from app.services.rep_timezone import rep_timezone

logger = logging.getLogger(__name__)

CONFIRM_FLAG = "HOY_CONFIRMATIONS_ENABLED"
CONFIRM_TYPE = "confirm_pending"
DOMAIN_HOY = "hoy"
MAX_WRITE_ATTEMPTS = 3
CLAIM_LEASE = timedelta(minutes=10)
SWEEP_INTERVAL_SECONDS = 60
_AFTER_DEADLINE_SECONDS = 0.5
_WRITE_STATE = ("write_pending", "write_claimed_at", "write_attempts", "write_error", "write_failed", "write_applied")


@dataclass(frozen=True)
class DealSnapshot:
    provider: str
    pipeline_id: Optional[str] = None
    stage_id: Optional[str] = None
    stage_labels: dict[str, str] = field(default_factory=dict)


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


def _meeting_booked(proposal: Optional[dict], config: Any) -> Optional[dict[str, str]]:
    if not proposal or proposal["agreement"] != "agreed" or proposal["decision"] == "omitted":
        return None
    pipeline_id = str(getattr(config, "meeting_booked_pipeline_id", None) or "").strip()
    stage_id = str(getattr(config, "meeting_booked_stage_id", None) or "").strip()
    if not pipeline_id or not stage_id:
        return None
    return {"pipeline_id": pipeline_id, "stage_id": stage_id}


def _meeting_pending(proposal: Optional[dict]) -> Optional[dict[str, Any]]:
    if not proposal:
        return None
    if proposal["agreement"] != "agreed" or proposal["decision"] in {"accepted", "omitted", "corrected"}:
        return None
    if proposal.get("needs_review") or not proposal.get("starts_at"):
        return None
    return {"proposal_id": proposal["proposal_id"], "starts_at": proposal["starts_at"]}


def _stage_pending(
    *,
    deal: DealSnapshot,
    meeting_booked: Optional[dict[str, str]],
    inferred: Optional[str],
) -> Optional[dict[str, Any]]:
    if deal.provider not in STAGE_FIELD:
        return None
    current = deal.stage_id
    stage_ids = [str(x) for x in (current, (meeting_booked or {}).get("stage_id")) if x]
    suggested_id = suggested_stage(
        pipeline_id=deal.pipeline_id,
        stage_ids=stage_ids,
        meeting_booked=meeting_booked,
        inferred=inferred,
        fallback=current,
    )
    if not suggested_id or str(suggested_id) == str(current or ""):
        return None
    return {
        "field": STAGE_FIELD[deal.provider],
        "stage_id": str(suggested_id),
        "stage_label": deal.stage_labels.get(str(suggested_id)) or str(suggested_id),
        "current_stage_id": str(current) if current else None,
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
    """Whether a confirm_pending signal applies. Reads only company flags."""
    if not is_enabled(supabase, company_id, CONFIRM_FLAG):
        return None
    proposal = latest_proposal(proposal_rows)
    meeting = _meeting_pending(proposal)
    stage = None
    extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
    if deal and stage_confirm_enabled(supabase, company_id, deal.provider):
        inferred = extraction.get("dealStage")
        inferred = inferred.strip() or None if isinstance(inferred, str) else None
        stage = _stage_pending(deal=deal, meeting_booked=_meeting_booked(proposal, config), inferred=inferred)
    if not meeting and not stage:
        return None
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


def confirm_payload(pending: PendingConfirm, *, lang: str = "es", tz_name: str = "Europe/Madrid") -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if pending.contact_name:
        payload["contact_name"] = pending.contact_name
    if pending.meeting:
        payload["meeting"] = dict(pending.meeting)
    if pending.stage:
        payload["stage"] = dict(pending.stage)
    payload["reason"] = confirm_reason(payload, lang=lang, tz_name=tz_name)
    return payload


def build_confirm_signal(pending: PendingConfirm, *, lang: str = "es", tz_name: str = "Europe/Madrid") -> Signal:
    return Signal(
        CONFIRM_TYPE,
        contact_id=pending.contact_id,
        deal_id=pending.deal_id,
        source_memo_id=pending.memo_id,
        due_at=None,
        payload=confirm_payload(pending, lang=lang, tz_name=tz_name),
        dedupe_key=confirm_dedupe_key(pending.memo_id),
        connection_id=pending.connection_id or None,
    )


async def fetch_deal_snapshot(supabase, *, memo: dict, company_id: str) -> Optional[DealSnapshot]:
    """Current deal stage and stage names. HubSpot only: auto-approve exists only for HubSpot calls."""
    from app.services.crm_providers.resolve import resolve_sync_connection_for_company

    deal_id = memo.get("hubspot_deal_id") or memo.get("matched_deal_id")
    if not deal_id:
        return None
    try:
        connection = resolve_sync_connection_for_company(supabase, company_id)
    except Exception:
        logger.exception("confirm_pending: CRM connection lookup failed",
                         extra=log_domain(DOMAIN_HOY, "confirm_deal_snapshot_failed", memo_id=memo.get("id")))
        return None
    if not connection or (connection.get("provider") or "").lower() != "hubspot":
        return None
    from app.services.hubspot.client import HubSpotClient
    from app.services.hubspot.deals import HubSpotDealsService
    from app.services.hubspot.schema import HubSpotSchemaService
    from app.services.hubspot.search import HubSpotSearchService
    from app.services.hubspot.token_refresh import ensure_hubspot_connection_tokens_fresh

    try:
        connection = await ensure_hubspot_connection_tokens_fresh(supabase, connection)
        client = HubSpotClient((connection.get("access_token") or "").strip())
        schema = HubSpotSchemaService(client, supabase, str(connection.get("id") or ""))
        deals = HubSpotDealsService(client, HubSpotSearchService(client), schema)
        deal = await deals.get(str(deal_id), properties=["pipeline", "dealstage"])
        props = deal.properties or {}
        pipeline_id = props.get("pipeline")
        labels: dict[str, str] = {}
        for pipeline in (await schema.get_deal_schema()).pipelines:
            if pipeline_id and pipeline.id != pipeline_id:
                continue
            labels.update({stage.id: stage.label for stage in pipeline.stages if stage.label})
    except Exception:
        logger.exception("confirm_pending: deal snapshot failed",
                         extra=log_domain(DOMAIN_HOY, "confirm_deal_snapshot_failed", memo_id=memo.get("id")))
        return None
    return DealSnapshot(provider="hubspot", pipeline_id=pipeline_id, stage_id=props.get("dealstage"), stage_labels=labels)


def _existing_signal(supabase, *, company_id: str, user_id: str, dedupe_key: str) -> Optional[dict]:
    rows = (
        supabase.table("action_signals")
        .select("*")
        .eq("company_id", company_id)
        .eq("user_id", user_id)
        .eq("dedupe_key", dedupe_key)
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


async def materialize_confirm_after_auto_approve(
    supabase,
    *,
    memo_id: str,
    user_id: str,
    company_id: str,
) -> bool:
    """Insert confirm_pending when stage or meeting still needs the rep. Best-effort.

    A signal the rep already acted on is never reopened by a later auto-approve.
    """
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
        existing = _existing_signal(
            supabase, company_id=company_id, user_id=user_id, dedupe_key=confirm_dedupe_key(memo_id),
        )
        if existing and existing.get("status") != "pending":
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
        signal = build_confirm_signal(pending, tz_name=rep_timezone(user_id))
        if existing:
            kept = {k: v for k, v in (existing.get("payload") or {}).items() if k in _WRITE_STATE}
            supabase.table("action_signals").update({"payload": {**signal.payload, **kept}}).eq(
                "id", existing["id"]
            ).eq("status", "pending").execute()
            return True
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
        logger.exception("confirm_pending materialize failed",
                         extra=log_domain(DOMAIN_HOY, "confirm_materialize_failed", memo_id=memo_id))
        return False


def mark_confirm_write_pending(payload: dict) -> dict:
    merged = {k: v for k, v in (payload or {}).items() if k not in _WRITE_STATE and k != "detail"}
    merged["write_pending"] = True
    return merged


def clear_confirm_write_pending(payload: dict) -> dict:
    merged = dict(payload or {})
    merged.pop("write_pending", None)
    return merged


def _parse(value) -> Optional[datetime]:
    if not value:
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def confirm_write_due(row: dict, now: datetime) -> bool:
    """Confirmed, undo window over, not written, not given up, and nobody holds a live claim."""
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    if not payload.get("write_pending") or payload.get("write_applied") or payload.get("write_failed"):
        return False
    if row.get("type") != CONFIRM_TYPE or row.get("status") != "resolved":
        return False
    deadline = _parse(row.get("undo_deadline"))
    now = _parse(now)
    if deadline is None or now <= deadline:
        return False
    claimed = _parse(payload.get("write_claimed_at"))
    return claimed is None or now - claimed > CLAIM_LEASE


def _conditional_update(supabase, row: dict, changes: dict) -> Optional[dict]:
    saved = (
        supabase.table("action_signals")
        .update({**changes, "version": int(row.get("version") or 0) + 1})
        .eq("id", row["id"])
        .eq("version", row.get("version"))
        .execute()
    )
    rows = saved.data or []
    return rows[0] if rows else None


def claim_confirm_write(supabase, row: dict, now: datetime) -> Optional[dict]:
    """Take the write. Conditional on the version, so an undo or another worker wins or loses whole."""
    payload = dict(row.get("payload") or {})
    payload["write_claimed_at"] = _parse(now).isoformat()
    payload["write_attempts"] = int(payload.get("write_attempts") or 0) + 1
    return _conditional_update(supabase, row, {"payload": payload})


async def apply_confirm_writes(supabase, *, row: dict, company_id: str, user_id: str) -> None:
    """The same CRM writes the review does: meeting via accept, stage via the review's stage write."""
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    memo_id = str(row.get("memo_id") or "")
    if not memo_id:
        raise ValueError("confirm_pending without memo_id")
    meeting = payload.get("meeting") if isinstance(payload.get("meeting"), dict) else None
    if meeting and meeting.get("proposal_id"):
        await asyncio.to_thread(
            accept_meeting_proposal,
            supabase,
            company_id=company_id,
            memo_id=memo_id,
            decision="accept",
            proposal_id=str(meeting["proposal_id"]),
        )
    stage = payload.get("stage") if isinstance(payload.get("stage"), dict) else None
    if stage and stage.get("stage_id"):
        await write_confirmed_stage(
            supabase,
            memo_id=memo_id,
            user_id=user_id,
            company_id=company_id,
            stage_id=str(stage["stage_id"]),
        )


def _record_failure(supabase, claimed: dict, error: Exception) -> str:
    payload = dict(claimed.get("payload") or {})
    payload.pop("write_claimed_at", None)
    payload["write_error"] = str(error)[:300]
    if int(payload.get("write_attempts") or 0) < MAX_WRITE_ATTEMPTS:
        _conditional_update(supabase, claimed, {"payload": payload})
        return "retry"
    payload.pop("write_pending", None)
    payload["write_failed"] = True
    payload["detail"] = failed_detail("es")
    _conditional_update(supabase, claimed, {
        "payload": payload,
        "status": "pending",
        "previous_status": claimed.get("status"),
        "undo_deadline": None,
    })
    return "failed"


async def run_confirm_write(supabase, signal_id: str, *, now: Optional[datetime] = None) -> str:
    """skipped | lost | applied | retry | failed | error. Never raises."""
    phase = "load"
    try:
        now = now or datetime.now(timezone.utc)
        rows = supabase.table("action_signals").select("*").eq("id", signal_id).limit(1).execute().data or []
        row = rows[0] if rows else None
        if not row or not confirm_write_due(row, now):
            return "skipped"
        if not is_enabled(supabase, row.get("company_id"), CONFIRM_FLAG):
            return "skipped"
        phase = "claim"
        claimed = claim_confirm_write(supabase, row, now)
        if claimed is None:
            return "lost"
        phase = "write"
        try:
            await apply_confirm_writes(
                supabase, row=claimed, company_id=str(claimed["company_id"]), user_id=str(claimed["user_id"]),
            )
        except Exception as error:
            logger.exception(
                "Hoy confirm CRM write failed",
                extra=log_domain(
                    DOMAIN_HOY, "confirm_write_failed", signal_id=signal_id,
                    attempt=(claimed.get("payload") or {}).get("write_attempts"),
                ),
            )
            phase = "record_failure"
            return _record_failure(supabase, claimed, error)
        phase = "record_success"
        payload = {k: v for k, v in (claimed.get("payload") or {}).items()
                   if k not in ("write_pending", "write_claimed_at", "write_error")}
        payload["write_applied"] = True
        _conditional_update(supabase, claimed, {"payload": payload})
        return "applied"
    except Exception:
        logger.exception("Hoy confirm write crashed",
                         extra=log_domain(DOMAIN_HOY, f"confirm_write_{phase}_error", signal_id=signal_id))
        return "error"


_SCHEDULED: set[asyncio.Task] = set()


def schedule_confirm_write(supabase, signal_id: str, undo_deadline) -> Optional[asyncio.Task]:
    """Run the write just after the undo window. The sweep covers restarts and lost tasks."""
    deadline = _parse(undo_deadline)
    if deadline is None:
        return None

    async def _later() -> str:
        delay = (deadline - datetime.now(timezone.utc)).total_seconds() + _AFTER_DEADLINE_SECONDS
        await asyncio.sleep(max(delay, 0))
        return await run_confirm_write(supabase, signal_id)

    task = asyncio.get_running_loop().create_task(_later())
    _SCHEDULED.add(task)
    task.add_done_callback(_SCHEDULED.discard)
    return task


async def sweep_confirm_writes(supabase, *, now: Optional[datetime] = None) -> int:
    """Every due confirm write across companies. Returns how many were applied."""
    now = now or datetime.now(timezone.utc)
    try:
        rows = (
            supabase.table("action_signals")
            .select("*")
            .eq("type", CONFIRM_TYPE)
            .eq("status", "resolved")
            .eq("payload->>write_pending", "true")
            .execute()
        ).data or []
    except Exception:
        logger.exception("Hoy confirm sweep read failed", extra=log_domain(DOMAIN_HOY, "confirm_sweep_failed"))
        return 0
    applied = 0
    for row in rows:
        if row.get("id") and confirm_write_due(row, now):
            if await run_confirm_write(supabase, str(row["id"]), now=now) == "applied":
                applied += 1
    return applied
