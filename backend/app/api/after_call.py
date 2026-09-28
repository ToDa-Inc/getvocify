"""Lista 4 T4 (E10, E11): the after-call step in Hoy's contact panel. Behind AFTER_CALL_FLOW_ENABLED.

GET  /memos/{id}/after-call  what the panel prefills: suggested follow-up date and why, whether
                             an email was promised, the company's deal rule, the lead statuses.
POST /memos/{id}/outcome     the outcome for a memo that is already approved (auto-approve got
                             there first). POST /memos/{id}/approve takes the same outcome
                             fields for a memo still waiting for review.

record_outcome is the part both share: store memos.rep_outcome/followup_at, hand a booked
meeting to the AE (HANDOFF_ENABLED) and close the contact's Hoy cards when the rep closes it
out. The decisions themselves are pure, in services/after_call.py.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.api.handoffs import CRM_OWNER_FLAG, _apply_crm_owner_effect
from app.deps import get_membership, get_supabase
from app.models.memo import MemoExtraction, RecordOutcomeRequest
from app.services import after_call
from app.services.company import CompanyService, Membership
from app.services.crm_config import CRMConfigurationService
from app.services.crm_providers import AmbiguousPrimaryCRMError, build_crm_provider, resolve_sync_connection
from app.services.feature_flags import is_enabled
from app.services.handoffs import (
    HandoffError,
    ae_membership_row,
    create_handoff,
    resolve_ae,
    resolve_owner_for_general,
    valid_ae,
)
from app.services.hoy.actions import ActionError, apply_action
from app.services.hoy.confirmations import CONFIRM_TYPE

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/memos", tags=["after-call"])

FLAG = "AFTER_CALL_FLOW_ENABLED"
HANDOFF_FLAG = "HANDOFF_ENABLED"
# Hoy cards still asking for the rep's attention. A confirm card is a CRM write waiting for
# its OK, not a reason to call - closing the contact out does not answer it.
_OPEN_SIGNAL_STATUSES = ("pending", "snoozed")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def enabled(supabase: Client, company_id: Optional[str]) -> bool:
    return is_enabled(supabase, company_id, FLAG)


def _owned_memo(supabase: Client, memo_id: str, membership: Membership) -> dict:
    """The rep's own memo. Another company's (or an unknown id) is 404; a teammate's is 403 -
    the outcome is what the caller did on the call, nobody records it for them."""
    rows = supabase.table("memos").select("*").eq("id", str(memo_id)).limit(1).execute().data or []
    memo = rows[0] if rows else None
    if not memo or str(memo.get("company_id") or "") != str(membership.company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memo not found")
    if str(memo.get("user_id") or "") != str(membership.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo quien hizo la llamada registra su resultado")
    return memo


def _intelligence(memo: dict) -> dict:
    extraction = memo.get("extraction") or {}
    intelligence = extraction.get("intelligence") if isinstance(extraction, dict) else None
    return intelligence if isinstance(intelligence, dict) else {}


def _memo_deal_id(memo: dict) -> Optional[str]:
    return memo.get("hubspot_deal_id") or memo.get("matched_deal_id") or None


def _meeting_starts_at(memo: dict) -> Optional[str]:
    meeting = _intelligence(memo).get("meeting") or {}
    return meeting.get("starts_at") if meeting.get("agreed") is True else None


def _membership_or_none(supabase: Client, user_id: str) -> Optional[Membership]:
    try:
        return CompanyService(supabase).require_membership(user_id)
    except Exception:
        return None


def followup_date(memo: dict, rep_outcome: str, followup_at: Optional[datetime], overrides: dict, now: datetime) -> Optional[datetime]:
    """Only a follow-up has a date: the rep's, else the cadence's suggestion (E8)."""
    if rep_outcome != after_call.FOLLOW_UP:
        return None
    if followup_at is not None:
        return followup_at if followup_at.tzinfo else followup_at.replace(tzinfo=timezone.utc)
    return after_call.suggested_followup_at(memo, overrides, now)


def _store_outcome(supabase: Client, memo_id: str, rep_outcome: str, due: Optional[datetime]) -> bool:
    """memos.rep_outcome/followup_at (migration 062). A database without the columns logs and
    carries on - the CRM write already happened and must not turn into an error."""
    try:
        supabase.table("memos").update({
            "rep_outcome": rep_outcome,
            "followup_at": due.isoformat() if due else None,
        }).eq("id", str(memo_id)).execute()
        return True
    except Exception:
        logger.warning("after-call outcome not stored for memo %s (migration 062?)", memo_id, exc_info=True)
        return False


def _handoff(
    supabase: Client,
    *,
    membership: Membership,
    memo: dict,
    contact_id: Optional[str],
    deal_id: Optional[str],
) -> Optional[dict]:
    """A booked meeting from an SDR (or a General with a route) goes to the AE, same as the
    panel's "Reunión agendada" (POST /handoffs) - idempotent per contact. Never fails the
    outcome: a missing AE comes back as a hint so the panel can open the AE picker."""
    if membership.sales_role == "ae" or not is_enabled(supabase, membership.company_id, HANDOFF_FLAG):
        return None
    if not contact_id:
        return {"status": "no_contact"}
    try:
        connection = resolve_sync_connection(supabase, membership.user_id)
    except AmbiguousPrimaryCRMError:
        connection = None
    if not connection:
        return {"status": "no_connection"}
    try:
        if membership.sales_role == "sdr":
            ae_user_id = resolve_ae(membership, supabase=supabase, company_id=membership.company_id)
        else:
            ae_user_id = resolve_owner_for_general(membership)
            if not ae_user_id or str(ae_user_id) == str(membership.user_id):
                return {"status": "self_owned"}
        if not valid_ae(ae_membership_row(supabase, company_id=membership.company_id, ae_user_id=ae_user_id)):
            return {"status": "invalid_ae"}
        connection_id = str(connection["id"])
        row = create_handoff(
            supabase,
            company_id=membership.company_id,
            connection_id=connection_id,
            contact_id=str(contact_id),
            sdr_user_id=membership.user_id,
            ae_user_id=ae_user_id,
            deal_id=str(deal_id) if deal_id else None,
            source_memo_id=str(memo.get("id")),
            meeting_starts_at=_meeting_starts_at(memo),
        )
    except HandoffError as exc:
        return {"status": exc.code}
    except Exception:
        logger.warning("after-call handoff failed for memo %s", memo.get("id"), exc_info=True)
        return {"status": "failed"}
    if row.get("skipped"):
        return {"status": "skipped"}
    if row.get("created") and is_enabled(supabase, membership.company_id, CRM_OWNER_FLAG):
        try:
            _apply_crm_owner_effect(
                supabase,
                company_id=membership.company_id,
                connection_id=connection_id,
                handoff_id=row.get("id"),
                ae_user_id=ae_user_id,
                deal_id=str(deal_id) if deal_id else None,
                contact_id=str(contact_id),
            )
        except Exception:
            logger.warning("after-call handoff CRM owner effect failed for memo %s", memo.get("id"), exc_info=True)
    return {
        "status": "created" if row.get("created") else "exists",
        "id": row.get("id"),
        "ae_user_id": ae_user_id,
    }


def resolve_contact_signals(
    supabase: Client,
    *,
    membership: Membership,
    contact_id: Optional[str],
    memo_id: str,
    reason: str,
    now: datetime,
) -> int:
    """The rep closed the contact out: its open Hoy cards are resolved the way "Descalificar"
    resolves one (hoy/actions.apply_action), with the outcome kept as the reason. The request
    id is per memo and card, so a retried outcome replays instead of bumping versions again."""
    if not contact_id:
        return 0
    rows = (
        supabase.table("action_signals")
        .select("*")
        .eq("company_id", membership.company_id)
        .eq("user_id", membership.user_id)
        .eq("contact_id", str(contact_id))
        .in_("status", list(_OPEN_SIGNAL_STATUSES))
        .execute()
    ).data or []
    resolved = 0
    for row in rows:
        if row.get("type") == CONFIRM_TYPE:
            continue
        try:
            result = apply_action(
                row,
                action="disqualify",
                request_id=f"after-call:{memo_id}:{row.get('id')}",
                expected_version=row.get("version"),
                until=None,
                now=now,
                user_id=membership.user_id,
                company_id=membership.company_id,
            )
        except ActionError:
            continue
        if result["replayed"]:
            continue
        saved = (
            supabase.table("action_signals")
            .update({
                "status": result["status"],
                "version": result["version"],
                "previous_status": result["previous_status"],
                "last_action_request_id": result["last_action_request_id"],
                "last_action_at": result["last_action_at"],
                "undo_deadline": result["undo_deadline"],
                "snoozed_until": None,
                "payload": {**dict(row.get("payload") or {}), "resolution_reason": reason},
            })
            .eq("id", row["id"])
            .eq("company_id", membership.company_id)
            .eq("user_id", membership.user_id)
            .eq("version", row["version"])
            .execute()
        )
        resolved += 1 if (saved.data or []) else 0
    return resolved


def record_outcome(
    supabase: Client,
    *,
    memo: dict,
    membership: Optional[Membership],
    rep_outcome: str,
    followup_at: Optional[datetime],
    contact_id: Optional[str] = None,
    deal_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> dict:
    """Everything the outcome does in Vocify itself, once the CRM accepted the call. Returns
    the hint the panel shows (stored date, handoff status, cards closed)."""
    now = now or _now()
    company_id = memo.get("company_id") or (membership.company_id if membership else None)
    overrides = CompanyService(supabase).followup_cadence(str(company_id)) if company_id else {}
    due = followup_date(memo, rep_outcome, followup_at, overrides, now)
    contact_id = contact_id or memo.get("hubspot_contact_id")
    deal_id = deal_id or _memo_deal_id(memo)
    hint: dict[str, Any] = {
        "rep_outcome": rep_outcome,
        "followup_at": due.isoformat() if due else None,
        "stored": _store_outcome(supabase, str(memo["id"]), rep_outcome, due),
        "handoff": None,
        "signals_resolved": 0,
    }
    if membership is None:
        return hint
    if rep_outcome == after_call.MEETING_BOOKED:
        hint["handoff"] = _handoff(supabase, membership=membership, memo=memo, contact_id=contact_id, deal_id=deal_id)
    elif rep_outcome in after_call.REASON_REQUIRED:
        try:
            hint["signals_resolved"] = resolve_contact_signals(
                supabase, membership=membership, contact_id=contact_id, memo_id=str(memo["id"]),
                reason=rep_outcome, now=now,
            )
        except Exception:
            logger.warning("after-call signals not resolved for memo %s", memo.get("id"), exc_info=True)
    return hint


def record_outcome_for_user(supabase: Client, *, memo: dict, user_id: str, **kwargs) -> dict:
    """record_outcome for callers that only know the user (POST /memos/{id}/approve)."""
    return record_outcome(supabase, memo=memo, membership=_membership_or_none(supabase, user_id), **kwargs)


async def _write_crm_outcome(
    supabase: Client,
    *,
    memo: dict,
    user_id: str,
    body: RecordOutcomeRequest,
) -> dict:
    """The call outcome in the CRM for an already-approved memo: HubSpot's call_outcome writer
    (contact lead status, deal mirror, Lost note, On hold task). Pipedrive/Salesforce have no
    call outcome writer, so there the outcome lives in Vocify only - said, not hidden."""
    try:
        connection = resolve_sync_connection(supabase, user_id)
    except AmbiguousPrimaryCRMError:
        connection = None
    if not connection:
        return {"status": "no_crm"}
    provider_name = (connection.get("provider") or "").lower()
    if provider_name != "hubspot":
        return {"status": "unsupported", "provider": provider_name}
    config = await CRMConfigurationService(supabase).get_configuration(user_id, connection_id=str(connection["id"]))
    plan = after_call.approval_plan(
        rep_outcome=body.rep_outcome,
        reason=body.disqualify_reason,
        lead_status=body.lead_status,
        provider=provider_name,
        rule=None,
        has_deal=True,
        config=config,
    )
    extraction_raw = memo.get("extraction") or {}
    try:
        extraction = MemoExtraction(**extraction_raw) if extraction_raw else None
    except Exception:
        extraction = None
    try:
        crm = build_crm_provider(supabase, connection)
        result = await crm.record_call_outcome(
            memo_id=str(memo["id"]),
            user_id=user_id,
            call_outcome=plan["call_outcome"],
            lost_reason=plan["lost_reason"],
            lost_reason_deal_property=(getattr(config, "lost_reason_deal_property", None) or None) if config else None,
            lost_lead_status_value=plan.get(
                "lost_lead_status_value", (getattr(config, "lost_lead_status_value", None) or None) if config else None
            ),
            on_hold_lead_status_value=plan.get(
                "on_hold_lead_status_value", (getattr(config, "on_hold_lead_status_value", None) or None) if config else None
            ),
            contact_id=memo.get("hubspot_contact_id"),
            deal_id=_memo_deal_id(memo),
            company_id=None,
            contact_name=(extraction_raw.get("contactName") if isinstance(extraction_raw, dict) else None),
            extraction=extraction,
        )
    except Exception:
        logger.warning("after-call CRM outcome failed for memo %s", memo.get("id"), exc_info=True)
        return {"status": "failed", "failed": "Couldn't record the call outcome in HubSpot."}
    if result.failed:
        return {"status": "failed", "failed": result.failed, "warning": result.warning}
    return {"status": "written", "warning": result.warning}


async def apply_outcome_to_approved(supabase: Client, *, memo: dict, membership: Optional[Membership], user_id: str, body: RecordOutcomeRequest) -> dict:
    """POST /outcome's work, shared with an approve that arrives after auto-approve."""
    crm = await _write_crm_outcome(supabase, memo=memo, user_id=user_id, body=body)
    hint = record_outcome(
        supabase, memo=memo, membership=membership, rep_outcome=body.rep_outcome, followup_at=body.followup_at,
    )
    hint["crm"] = crm
    # E11 after the fact: an auto-approved memo was synced without a deal. Creating one now
    # would mean a second full sync of an approved memo, so it is not done here - the hint
    # says the rule would have allowed one and the panel points at the memo instead.
    if not _memo_deal_id(memo):
        config = await CRMConfigurationService(supabase).get_configuration(user_id)
        rule = getattr(config, "deal_creation_rule", None) if config else None
        if after_call.normalize_rule(rule) != after_call.DEAL_RULE_ALWAYS and after_call.deal_allowed(rule, body.rep_outcome):
            hint["deal"] = {"status": "not_created_after_approval"}
    return hint


@router.get("/{memo_id}/after-call")
async def get_after_call(
    memo_id: UUID,
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
):
    if not enabled(supabase, membership.company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    memo = _owned_memo(supabase, str(memo_id), membership)
    now = _now()
    overrides = CompanyService(supabase).followup_cadence(membership.company_id)
    config = await CRMConfigurationService(supabase).get_configuration(membership.user_id)
    try:
        connection = resolve_sync_connection(supabase, membership.user_id)
    except AmbiguousPrimaryCRMError:
        connection = None
    provider_name = (connection.get("provider") or "").lower() if connection else None
    stopper = after_call.memo_stopper(memo, now)
    # Lead status is HubSpot's call outcome writer; elsewhere the panel shows none.
    lead_status_writable = provider_name == "hubspot"
    return {
        "memo_status": memo.get("status"),
        "provider": provider_name,
        "suggested_followup_at": after_call.suggested_followup_at(memo, overrides, now).isoformat(),
        "stopper": stopper,
        "promised_email": after_call.promised_email(_intelligence(memo)),
        "deal_creation_rule": after_call.normalize_rule(getattr(config, "deal_creation_rule", None) if config else None),
        # Salesforce always needs an opportunity: its sync ignores the rule.
        "deal_rule_applies": provider_name in {"hubspot", "pipedrive"},
        "has_deal": bool(_memo_deal_id(memo)),
        "lead_status_options": after_call.lead_status_options(config) if lead_status_writable else None,
        "proposed_lead_status": (
            {outcome: after_call.proposed_lead_status(outcome, stopper, config) for outcome in after_call.REP_OUTCOMES}
            if lead_status_writable else None
        ),
        "lost_reasons": list(getattr(config, "lost_reasons", None) or []) if config else [],
        "rep_outcome": memo.get("rep_outcome"),
        "followup_at": memo.get("followup_at"),
    }


@router.post("/{memo_id}/outcome")
async def post_outcome(
    memo_id: UUID,
    body: RecordOutcomeRequest,
    membership: Membership = Depends(get_membership),
    supabase: Client = Depends(get_supabase),
):
    if not enabled(supabase, membership.company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    memo = _owned_memo(supabase, str(memo_id), membership)
    if memo.get("status") != "approved":
        # Not synced yet: the outcome goes with the approval (POST /approve), in one write.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "not_approved"})
    return {"after_call": await apply_outcome_to_approved(
        supabase, memo=memo, membership=membership, user_id=membership.user_id, body=body,
    )}
