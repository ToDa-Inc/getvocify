BEGIN;

ALTER TABLE crm_configurations DROP COLUMN IF EXISTS create_tasks;

COMMIT;
