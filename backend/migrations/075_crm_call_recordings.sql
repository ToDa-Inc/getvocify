-- Whether Vocify processes the call recordings this rep's own dialer (HubSpot calling, Aircall...)
-- saves in the CRM. Off for a rep who records calls with Vocify's island: the call is captured
-- live, so its CRM recording is never processed a second time. The company switch
-- (crm_configurations.auto_sync_hubspot_calls) still decides first.
-- Rollback: 075_crm_call_recordings.down.sql

ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS process_crm_call_recordings BOOLEAN NOT NULL DEFAULT true;
