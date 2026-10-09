-- Drops the playbook goal column.

BEGIN;

ALTER TABLE playbooks
  DROP COLUMN IF EXISTS goal;

COMMIT;
