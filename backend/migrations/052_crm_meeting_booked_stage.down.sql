BEGIN;

ALTER TABLE crm_configurations
  DROP CONSTRAINT IF EXISTS crm_configurations_meeting_booked_stage_check;

ALTER TABLE crm_configurations
  DROP COLUMN IF EXISTS meeting_booked_stage_id,
  DROP COLUMN IF EXISTS meeting_booked_pipeline_id;

COMMIT;
