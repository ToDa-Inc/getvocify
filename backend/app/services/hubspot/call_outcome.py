"""
Call outcome: Converted / On Hold / Lost.

The rep marks the result of a call on the confirmation screen (optional -
None means they didn't mark one, unchanged legacy behavior). This is stored
primarily on the CONTACT (hs_lead_status + vocify_lost_reason), and mirrored
to the deal only when one exists:

  converted  -> contact hs_lead_status='OPEN_DEAL' (a real HubSpot default
               option - no provisioning needed); deal (if any) dealstage ->
               its pipeline's "appointmentscheduled" stage.
  on_hold    -> contact hs_lead_status='VOCIFY_FOLLOW_UP' + a follow-up task
               on the deal (or contact, if no deal). Deliberately does NOT
               touch dealstage even when a deal exists: guessing which stage
               of an arbitrary customer's pipeline means "on hold" is exactly
               the kind of heuristic that breaks on portals we've never seen
               - see find_closed_lost_stage_id below for why "lost" gets to
               use a real signal (isClosed+probability) instead.
  lost       -> contact hs_lead_status='VOCIFY_LOST' + vocify_lost_reason;
               deal (if any) dealstage -> its pipeline's closed-lost stage
               (found via metadata, see find_closed_lost_stage_id) + the
               portal's own lost-reason property (see
               resolve_lost_reason_property), when either can be found.

VOCIFY_LOST / VOCIFY_FOLLOW_UP are custom hs_lead_status options, and
vocify_lost_reason is a custom contact property - neither is a HubSpot
default, so every portal needs them created once. This is SELF-PROVISIONED
(see ensure_call_outcome_capability below), not a manual setup step someone
has to remember: the first time a preview is built for a portal missing
them, sync tries to create them right then, idempotently. If that succeeds
(the common case - it only needs crm.schemas.contacts.write, requested at
connect time), the buttons just work with zero admin action. If it fails
(most likely: an existing connection authorized before this app requested
that scope, so the stored OAuth token doesn't have it), the extension does
NOT show the Converted/On Hold/Lost buttons for that account at all - never
"offer it and fail after", per the explicit design decision here. See
ensure_call_outcome_capability for the caching/backoff around this check,
and scripts/provision_outcome_properties.py (now optional/dev-only - kept
for testing against a Private App token in a sandbox portal, not part of
the production rollout anymore).

IMPORTANT - allowlist bypass, on purpose: every write in this module ignores
allowed_contact_fields / allowed_deal_fields. This is the one intentional
exception in the whole sync pipeline. Everywhere else, allowed_*_fields
exists to keep the LLM's own (sometimes wrong) inferences from overwriting
fields a client didn't opt into. Call outcome is never an LLM inference -
it's the rep explicitly clicking "Lost" and typing a reason on the
confirmation screen, a deliberate action with the same standing as a rep
editing a field by hand in HubSpot directly. Silently dropping that because
hs_lead_status isn't in some allowlist would be worse than surprising - it
would make an explicit action disappear with no error. To keep this
invisible-by-design choice from becoming an invisible-in-practice surprise
for a client who deliberately restricts fields, it's also called out next to
the allowlist editors in the HubSpot Configuration screen (see
HubSpotConfiguration.tsx).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, NamedTuple, Optional

from supabase import Client

from app.logging_config import log_domain, DOMAIN_HUBSPOT
from app.services.crm_updates import CRMUpdatesService

from .client import HubSpotClient
from .contacts import HubSpotContactService
from .deals import HubSpotDealService
from .exceptions import HubSpotError, HubSpotNotFoundError, HubSpotScopeError
from .schema import HubSpotSchemaService
from .tasks import HubSpotTasksService, _next_step_schedule_hints, _parse_date_from_text
from .types import CallOutcomeCapability, HubSpotPipeline, HubSpotProperty
from app.models.memo import MemoExtraction

logger = logging.getLogger(__name__)

CallOutcome = Literal["converted", "on_hold", "lost"]

HS_LEAD_STATUS_CONVERTED = "OPEN_DEAL"
HS_LEAD_STATUS_ON_HOLD = "VOCIFY_FOLLOW_UP"
HS_LEAD_STATUS_LOST = "VOCIFY_LOST"

CONTACT_LOST_REASON_PROPERTY = "vocify_lost_reason"
HS_LEAD_STATUS_PROPERTY = "hs_lead_status"

ACTION_TYPE = "update_call_outcome"
FOLLOWUP_TASK_ACTION_TYPE = "create_followup_task"


class CallOutcomeWriteResult(NamedTuple):
    """Split so callers (sync.py) can tell a cosmetic degradation from a
    real data-loss failure - see SyncResult.outcome_warning/outcome_failed
    in hubspot/types.py for what each becomes on the wire."""

    warning: Optional[str] = None
    failed: Optional[str] = None


# ============================================================================
# SELF-PROVISIONING (see module docstring for why this replaces a manual step)
# ============================================================================

CALL_OUTCOME_PROVISIONING_KEY = "call_outcome_provisioning"
# Once a portal is confirmed missing the scope, don't retry on every single
# preview - HubSpot's answer won't change until the customer reconnects.
_PROVISION_RECHECK_BACKOFF = timedelta(hours=6)

# Must match backend/scripts/provision_outcome_properties.py's
# NEW_LEAD_STATUS_OPTIONS (that script imports these constants instead of
# redefining them, to keep the two in sync).
REQUIRED_LEAD_STATUS_OPTIONS: list[dict[str, str]] = [
    {"label": "Lost (Vocify)", "value": HS_LEAD_STATUS_LOST},
    {"label": "Follow-up (Vocify)", "value": HS_LEAD_STATUS_ON_HOLD},
]


async def _fetch_raw_property(
    client: HubSpotClient, object_type: str, name: str
) -> Optional[dict[str, Any]]:
    """Raw (untyped) property fetch - deliberately NOT via HubSpotSchemaService:
    that returns HubSpotProperty/PropertyOption models which don't round-trip
    fields like displayOrder, and this needs to PATCH back a faithful merge
    of the portal's existing options, not a lossy reconstruction."""
    try:
        return await client.get(f"/crm/v3/properties/{object_type}/{name}")
    except HubSpotNotFoundError:
        return None


async def provision_call_outcome_properties(client: HubSpotClient) -> None:
    """
    Idempotently create the two things apply_call_outcome writes to that
    aren't HubSpot defaults. Safe to call every time - only PATCHes/POSTs
    what's actually missing. Raises on any HubSpot API failure (most
    commonly HubSpotScopeError when the token lacks
    crm.schemas.contacts.write); callers decide what that means.
    """
    lead_status = await _fetch_raw_property(client, "contacts", HS_LEAD_STATUS_PROPERTY)
    if lead_status is None:
        raise HubSpotError(
            f"Contact property '{HS_LEAD_STATUS_PROPERTY}' not found on this portal - "
            "this is a HubSpot default that should always exist."
        )

    existing_options = lead_status.get("options") or []
    existing_values = {opt.get("value") for opt in existing_options}
    missing = [opt for opt in REQUIRED_LEAD_STATUS_OPTIONS if opt["value"] not in existing_values]
    if missing:
        next_order = max((opt.get("displayOrder", -1) for opt in existing_options), default=-1) + 1
        merged_options = list(existing_options) + [
            {**opt, "displayOrder": next_order + i, "hidden": False} for i, opt in enumerate(missing)
        ]
        await client.patch(
            f"/crm/v3/properties/contacts/{HS_LEAD_STATUS_PROPERTY}",
            {"options": merged_options},
        )

    lost_reason_prop = await _fetch_raw_property(client, "contacts", CONTACT_LOST_REASON_PROPERTY)
    if lost_reason_prop is None:
        await client.post(
            "/crm/v3/properties/contacts",
            {
                "groupName": "contactinformation",
                "name": CONTACT_LOST_REASON_PROPERTY,
                "label": "Lost reason (Vocify)",
                "description": (
                    "Why this contact was marked Lost from a Vocify call. Written by "
                    "the extension's call-outcome step, not editable by allowlists."
                ),
                "type": "string",
                "fieldType": "text",
            },
        )


def _persist_provisioning_status(
    supabase: Client,
    connection_id: Any,
    metadata: dict[str, Any],
    *,
    provisioned: bool,
    error: Optional[str],
    checked_at_iso: str,
) -> None:
    """Best-effort cache write to crm_connections.metadata (no schema change
    needed - metadata is already a JSONB column used for portal_id/region/
    etc.). If this write itself fails, the next preview just re-attempts
    provisioning - safe, since provisioning is idempotent."""
    metadata = dict(metadata)
    metadata[CALL_OUTCOME_PROVISIONING_KEY] = {
        "provisioned_at": checked_at_iso if provisioned else None,
        "checked_at": checked_at_iso,
        "error": error,
    }
    try:
        supabase.table("crm_connections").update({"metadata": metadata}).eq(
            "id", str(connection_id)
        ).execute()
    except Exception as e:
        logger.warning(
            "⚠️ Failed to persist call outcome provisioning status: %s",
            e,
            extra=log_domain(
                DOMAIN_HUBSPOT, "call_outcome_provision_status_write_failed",
                connection_id=str(connection_id), error=str(e),
            ),
        )


async def ensure_call_outcome_capability(
    *,
    supabase: Client,
    connection: dict[str, Any],
    client: HubSpotClient,
) -> CallOutcomeCapability:
    """
    Capability gate for the Converted/On Hold/Lost buttons - called once per
    preview (see app/api/memos.py). This IS the "no manual step" fix:

    - Already provisioned (crm_connections.metadata, set the first time this
      succeeds for this portal) -> available, zero HubSpot API calls.
    - Not yet provisioned -> try right now, idempotently
      (provision_call_outcome_properties). Success is permanent - HubSpot
      doesn't remove properties on its own - so this never runs again for a
      portal that succeeds once.
    - Failure (most commonly: connected before this app requested
      crm.schemas.contacts.write, so the stored token lacks it) -> stays
      unavailable, rechecked at most once per _PROVISION_RECHECK_BACKOFF so
      a permanently-missing scope doesn't turn into a HubSpot API call on
      every single preview. The extension simply doesn't show the buttons
      for this account (see popup.js initCallOutcome) - never "offer them
      and fail after clicking Lost".
    """
    metadata = dict(connection.get("metadata") or {})
    status_data = dict(metadata.get(CALL_OUTCOME_PROVISIONING_KEY) or {})

    if status_data.get("provisioned_at"):
        return CallOutcomeCapability(available=True)

    checked_at_raw = status_data.get("checked_at")
    if checked_at_raw:
        try:
            checked_at = datetime.fromisoformat(checked_at_raw)
            if checked_at.tzinfo is None:
                checked_at = checked_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - checked_at < _PROVISION_RECHECK_BACKOFF:
                return CallOutcomeCapability(available=False, reason=status_data.get("error"))
        except ValueError:
            pass  # Corrupt cache entry - fall through and re-check now.

    now_iso = datetime.now(timezone.utc).isoformat()
    connection_id = connection.get("id")
    try:
        await provision_call_outcome_properties(client)
    except HubSpotScopeError as e:
        reason = (
            "This HubSpot account needs to be reconnected to enable Call outcome "
            "tracking (Vocify now needs permission to add a couple of status "
            "options to contacts)."
        )
        logger.warning(
            "⚠️ Call outcome provisioning failed: missing scope: %s",
            e,
            extra=log_domain(
                DOMAIN_HUBSPOT, "call_outcome_provision_scope_missing",
                connection_id=str(connection_id), error=str(e),
            ),
        )
        _persist_provisioning_status(
            supabase, connection_id, metadata, provisioned=False, error=reason, checked_at_iso=now_iso
        )
        return CallOutcomeCapability(available=False, reason=reason)
    except Exception as e:
        reason = "Couldn't verify HubSpot is ready for Call outcome tracking yet - retrying automatically."
        logger.warning(
            "⚠️ Call outcome provisioning failed: %s",
            e,
            extra=log_domain(
                DOMAIN_HUBSPOT, "call_outcome_provision_failed",
                connection_id=str(connection_id), error=str(e),
            ),
        )
        _persist_provisioning_status(
            supabase, connection_id, metadata, provisioned=False, error=reason, checked_at_iso=now_iso
        )
        return CallOutcomeCapability(available=False, reason=reason)

    logger.info(
        "✅ Call outcome properties provisioned",
        extra=log_domain(DOMAIN_HUBSPOT, "call_outcome_provisioned", connection_id=str(connection_id)),
    )
    _persist_provisioning_status(
        supabase, connection_id, metadata, provisioned=True, error=None, checked_at_iso=now_iso
    )
    return CallOutcomeCapability(available=True)

# HubSpot's own default name (confirmed against HubSpot's default deal
# properties) tried first, exact match. The label keywords below are a
# fallback for portals where it was renamed, deleted and rebuilt as a custom
# property, or never existed as the default at all - bilingual (EN/ES)
# since this codebase serves both.
_DEFAULT_LOST_REASON_PROPERTY_NAME = "closed_lost_reason"
_LOST_REASON_LABEL_KEYWORD_PAIRS = (
    ("lost", "reason"),
    ("perdid", "motivo"),
    ("perdid", "razon"),
    ("perdid", "razón"),
)


def find_closed_lost_stage_id(pipeline: HubSpotPipeline) -> Optional[str]:
    """
    Find this pipeline's closed-lost stage from HubSpot's own stage metadata
    (isClosed=true AND probability=0) - never a label or hardcoded stage id,
    so it works regardless of language or custom stage naming. Returns None
    when the pipeline has no such stage (a real, common case - not every
    account configures one); callers must treat that as "can't move stage
    for this deal", not raise an error.
    """
    for stage in pipeline.stages:
        meta = stage.metadata or {}
        is_closed = str(meta.get("isClosed", "")).strip().lower() == "true"
        probability = meta.get("probability")
        try:
            is_zero_probability = probability is not None and float(probability) == 0.0
        except (TypeError, ValueError):
            is_zero_probability = False
        if is_closed and is_zero_probability:
            return stage.id
    return None


async def resolve_lost_reason_property(
    schema_service: HubSpotSchemaService,
    configured_property: Optional[str],
) -> Optional[HubSpotProperty]:
    """
    Resolve which deal property holds this portal's "closed lost reason".

    Order:
    1. crm_configurations.lost_reason_deal_property, if set AND still
       present in the portal's CURRENT deal schema - a client may have
       deleted/renamed it since configuring; a stale name must not be sent.
    2. Auto-detect every time sync runs (not only from the configuration
       screen): HubSpot's own default name if present.
    3. Auto-detect: any deal property whose label matches known lost+reason
       keyword pairs.

    Returns None (not a guess) when nothing matches - the caller must skip
    writing the property rather than invent one.
    """
    try:
        schema = await schema_service.get_deal_schema()
    except Exception as e:
        logger.warning(
            "Lost reason property resolution: schema fetch failed: %s",
            e,
            extra=log_domain(DOMAIN_HUBSPOT, "lost_reason_property_schema_failed", error=str(e)),
        )
        return None

    by_name = {p.name: p for p in schema.properties}

    if configured_property and configured_property in by_name:
        return by_name[configured_property]

    if _DEFAULT_LOST_REASON_PROPERTY_NAME in by_name:
        return by_name[_DEFAULT_LOST_REASON_PROPERTY_NAME]

    for prop in schema.properties:
        label = (prop.label or "").lower()
        for kw_a, kw_b in _LOST_REASON_LABEL_KEYWORD_PAIRS:
            if kw_a in label and kw_b in label:
                return prop
    return None


def _reason_matches_option(prop: HubSpotProperty, reason: str) -> bool:
    reason_norm = reason.strip().lower()
    for opt in prop.options:
        if opt.value.strip().lower() == reason_norm or opt.label.strip().lower() == reason_norm:
            return True
    return False


@dataclass
class CallOutcomeContext:
    """Everything apply_call_outcome needs, gathered by the caller (sync.py)
    from things it already has in scope - kept as one object so the
    function signature doesn't grow a dozen positional params."""

    memo_id: str
    user_id: str
    connection_id: str
    call_outcome: CallOutcome
    lost_reason: Optional[str]
    lost_reason_deal_property_configured: Optional[str]
    contact_id: Optional[str]
    deal_id: Optional[str]
    contact_name: Optional[str]
    hubspot_owner_id: Optional[str]
    previous_updates: list[dict[str, Any]] = field(default_factory=list)
    extraction: Optional[MemoExtraction] = None


async def apply_call_outcome(
    ctx: CallOutcomeContext,
    *,
    crm_updates: CRMUpdatesService,
    contacts: HubSpotContactService,
    deals: HubSpotDealService,
    tasks: HubSpotTasksService,
    schema_service: HubSpotSchemaService,
) -> CallOutcomeWriteResult:
    """
    Write the call outcome to HubSpot. Returns a CallOutcomeWriteResult
    distinguishing two severities (see SyncResult.outcome_warning/
    outcome_failed in hubspot/types.py for how each surfaces to the rep):

    - .failed: the core write (contact hs_lead_status + vocify_lost_reason -
      the source of truth per the module docstring) did NOT land anywhere.
      This must not be presented as success.
    - .warning: the core write succeeded, but a secondary MIRROR onto the
      deal (dealstage, the portal's lost-reason property) or the On Hold
      follow-up task didn't - the outcome IS saved on the contact, this is
      just a non-blocking heads-up.

    Every HubSpot write below is independently try/excepted: a failure here
    logs, is folded into the returned result, and never propagates - it
    must not abort or revert anything sync.py already wrote in earlier
    steps (Steps 1-7).
    """
    warning: Optional[str] = None
    failed: Optional[str] = None

    if not ctx.contact_id:
        # Contact-first design: the contact is the source of truth for
        # outcome. No resolved contact means there is nowhere safe to write
        # it - never fall back to the company, per the design decision.
        # Nothing was saved anywhere -> critical, not a minor warning.
        logger.warning(
            "Call outcome skipped: no contact resolved",
            extra=log_domain(DOMAIN_HUBSPOT, "call_outcome_no_contact", memo_id=ctx.memo_id),
        )
        return CallOutcomeWriteResult(
            failed="No contact was resolved for this call, so the outcome wasn't recorded in HubSpot."
        )

    outcome_already_done = CRMUpdatesService.is_action_already_done(
        ctx.previous_updates, (ACTION_TYPE,)
    )
    if not outcome_already_done:
        # --- Contact write (always - the source of truth) ---
        contact_props: dict[str, Any] = {}
        if ctx.call_outcome == "lost":
            contact_props["hs_lead_status"] = HS_LEAD_STATUS_LOST
            contact_props[CONTACT_LOST_REASON_PROPERTY] = ctx.lost_reason or ""
        elif ctx.call_outcome == "on_hold":
            contact_props["hs_lead_status"] = HS_LEAD_STATUS_ON_HOLD
        elif ctx.call_outcome == "converted":
            contact_props["hs_lead_status"] = HS_LEAD_STATUS_CONVERTED

        try:
            async with crm_updates.track(
                memo_id=ctx.memo_id,
                user_id=ctx.user_id,
                crm_connection_id=ctx.connection_id,
                action_type=ACTION_TYPE,
                resource_type="contact",
            ) as tracked:
                await contacts.update(ctx.contact_id, contact_props)
                tracked.data = {
                    "contact_id": ctx.contact_id,
                    "call_outcome": ctx.call_outcome,
                    "properties": contact_props,
                }
                tracked.resource_id = ctx.contact_id
                logger.info(
                    "✅ Call outcome written to contact",
                    extra=log_domain(
                        DOMAIN_HUBSPOT, "call_outcome_contact_updated",
                        contact_id=ctx.contact_id, call_outcome=ctx.call_outcome, memo_id=ctx.memo_id,
                    ),
                )
        except Exception as e:
            # Critical: the source of truth didn't get written. Still worth
            # attempting the deal mirror below (something usable might land
            # on the deal even if the contact write failed), but this is
            # reported as .failed regardless of what the mirror does.
            failed = (
                f"Couldn't save the {ctx.call_outcome} outcome"
                + (" or Lost reason" if ctx.call_outcome == "lost" else "")
                + " to the contact in HubSpot."
            )
            logger.warning(
                "⚠️ Call outcome contact update failed: %s",
                e,
                extra=log_domain(
                    DOMAIN_HUBSPOT, "call_outcome_contact_failed",
                    memo_id=ctx.memo_id, contact_id=ctx.contact_id, error=str(e),
                ),
            )

        # --- Deal mirror (only when a deal exists) ---
        if ctx.deal_id:
            deal_warning = await _apply_deal_mirror(
                ctx, crm_updates=crm_updates, deals=deals, schema_service=schema_service
            )
            if deal_warning:
                warning = f"{warning} {deal_warning}".strip() if warning else deal_warning
    else:
        logger.info(
            "Skipping duplicate call outcome write for memo retry",
            extra=log_domain(DOMAIN_HUBSPOT, "call_outcome_skipped_duplicate", memo_id=ctx.memo_id),
        )

    # --- Follow-up task for On Hold (independent of the above - its own dedupe) ---
    if ctx.call_outcome == "on_hold":
        followup_warning = await _create_followup_task(
            ctx, crm_updates=crm_updates, tasks=tasks
        )
        if followup_warning:
            warning = f"{warning} {followup_warning}".strip() if warning else followup_warning

    return CallOutcomeWriteResult(warning=warning, failed=failed)


async def _create_followup_task(
    ctx: CallOutcomeContext,
    *,
    crm_updates: CRMUpdatesService,
    tasks: HubSpotTasksService,
) -> Optional[str]:
    followup_already_done = CRMUpdatesService.is_action_already_done(
        ctx.previous_updates, (FOLLOWUP_TASK_ACTION_TYPE,)
    )
    if followup_already_done:
        logger.info(
            "Skipping duplicate follow-up task for memo retry",
            extra=log_domain(DOMAIN_HUBSPOT, "followup_task_skipped_duplicate", memo_id=ctx.memo_id),
        )
        return None

    # Reuse the same LLM-extracted schedule hints next-step tasks already
    # rely on (more reliable than re-parsing the raw transcript) - falls
    # back to a fixed +3 days when the memo had no schedule hint at all,
    # same default _parse_date_from_text uses for a next-step task.
    hints = _next_step_schedule_hints(ctx.extraction) if ctx.extraction else []
    due_date = _parse_date_from_text(hints[0]) if hints else None
    if due_date is None:
        due_date = datetime.now(timezone.utc) + timedelta(days=3)

    subject = f"Follow-up with {ctx.contact_name}" if ctx.contact_name else "Follow-up"

    try:
        async with crm_updates.track(
            memo_id=ctx.memo_id,
            user_id=ctx.user_id,
            crm_connection_id=ctx.connection_id,
            action_type=FOLLOWUP_TASK_ACTION_TYPE,
            resource_type="task",
        ) as tracked:
            task_id = await tasks.create_task(
                subject=subject,
                due_date=due_date,
                deal_id=ctx.deal_id,
                contact_id=None if ctx.deal_id else ctx.contact_id,
                body="Marked On Hold from a Vocify call - follow up before this date.",
                hubspot_owner_id=ctx.hubspot_owner_id,
            )
            if not task_id:
                raise RuntimeError("HubSpot task creation returned no id")
            tracked.data = {
                "task_id": task_id,
                "deal_id": ctx.deal_id,
                "contact_id": ctx.contact_id,
                "due_date": due_date.isoformat(),
            }
            tracked.resource_id = task_id
            logger.info(
                "✅ On Hold follow-up task created",
                extra=log_domain(
                    DOMAIN_HUBSPOT, "followup_task_created",
                    task_id=task_id, deal_id=ctx.deal_id, contact_id=ctx.contact_id, memo_id=ctx.memo_id,
                ),
            )
    except Exception as e:
        logger.warning(
            "⚠️ On Hold follow-up task creation failed: %s",
            e,
            extra=log_domain(DOMAIN_HUBSPOT, "followup_task_failed", memo_id=ctx.memo_id, error=str(e)),
        )
        return "Couldn't create the follow-up task in HubSpot."
    return None


async def _apply_deal_mirror(
    ctx: CallOutcomeContext,
    *,
    crm_updates: CRMUpdatesService,
    deals: HubSpotDealService,
    schema_service: HubSpotSchemaService,
) -> Optional[str]:
    warning: Optional[str] = None
    deal_props: dict[str, Any] = {}

    try:
        deal = await deals.get(ctx.deal_id, properties=["pipeline"])
        pipeline_id = (deal.properties or {}).get("pipeline")
    except Exception as e:
        logger.warning(
            "⚠️ Call outcome: could not fetch deal's pipeline: %s",
            e,
            extra=log_domain(DOMAIN_HUBSPOT, "call_outcome_deal_fetch_failed", memo_id=ctx.memo_id, deal_id=ctx.deal_id),
        )
        return "Couldn't read the deal's pipeline, so its stage wasn't changed."

    if ctx.call_outcome == "lost":
        try:
            schema = await schema_service.get_deal_schema()
            pipeline = next((p for p in schema.pipelines if p.id == pipeline_id), None)
            stage_id = find_closed_lost_stage_id(pipeline) if pipeline else None
        except Exception as e:
            logger.warning(
                "⚠️ Call outcome: closed-lost stage lookup failed: %s",
                e,
                extra=log_domain(DOMAIN_HUBSPOT, "call_outcome_stage_lookup_failed", memo_id=ctx.memo_id),
            )
            stage_id = None

        if stage_id:
            deal_props["dealstage"] = stage_id
        else:
            warning = (
                "This pipeline has no closed-lost stage configured in HubSpot, "
                "so the deal's stage wasn't changed (the contact was still marked Lost)."
            )

        lost_reason_prop = await resolve_lost_reason_property(
            schema_service, ctx.lost_reason_deal_property_configured
        )
        reason = ctx.lost_reason or ""
        if lost_reason_prop is None:
            reason_warning = (
                "No lost-reason property was found on this portal's deals, so the reason "
                "wasn't written to the deal (it's still saved on the contact)."
            )
            warning = f"{warning} {reason_warning}".strip() if warning else reason_warning
        elif lost_reason_prop.type == "enumeration" and lost_reason_prop.options and not _reason_matches_option(lost_reason_prop, reason):
            reason_warning = (
                f"The deal's lost-reason field is a dropdown and doesn't have "
                f"\"{reason}\" as an option, so it wasn't set there (it's still saved on the contact)."
            )
            warning = f"{warning} {reason_warning}".strip() if warning else reason_warning
        else:
            deal_props[lost_reason_prop.name] = reason

    elif ctx.call_outcome == "converted":
        try:
            stage_id = await deals._resolve_stage_id("appointmentscheduled", pipeline_id=pipeline_id)
        except Exception:
            stage_id = None
        if stage_id:
            deal_props["dealstage"] = stage_id
    # on_hold: deliberately no dealstage change - see module docstring.

    if not deal_props:
        return warning

    try:
        async with crm_updates.track(
            memo_id=ctx.memo_id,
            user_id=ctx.user_id,
            crm_connection_id=ctx.connection_id,
            action_type=ACTION_TYPE,
            resource_type="deal",
        ) as tracked:
            await deals.update(ctx.deal_id, deal_props, hubspot_owner_id=ctx.hubspot_owner_id)
            tracked.data = {
                "deal_id": ctx.deal_id,
                "call_outcome": ctx.call_outcome,
                "properties": deal_props,
            }
            tracked.resource_id = ctx.deal_id
            logger.info(
                "✅ Call outcome mirrored to deal",
                extra=log_domain(
                    DOMAIN_HUBSPOT, "call_outcome_deal_updated",
                    deal_id=ctx.deal_id, call_outcome=ctx.call_outcome, memo_id=ctx.memo_id,
                    updated_fields=list(deal_props.keys()),
                ),
            )
    except Exception as e:
        deal_write_warning = "Couldn't update the deal's stage/reason in HubSpot (the contact was still updated)."
        warning = f"{warning} {deal_write_warning}".strip() if warning else deal_write_warning
        logger.warning(
            "⚠️ Call outcome deal update failed: %s",
            e,
            extra=log_domain(
                DOMAIN_HUBSPOT, "call_outcome_deal_failed",
                memo_id=ctx.memo_id, deal_id=ctx.deal_id, error=str(e),
            ),
        )

    return warning
