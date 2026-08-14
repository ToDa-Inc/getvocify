-- Migration 020: Add 'line_item' to crm_updates.resource_type CHECK
--
-- Bug found while auditing every resource_type value used in sync.py before
-- migrating call sites to track() (per FASE 2.2 review). It is NOT one of
-- the two new track() sites added in that migration - it predates this
-- entire effort:
--
-- Migration 015 (crm_updates_line_item_action.sql) added 'create_line_item'
-- to the action_type CHECK, but the matching resource_type value the code
-- has always used for that action - resource_type="line_item"
-- (backend/app/services/hubspot/sync.py, create_line_item block) - was
-- never added to the resource_type CHECK. That constraint has only ever
-- allowed ('deal', 'contact', 'company', 'task', 'note') - verified against
-- both production's pg_get_constraintdef dump (transcribed into
-- migrations/018_schema_baseline.sql) and every migration file in this
-- repo: resource_type is only ever touched in 018, and 'line_item' is not
-- in it there either.
--
-- Effect in production: every INSERT into crm_updates for a create_line_item
-- action has been violating this CHECK constraint since migration 015 was
-- applied, unconditionally. sync.py's per-item try/except swallows the
-- resulting exception and logs it as a generic "⚠️ Line item create failed"
-- warning (backend/app/services/hubspot/sync.py) - indistinguishable from a
-- real HubSpot failure in the logs, even though the line item itself was
-- created successfully in HubSpot; only the audit write ever failed. This
-- has apparently never been observed/reported because no account exercising
-- line items (allowed_line_item_fields configured + extracted line item
-- data) has hit this path yet - the account-wide crm_updates audit (FASE
-- 2.2 point 4) found zero create_line_item rows in the 8 that exist.
--
-- Fix: add 'line_item' to the allowed values, matching action_type's own
-- list. Purely additive - existing rows are unaffected, no data migration
-- needed (there ARE no create_line_item rows to fix).
--
-- DEPLOYMENT ORDERING - this is not optional, unlike most additive
-- migrations in this repo: this migration MUST be applied before (or
-- atomically with) deploying the track()-enabled sync.py. Before track(),
-- CRMUpdatesService.create_update() was called AFTER the HubSpot API call
-- had already succeeded, so this CHECK violation only ever lost the audit
-- row - the line item itself still landed in HubSpot fine. track() reserves
-- the crm_updates row BEFORE calling HubSpot (that's the whole point - see
-- FASE 2.2), so the same CHECK violation would now raise BEFORE
-- self.client.post() to create the line item ever runs. Deploying track()
-- against a database that still has the old resource_type CHECK would turn
-- this from "audit lost, line item created" into "line item never created
-- at all, for every attempt, in production."

BEGIN;

ALTER TABLE crm_updates
DROP CONSTRAINT IF EXISTS crm_updates_resource_type_check;

ALTER TABLE crm_updates
ADD CONSTRAINT crm_updates_resource_type_check
CHECK (resource_type IN ('deal', 'contact', 'company', 'task', 'note', 'line_item'));

COMMIT;

-- Post-apply verification:
-- 1. Constraint now includes line_item:
--    SELECT pg_get_constraintdef(oid) FROM pg_constraint
--    WHERE conname = 'crm_updates_resource_type_check';
-- 2. Sanity check nothing broke (should be unchanged from before this ran):
--    SELECT resource_type, COUNT(*) FROM crm_updates GROUP BY resource_type;
