-- Migration 021: Call outcome (Converted / On Hold / Lost)
--
-- Feature: at memo-approval time, the rep marks the result of the call.
-- Lost requires a reason (enforced in the API layer with a 422, not here -
-- see ApproveMemoRequest in backend/app/models/memo.py). This migration only
-- adds the storage this needs; it does not change any existing row.
--
-- Two independent, additive changes, same rules as every migration in this
-- repo: idempotent (safe to run more than once), non-breaking (nothing
-- dropped/renamed), no data touched.
--
-- ORDERING: apply this before deploying the code that uses it (same
-- deployment-ordering concern as migration 020) - the new code calls
-- CRMUpdatesService.track() with action_type='update_call_outcome' /
-- 'create_followup_task' BEFORE calling HubSpot (that's the whole point of
-- track() - see crm_updates.py), so the INSERT must succeed against the
-- CHECK constraint from the first request, not just eventually.

BEGIN;

-- =====================================================================
-- 1. crm_updates.action_type: two new values.
--
-- 'update_call_outcome' (resource_type 'contact' or 'deal', both already
-- allowed - no resource_type change needed) covers writing hs_lead_status +
-- vocify_lost_reason on the contact, and mirroring dealstage + the portal's
-- lost-reason property on the deal when one exists. Two rows per memo (one
-- per object actually written), same pattern as every other multi-object
-- step in sync.py (e.g. upsert_company / upsert_contact already being
-- separate rows for the same memo).
--
-- 'create_followup_task' (resource_type 'task', already allowed) is
-- deliberately NOT 'create_tasks'/'merge_tasks': those two already have
-- their own dedupe check in sync.py (tasks_already_synced, keyed on
-- next-steps). Reusing that action_type for the On Hold follow-up task
-- would let either dedupe wrongly suppress the other on a retry - a memo
-- with both real next-steps AND an On Hold follow-up needs two independent,
-- separately-retryable rows.
-- =====================================================================
ALTER TABLE crm_updates
DROP CONSTRAINT IF EXISTS crm_updates_action_type_check;

ALTER TABLE crm_updates
ADD CONSTRAINT crm_updates_action_type_check
CHECK (action_type IN (
  'create_deal',
  'update_deal',
  'upsert_company',
  'upsert_contact',
  'merge_tasks',
  'create_tasks',
  'create_note',
  'create_line_item',
  'update_call_outcome',
  'create_followup_task'
));

-- =====================================================================
-- 2. crm_configurations: per-account Lost reasons list + resolved deal
--    property name for the portal's own "closed lost reason" field.
--
-- lost_reasons: editable from the HubSpot Configuration screen. Shipped
-- with a sane English default so accounts that never touch this screen
-- still get a usable list instead of an empty one - "Other" is UI-only
-- (opens free text) and is intentionally NOT in this list; the backend
-- accepts whatever string arrives in lost_reason regardless of whether
-- it's one of these values.
--
-- lost_reason_deal_property: nullable on purpose. When unset, the sync
-- path auto-detects a candidate from the portal's live deal schema every
-- time (see resolve_lost_reason_property in
-- backend/app/services/hubspot/call_outcome.py) - this column is a
-- confirmed override for when auto-detection is ambiguous, wrong, or a
-- client wants a specific custom property, not a hard requirement to
-- configure before Lost works at all.
-- =====================================================================
ALTER TABLE crm_configurations
  ADD COLUMN IF NOT EXISTS lost_reasons JSONB NOT NULL DEFAULT
    '["No budget","No response","Chose a competitor","Bad timing","Not a fit"]'::jsonb,
  ADD COLUMN IF NOT EXISTS lost_reason_deal_property TEXT;

COMMIT;

-- Post-apply verification:
-- 1. New action_type values accepted:
--    SELECT pg_get_constraintdef(oid) FROM pg_constraint
--    WHERE conname = 'crm_updates_action_type_check';
-- 2. New crm_configurations columns present with expected defaults:
--    SELECT connection_id, lost_reasons, lost_reason_deal_property
--    FROM crm_configurations;
-- 3. Sanity check nothing existing broke (row counts unchanged):
--    SELECT action_type, COUNT(*) FROM crm_updates GROUP BY action_type;
