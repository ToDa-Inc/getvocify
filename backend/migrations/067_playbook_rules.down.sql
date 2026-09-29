-- Drops the label and the routing rule; every type falls back to the role default (D5).

BEGIN;

ALTER TABLE playbooks
  DROP COLUMN IF EXISTS applies_to,
  DROP COLUMN IF EXISTS label;

COMMIT;
