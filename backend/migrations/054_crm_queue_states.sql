-- F16: queue exit by CRM state (booked / ended). Empty lists mean nobody exits by state.
-- Backfill copies the F14 meeting-booked stage into queue_booked_states.
-- Rollback: 054_crm_queue_states.down.sql

BEGIN;

ALTER TABLE crm_configurations
  ADD COLUMN IF NOT EXISTS queue_state_source TEXT NOT NULL DEFAULT 'deal_stage',
  ADD COLUMN IF NOT EXISTS queue_booked_states TEXT[] NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS queue_ended_states TEXT[] NOT NULL DEFAULT '{}';

ALTER TABLE crm_configurations
  DROP CONSTRAINT IF EXISTS crm_configurations_queue_state_source_check;

ALTER TABLE crm_configurations
  ADD CONSTRAINT crm_configurations_queue_state_source_check
  CHECK (queue_state_source IN ('deal_stage', 'lead_status'));

UPDATE crm_configurations
SET queue_booked_states = ARRAY[meeting_booked_stage_id]
WHERE meeting_booked_stage_id IS NOT NULL
  AND meeting_booked_stage_id <> ''
  AND (queue_booked_states IS NULL OR queue_booked_states = '{}');

COMMIT;
