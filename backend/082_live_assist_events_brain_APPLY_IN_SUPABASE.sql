-- The live call assistant (spec 2026-10-16-live-call-assistant-design.md) logs one row per reading of each of its
-- producers: kind points | progress | recap, with how long it took, which provider wrote it, which playbook version
-- served it, the call it belongs to (capture_id holds the recording's id) and, in `detail`, what came out: counts, why
-- the reading happened, what the checks dropped. The prospect's words keep the existing limits (300 characters).
-- Until this is applied the app logs nothing for these readings (a failed write pauses them for ten minutes) and the
-- turn checks and cards are not affected.
-- Rollback: 082_live_assist_events_brain.down.sql

BEGIN;

ALTER TABLE live_assist_events ADD COLUMN IF NOT EXISTS detail JSONB;

ALTER TABLE live_assist_events DROP CONSTRAINT IF EXISTS live_assist_events_kind_check;
ALTER TABLE live_assist_events
  ADD CONSTRAINT live_assist_events_kind_check CHECK (kind IN ('turn', 'suggest', 'points', 'progress', 'recap'));

COMMIT;
