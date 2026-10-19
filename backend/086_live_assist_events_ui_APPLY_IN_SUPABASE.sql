-- The live call assistant's "Qué decir" view logs what the rep did with it (build contract 2026-10-20 §2.4): one row per UI
-- event, kind 'ui', with the event in `detail` (detail.event = shown | dismissed | reopened | rewrite | ask_step | tick | untick
-- | responder | bubble | open_recap | open_steps | open_brief | marker_shown | marker_seen) and the call in capture_id. This is
-- how we learn which suggestions help. The prospect's words keep the existing limits (300 characters, 90-day purge).
-- Until this is applied POST /copilot/live/events answers 204 and writes nothing (a failed write pauses it for ten minutes);
-- the readings and cards are not affected.
-- NUMBER: 086 (085 sales_process_goal): if someone else adds a 086, renumber this file.
-- Rollback: 086_live_assist_events_ui.down.sql

BEGIN;

ALTER TABLE live_assist_events DROP CONSTRAINT IF EXISTS live_assist_events_kind_check;
ALTER TABLE live_assist_events
  ADD CONSTRAINT live_assist_events_kind_check CHECK (kind IN ('turn', 'suggest', 'points', 'progress', 'recap', 'ui'));

COMMIT;
