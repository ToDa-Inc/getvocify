-- Drops report opt-outs (everyone back to the default: all on) and the meeting write time.

BEGIN;

DROP INDEX IF EXISTS idx_meeting_writes_created_at;
ALTER TABLE meeting_writes DROP COLUMN IF EXISTS created_at;
DROP TABLE IF EXISTS report_preferences;

COMMIT;
