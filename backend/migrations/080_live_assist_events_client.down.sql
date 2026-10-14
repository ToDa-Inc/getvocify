-- Drops the client timing stamps; the event log stays.

BEGIN;

ALTER TABLE live_assist_events DROP COLUMN IF EXISTS client;

COMMIT;
