-- Whether Vocify processes the call recordings this rep's own dialer (HubSpot calling, Aircall...)
-- saves in the CRM. Off by default: a rep records calls with the Vocify app, so a call is never
-- processed twice. Reps whose company already auto-processes HubSpot calls stay on.
-- The company switch (crm_configurations.auto_sync_hubspot_calls) still decides first.
-- Safe to run whether or not an earlier version of 075 (DEFAULT true) was applied.
-- Rollback: 075_crm_call_recordings.down.sql

BEGIN;

ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS process_crm_call_recordings BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE user_profiles ALTER COLUMN process_crm_call_recordings SET DEFAULT false;

UPDATE user_profiles p
SET process_crm_call_recordings = EXISTS (
  SELECT 1
  FROM crm_connections c
  JOIN crm_configurations cfg ON cfg.connection_id = c.id
  LEFT JOIN company_members m ON m.company_id = c.company_id AND m.user_id = p.id
  WHERE cfg.auto_sync_hubspot_calls
    AND (m.user_id IS NOT NULL OR c.user_id = p.id)
);

COMMIT;

-- Post-apply verification (expect the reps of companies with auto_sync_hubspot_calls on):
-- SELECT id FROM user_profiles WHERE process_crm_call_recordings;
