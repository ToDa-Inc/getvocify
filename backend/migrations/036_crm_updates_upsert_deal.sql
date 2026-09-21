-- Pipedrive sync writes action_type='upsert_deal' (create or patch).
-- Live CHECK from 022 only allows create_deal / update_deal → 23514.
-- Recreate the constraint with every existing value plus upsert_deal.

BEGIN;

ALTER TABLE crm_updates
DROP CONSTRAINT IF EXISTS crm_updates_action_type_check;

ALTER TABLE crm_updates
ADD CONSTRAINT crm_updates_action_type_check
CHECK (action_type IN (
  'create_deal',
  'update_deal',
  'upsert_deal',
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

COMMIT;
