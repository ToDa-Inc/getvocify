-- Drops the live help event log.

BEGIN;

DROP TABLE IF EXISTS live_assist_events;

COMMIT;
