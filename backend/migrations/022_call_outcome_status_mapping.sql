-- Migration 022: Call outcome status mapping (configurable, no schema writes)
--
-- Replaces migration 021's self-provisioning design (which required
-- crm.schemas.contacts.write to create VOCIFY_LOST / VOCIFY_FOLLOW_UP
-- options on the client's hs_lead_status property). That scope is no longer
-- requested at all - see backend/app/services/hubspot/oauth.py. Instead,
-- each account's admin picks which of their OWN EXISTING hs_lead_status
-- values means "On Hold" / "Lost" from the HubSpot Configuration screen.
-- Vocify never creates or edits HubSpot picklist options.
--
-- The Lost reason itself no longer lives in a custom contact property
-- either (vocify_lost_reason is gone - confirmed not created in any
-- connected portal as of this migration, see chat history) - it's written
-- as a HubSpot note instead (merged into the memo's own transcript note
-- when one is created in the same sync, otherwise a small standalone note -
-- see format_call_outcome_section / _ensure_lost_reason_note in
-- backend/app/services/hubspot/call_outcome.py). That's why this migration
-- needs a new crm_updates.action_type for the standalone case, but no new
-- contact-property machinery.
--
-- Same rules as every migration in this repo: idempotent, non-breaking, no
-- data touched. ORDERING: apply this before deploying the code that uses it
-- - same reasoning as migration 021 (crm_updates.track() reserves a
-- 'pending' row for the new action_type BEFORE calling HubSpot, so the
-- INSERT must pass the CHECK constraint from the very first request).

BEGIN;

-- =====================================================================
-- 1. crm_updates.action_type: one new value for the standalone Lost-reason
--    note (resource_type 'note', already allowed - see migration 021).
--    Kept separate from 'create_note' (the memo's own transcript note) so
--    each is independently retryable: a memo can merge the reason into its
--    transcript note (no new row needed at all - it's part of the existing
--    'create_note' row's data), OR write it standalone when there's no
--    transcript note to merge into (create_note=false, no transcript, or
--    that step failed) - never both, see _ensure_lost_reason_note.
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
  'create_followup_task',
  'create_outcome_note'
));

-- =====================================================================
-- 2. crm_configurations: the admin's mapping from THIS portal's own
--    hs_lead_status values to Vocify's On Hold / Lost outcomes.
--
-- Both nullable, no default - NULL means "not configured", which is a
-- real, expected, gating state (not an oversight to auto-fill): the
-- extension does not show the On Hold / Lost buttons at all until the
-- admin has picked a value here (see call_outcome.py:
-- compute_call_outcome_availability), because there is no safe default to
-- guess - see migration 021 for the same reasoning about "on hold" pipeline
-- stages, which applies identically to lead-status values.
--
-- Revalidated against the live hs_lead_status schema on every preview AND
-- every sync (not just trusted from this column) - a client who deletes or
-- renames the option after configuring it must not get an invalid value
-- silently written.
-- =====================================================================
ALTER TABLE crm_configurations
  ADD COLUMN IF NOT EXISTS lost_lead_status_value TEXT,
  ADD COLUMN IF NOT EXISTS on_hold_lead_status_value TEXT;

COMMIT;

-- Post-apply verification:
-- 1. New action_type value accepted:
--    SELECT pg_get_constraintdef(oid) FROM pg_constraint
--    WHERE conname = 'crm_updates_action_type_check';
-- 2. New crm_configurations columns present (NULL for every existing row,
--    since nobody has mapped anything yet):
--    SELECT connection_id, lost_lead_status_value, on_hold_lead_status_value
--    FROM crm_configurations;
-- 3. Sanity check nothing existing broke (row counts unchanged):
--    SELECT action_type, COUNT(*) FROM crm_updates GROUP BY action_type;
