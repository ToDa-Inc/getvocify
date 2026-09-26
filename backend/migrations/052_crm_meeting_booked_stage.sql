-- F14: the stage a deal moves to when a booked meeting is saved to the CRM, chosen per company
-- on its CRM configuration. NULL means no stage ever moves. A stage needs its pipeline.
-- Rollback: 052_crm_meeting_booked_stage.down.sql

BEGIN;

ALTER TABLE crm_configurations
  ADD COLUMN IF NOT EXISTS meeting_booked_pipeline_id TEXT,
  ADD COLUMN IF NOT EXISTS meeting_booked_stage_id TEXT;

ALTER TABLE crm_configurations
  DROP CONSTRAINT IF EXISTS crm_configurations_meeting_booked_stage_check;

ALTER TABLE crm_configurations
  ADD CONSTRAINT crm_configurations_meeting_booked_stage_check
  CHECK (meeting_booked_stage_id IS NULL OR meeting_booked_pipeline_id IS NOT NULL);

COMMIT;
