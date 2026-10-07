-- Drops the per-rep switch; every rep's CRM call recordings are processed again (company switch permitting).

ALTER TABLE user_profiles DROP COLUMN IF EXISTS process_crm_call_recordings;
