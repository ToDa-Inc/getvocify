-- «Cómo trabajamos» per call type: what a good outcome is (the goal, the other good outcomes, when to stop pursuing the
-- goal) and how the company conducts these calls (a few criteria in its own words). The live card brain reads it as
-- guidance on how to decide, never as a source of facts. Not versioned: like `recognize` (076), a change applies to the
-- next call; steps, objections and qualification keep their draft and publish.
--   conduct  {"goal": text, "also_good": text, "stop_when": text, "criteria": [text]}  NULL = not configured
-- Nullable, no backfill. Read and written by the backend (service role) with plain selects and updates: no function
-- changes, so the app works the same until this is applied (the «Cómo trabajamos» tab then says it cannot save).
-- NUMBER: 087 (086 live_assist_events_ui): if someone else adds a 087, renumber this file.
-- Rollback: 087_playbook_conduct.down.sql

BEGIN;

ALTER TABLE playbooks ADD COLUMN IF NOT EXISTS conduct JSONB;

COMMIT;
