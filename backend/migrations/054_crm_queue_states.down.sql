BEGIN;

ALTER TABLE crm_configurations
  DROP CONSTRAINT IF EXISTS crm_configurations_queue_state_source_check;

ALTER TABLE crm_configurations
  DROP COLUMN IF EXISTS queue_ended_states,
  DROP COLUMN IF EXISTS queue_booked_states,
  DROP COLUMN IF EXISTS queue_state_source;

COMMIT;
