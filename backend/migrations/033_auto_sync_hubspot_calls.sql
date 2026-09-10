-- Opt-in auto-write after HubSpot-native call recordings land.
-- Off by default: existing workspaces keep Transcribe → review.

BEGIN;

ALTER TABLE crm_configurations
  ADD COLUMN IF NOT EXISTS auto_sync_hubspot_calls BOOLEAN NOT NULL DEFAULT false;

COMMIT;

-- Post-apply verification:
-- SELECT connection_id, auto_sync_hubspot_calls FROM crm_configurations;
