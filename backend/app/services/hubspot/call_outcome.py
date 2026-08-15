"""
Call outcome: Converted / On Hold / Lost.

The rep marks the result of a call on the confirmation screen (optional -
None means they didn't mark one, unchanged legacy behavior). This is stored
primarily on the CONTACT (hs_lead_status), and mirrored to the deal only
when one exists:

  converted  -> contact hs_lead_status='OPEN_DEAL' (a real HubSpot default
               option - never created here); deal (if any) dealstage ->
               its pipeline's "appointmentscheduled" stage.
  on_hold    -> contact hs_lead_status=<the account's configured On Hold
               value> + a follow-up task on the deal (or contact, if no
               deal). Deliberately does NOT touch dealstage even when a
               deal exists: guessing which stage of an arbitrary
               customer's pipeline means "on hold" is exactly the kind of
               heuristic that breaks on portals we've never seen - see
               find_closed_lost_stage_id below for why "lost" gets to use
               a real signal (isClosed+probability) instead.
  lost       -> contact hs_lead_status=<the account's configured Lost
               value> + a note recording the reason (see "THE LOST REASON
               NOTE" below); deal (if any) dealstage -> its pipeline's
               closed-lost stage (found via metadata, see
               find_closed_lost_stage_id) + the portal's own lost-reason
               property (see resolve_lost_reason_property), when either
               can be found.

CONFIGURABLE MAPPING, NOT SELF-PROVISIONING: On Hold and Lost each need a
value on the contact's hs_lead_status property that means that outcome.
Earlier versions of this feature had Vocify create two new options itself
(VOCIFY_LOST / VOCIFY_FOLLOW_UP) the first time they were needed, which
required the crm.schemas.contacts.write scope - permission to modify the
CLIENT's CRM schema, not just its data. That scope is no longer requested
at all (see oauth.py). Instead, the admin maps one of their OWN EXISTING
hs_lead_status values to each outcome from the HubSpot Configuration
screen (lost_lead_status_value / on_hold_lead_status_value in
crm_configurations) - if no existing value fits (most commonly "On Hold",
since portals rarely have a lead-status option for that), the admin
creates one themselves in their own HubSpot, guided by that same screen.
Vocify never touches the schema. This is the same reasoning migration 021
already applied to "which pipeline stage means on hold" - guessing at
another portal's meaning for a value is the class of heuristic that
breaks silently; making the client's own admin choose it explicitly (or
build it, if it doesn't exist) is the only version of this that's both
correct and honest about what Vocify is asking permission to touch.

Until an account configures a value for On Hold/Lost, the extension does
not offer that button at all (see compute_call_outcome_availability) -
never "offer it and fail after", same design principle as before, just
gated on configuration instead of a provisioning API call. Converted needs
no configuration (HS_LEAD_STATUS_CONVERTED is a real HubSpot default), but
is still revalidated against the live schema every time, for the rare
portal that removed it.

Every mapped value is REVALIDATED against the live hs_lead_status schema,
both when computing button availability (preview) and again right before
writing (sync) - a value the client deleted or renamed since configuring
must never be written, and must not keep showing a button that would then
silently no-op. See resolve_lead_status_value / _get_contact_lead_status_options.

THE LOST REASON NOTE: with the custom vocify_lost_reason contact property
gone (it required schema-write to create; confirmed not left behind in any
connected portal from earlier testing), the Lost reason is recorded as a
HubSpot note instead - a note is a data write (crm.objects.notes.write),
never a schema write. It's merged into the memo's own transcript note when
one is created in the same sync (see sync.py Step 7 and
note_format.format_hubspot_note_body) so the timeline doesn't get two
back-to-back entries for the same call; otherwise (create_note=false, no
transcript, or that step failed) a small standalone note is created here
instead - see _ensure_lost_reason_note. This note is the one thing this
module guarantees for Lost, independent of whether hs_lead_status is
mapped at all: even an account that hasn't configured a Lost value yet
would have gotten the note (though in practice the extension won't offer
the Lost button before that's configured either - this guarantee mostly
covers the narrow race where a value was valid when the preview was built
and invalidated before the rep hit approve).

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

from app.logging_config import log_domain, DOMAIN_HUBSPOT
from app.models.approval import CallOutcomeAvailability
from app.services.crm_updates import CRMUpdatesService

from .associations import HubSpotAssociationService
from .client import HubSpotClient
from .contacts import HubSpotContactService
from .deals import HubSpotDealService
from .note_format import format_standalone_call_outcome_note_body
from .notes import create_note_with_associations
from .schema import HubSpotSchemaService
from .tasks import HubSpotTasksService, _next_step_schedule_hints, _parse_date_from_text
from .types import HubSpotPipeline, HubSpotProperty
from app.models.memo import MemoExtraction

logger = logging.getLogger(__name__)

CallOutcome = Literal["converted", "on_hold", "lost"]

# The only hardcoded value left: a real HubSpot default option, present on
# every portal unless an admin explicitly removed it (revalidated below
# just like the configured On Hold/Lost values, for that edge case).
HS_LEAD_STATUS_CONVERTED = "OPEN_DEAL"
HS_LEAD_STATUS_PROPERTY = "hs_lead_status"

ACTION_TYPE = "update_call_outcome"
FOLLOWUP_TASK_ACTION_TYPE = "create_followup_task"
OUTCOME_NOTE_ACTION_TYPE = "create_outcome_note"


class CallOutcomeWriteResult(NamedTuple):
    """Split so callers (sync.py) can tell a cosmetic degradation from a
    real data-loss failure - see SyncResult.outcome_warning/outcome_failed
    in hubspot/types.py for what each becomes on the wire."""

    warning: Optional[str] = None
    failed: Optional[str] = None


# ============================================================================
# AVAILABILITY (button gating) - see module docstring for why this is
# configuration + revalidation, not self-provisioning.
# ============================================================================

async def _get_contact_lead_status_options(schema_service: HubSpotSchemaService) -> set[str]:
    """Live set of this portal's current hs_lead_status option values.
    Empty set (never an exception) on any failure - callers treat that
    exactly like "nothing is valid right now", the safe default."""
    try:
        schema = await schema_service.get_contact_schema()
    except Exception as e:
        logger.warning(
            "Call outcome: hs_lead_status schema fetch failed: %s",
            e,
            extra=log_domain(DOMAIN_HUBSPOT, "call_outcome_lead_status_schema_failed", error=str(e)),
        )
        return set()
    prop = next((p for p in schema.properties if p.name == HS_LEAD_STATUS_PROPERTY), None)
    return {opt.value for opt in prop.options} if prop else set()


async def compute_call_outcome_availability(
    *,
    schema_service: HubSpotSchemaService,
    lost_lead_status_value: Optional[str],
    on_hold_lead_status_value: Optional[str],
) -> CallOutcomeAvailability:
    """
    Called once per preview (see app/api/memos.py) - one schema fetch
    (cached, see HubSpotSchemaService) covers all three checks.
    """
    valid_values = await _get_contact_lead_status_options(schema_service)
    return CallOutcomeAvailability(
        converted=HS_LEAD_STATUS_CONVERTED in valid_values,
        on_hold=bool(on_hold_lead_status_value) and on_hold_lead_status_value in valid_values,
        lost=bool(lost_lead_status_value) and lost_lead_status_value in valid_values,
    )


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
    lost_lead_status_value: Optional[str]
    on_hold_lead_status_value: Optional[str]
    contact_id: Optional[str]
    deal_id: Optional[str]
    company_id: Optional[str]
    contact_name: Optional[str]
    hubspot_owner_id: Optional[str]
    # True when sync.py's Step 7 already wrote the Lost reason into the
    # memo's own transcript note this run, or a prior run did (see
    # sync.py's outcome_note_already_recorded) - tells _ensure_lost_reason_note
    # not to create a second, redundant note for the same reason.
    outcome_note_already_recorded: bool = False
    previous_updates: list[dict[str, Any]] = field(default_factory=list)
    extraction: Optional[MemoExtraction] = None


async def apply_call_outcome(
    ctx: CallOutcomeContext,
    *,
    crm_updates: CRMUpdatesService,
    contacts: HubSpotContactService,
    deals: HubSpotDealService,
    tasks: HubSpotTasksService,
    client: HubSpotClient,
    associations: HubSpotAssociationService,
    schema_service: HubSpotSchemaService,
) -> CallOutcomeWriteResult:
    """
    Write the call outcome to HubSpot. Returns a CallOutcomeWriteResult
    distinguishing two severities (see SyncResult.outcome_warning/
    outcome_failed in hubspot/types.py for how each surfaces to the rep):

    - .failed: for Lost, the reason note (the one guaranteed record - see
      module docstring) did NOT land anywhere. For any outcome, no contact
      was resolved at all. This must not be presented as success.
    - .warning: everything guaranteed landed, but a secondary write didn't
      - hs_lead_status has no valid mapped value right now, the contact
      update itself failed, the deal mirror (dealstage / lost-reason
      property) didn't apply, or the On Hold follow-up task failed.

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
        lead_status_options = await _get_contact_lead_status_options(schema_service)

        configured_value: Optional[str] = None
        if ctx.call_outcome == "lost":
            configured_value = ctx.lost_lead_status_value
        elif ctx.call_outcome == "on_hold":
            configured_value = ctx.on_hold_lead_status_value
        elif ctx.call_outcome == "converted":
            configured_value = HS_LEAD_STATUS_CONVERTED

        resolved_value = (
            configured_value if configured_value and configured_value in lead_status_options else None
        )

        if resolved_value:
            try:
                async with crm_updates.track(
                    memo_id=ctx.memo_id,
                    user_id=ctx.user_id,
                    crm_connection_id=ctx.connection_id,
                    action_type=ACTION_TYPE,
                    resource_type="contact",
                ) as tracked:
                    await contacts.update(ctx.contact_id, {HS_LEAD_STATUS_PROPERTY: resolved_value})
                    tracked.data = {
                        "contact_id": ctx.contact_id,
                        "call_outcome": ctx.call_outcome,
                        "properties": {HS_LEAD_STATUS_PROPERTY: resolved_value},
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
                # Not critical: for Lost, the reason is guaranteed via the
                # note below regardless of whether this write lands; for
                # Converted/On Hold there's no separate guarantee, but this
                # is still a secondary field write, not the rep's whole
                # action disappearing.
                warning = f"Couldn't update the contact's status in HubSpot for the {ctx.call_outcome} outcome."
                logger.warning(
                    "⚠️ Call outcome contact update failed: %s",
                    e,
                    extra=log_domain(
                        DOMAIN_HUBSPOT, "call_outcome_contact_failed",
                        memo_id=ctx.memo_id, contact_id=ctx.contact_id, error=str(e),
                    ),
                )
        else:
            unmapped_warning = (
                "No 'On hold' status is mapped for this account (or the mapped value no longer "
                "exists in HubSpot), so the contact's status wasn't changed."
                if ctx.call_outcome == "on_hold"
                else "No 'Lost' status is mapped for this account (or the mapped value no longer "
                "exists in HubSpot), so the contact's status wasn't changed (the reason was still "
                "recorded in a note)."
                if ctx.call_outcome == "lost"
                else "HubSpot's default 'Open Deal' status option is missing from this portal, so "
                "the contact's status wasn't changed."
            )
            logger.warning(
                "Call outcome: no valid hs_lead_status value to write (%s, configured=%r)",
                ctx.call_outcome, configured_value,
                extra=log_domain(
                    DOMAIN_HUBSPOT, "call_outcome_no_valid_lead_status",
                    memo_id=ctx.memo_id, call_outcome=ctx.call_outcome,
                ),
            )
            warning = unmapped_warning

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

    # --- Lost reason note (guaranteed record - see module docstring) ---
    if ctx.call_outcome == "lost" and not ctx.outcome_note_already_recorded:
        note_failure = await _ensure_lost_reason_note(
            ctx, crm_updates=crm_updates, client=client, associations=associations,
        )
        if note_failure:
            failed = note_failure

    # --- Follow-up task for On Hold (independent of the above - its own dedupe) ---
    if ctx.call_outcome == "on_hold":
        followup_warning = await _create_followup_task(
            ctx, crm_updates=crm_updates, tasks=tasks
        )
        if followup_warning:
            warning = f"{warning} {followup_warning}".strip() if warning else followup_warning

    return CallOutcomeWriteResult(warning=warning, failed=failed)


async def _ensure_lost_reason_note(
    ctx: CallOutcomeContext,
    *,
    crm_updates: CRMUpdatesService,
    client: HubSpotClient,
    associations: HubSpotAssociationService,
) -> Optional[str]:
    """
    Guarantees the Lost reason is visible somewhere in HubSpot even when
    hs_lead_status has no valid mapped value for this account - a small
    standalone note associated to whatever this memo resolved (contact,
    plus deal/company if present). Not called at all when sync.py's Step 7
    already merged the same information into the memo's own transcript
    note (see ctx.outcome_note_already_recorded) - one note per call, never
    two saying the same thing.

    Returns a user-facing message on failure. Unlike every other write in
    this module, this one has no fallback left if it fails - the caller
    treats that as CRITICAL (see apply_call_outcome).
    """
    already_done = CRMUpdatesService.is_action_already_done(
        ctx.previous_updates, (OUTCOME_NOTE_ACTION_TYPE,)
    )
    if already_done:
        logger.info(
            "Skipping duplicate outcome note for memo retry",
            extra=log_domain(DOMAIN_HUBSPOT, "outcome_note_skipped_duplicate", memo_id=ctx.memo_id),
        )
        return None

    note_body = format_standalone_call_outcome_note_body(lost_reason=ctx.lost_reason)
    note_properties: dict[str, Any] = {
        "hs_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hs_note_body": note_body,
    }
    if ctx.hubspot_owner_id:
        note_properties["hubspot_owner_id"] = ctx.hubspot_owner_id

    try:
        async with crm_updates.track(
            memo_id=ctx.memo_id,
            user_id=ctx.user_id,
            crm_connection_id=ctx.connection_id,
            action_type=OUTCOME_NOTE_ACTION_TYPE,
            resource_type="note",
        ) as tracked:
            note_id = await create_note_with_associations(
                client,
                associations,
                note_properties=note_properties,
                deal_id=ctx.deal_id,
                contact_id=ctx.contact_id,
                company_id=ctx.company_id,
                memo_id=ctx.memo_id,
                log_event="call_outcome_note",
            )
            if not note_id:
                raise RuntimeError("HubSpot note creation returned no id")
            tracked.data = {
                "note_id": note_id,
                "contact_id": ctx.contact_id,
                "deal_id": ctx.deal_id,
                "company_id": ctx.company_id,
            }
            tracked.resource_id = note_id
            logger.info(
                "✅ Lost reason note created",
                extra=log_domain(
                    DOMAIN_HUBSPOT, "outcome_note_created",
                    note_id=note_id, contact_id=ctx.contact_id, deal_id=ctx.deal_id, memo_id=ctx.memo_id,
                ),
            )
    except Exception as e:
        logger.warning(
            "⚠️ Lost reason note creation failed: %s",
            e,
            extra=log_domain(DOMAIN_HUBSPOT, "outcome_note_failed", memo_id=ctx.memo_id, error=str(e)),
        )
        return "Couldn't save the Lost reason anywhere in HubSpot (not on the contact, not as a note)."
    return None


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
                "so the deal's stage wasn't changed (the reason was still recorded in a note)."
            )

        lost_reason_prop = await resolve_lost_reason_property(
            schema_service, ctx.lost_reason_deal_property_configured
        )
        reason = ctx.lost_reason or ""
        if lost_reason_prop is None:
            reason_warning = (
                "No lost-reason property was found on this portal's deals, so the reason "
                "wasn't written to the deal (it's still recorded in a note)."
            )
            warning = f"{warning} {reason_warning}".strip() if warning else reason_warning
        elif lost_reason_prop.type == "enumeration" and lost_reason_prop.options and not _reason_matches_option(lost_reason_prop, reason):
            reason_warning = (
                f"The deal's lost-reason field is a dropdown and doesn't have "
                f"\"{reason}\" as an option, so it wasn't set there (it's still recorded in a note)."
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
        deal_write_warning = "Couldn't update the deal's stage/reason in HubSpot."
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
