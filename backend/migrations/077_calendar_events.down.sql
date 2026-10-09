-- Drops the stored meetings; the connected calendars stay.

BEGIN;

DROP TABLE IF EXISTS calendar_events;
ALTER TABLE calendar_connections DROP COLUMN IF EXISTS events_synced_at;
ALTER TABLE calendar_connections ALTER COLUMN auto_join SET DEFAULT true;

COMMIT;
