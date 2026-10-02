-- Drops attendees from memos. The history is lost.

BEGIN;

ALTER TABLE memos DROP COLUMN IF EXISTS attendees;

COMMIT;
