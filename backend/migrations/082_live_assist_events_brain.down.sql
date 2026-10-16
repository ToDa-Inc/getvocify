-- Drops what 082 added. The readings of the live call assistant are deleted: they cannot stay under the old kind check.

BEGIN;

DELETE FROM live_assist_events WHERE kind IN ('points', 'progress', 'recap');
ALTER TABLE live_assist_events DROP CONSTRAINT IF EXISTS live_assist_events_kind_check;
ALTER TABLE live_assist_events ADD CONSTRAINT live_assist_events_kind_check CHECK (kind IN ('turn', 'suggest'));
ALTER TABLE live_assist_events DROP COLUMN IF EXISTS detail;

COMMIT;
