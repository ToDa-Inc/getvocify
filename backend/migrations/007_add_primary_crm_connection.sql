-- Primary CRM for sync when user has multiple connected providers (HubSpot + Salesforce, etc.)
ALTER TABLE user_profiles
  ADD COLUMN IF NOT EXISTS primary_crm_connection_id UUID REFERENCES crm_connections(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_user_profiles_primary_crm
  ON user_profiles (primary_crm_connection_id)
  WHERE primary_crm_connection_id IS NOT NULL;
