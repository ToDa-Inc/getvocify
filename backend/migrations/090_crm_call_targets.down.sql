BEGIN;

ALTER TABLE crm_configurations DROP CONSTRAINT IF EXISTS crm_configurations_call_targets_check;
ALTER TABLE crm_configurations DROP COLUMN IF EXISTS call_targets;

COMMIT;
