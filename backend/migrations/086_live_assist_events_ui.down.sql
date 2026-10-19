-- Drops what 086 added. The UI events are deleted: they cannot stay under the old kind check.

BEGIN;

DELETE FROM live_assist_events WHERE kind = 'ui';
ALTER TABLE live_assist_events DROP CONSTRAINT IF EXISTS live_assist_events_kind_check;
ALTER TABLE live_assist_events
  ADD CONSTRAINT live_assist_events_kind_check CHECK (kind IN ('turn', 'suggest', 'points', 'progress', 'recap'));

COMMIT;
