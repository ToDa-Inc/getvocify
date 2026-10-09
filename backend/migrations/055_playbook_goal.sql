-- Lista 3 (T2): the playbook's business objective. Discovery aims at a booked meeting,
-- closing aims at a proposal and close (D4). Not written by the app yet — the app computes
-- the default from sales_motion_key — but reserved for a future per-company override.
-- Rollback: 055_playbook_goal.down.sql

BEGIN;

ALTER TABLE playbooks
  ADD COLUMN IF NOT EXISTS goal TEXT;

COMMIT;
