-- Fields AI can fill, per sales role and per person. The Head of Sales keeps one CRM
-- configuration for the whole company (crm_configurations: pipeline, stages, Skip Approve,
-- create contacts/companies, and the company-wide field lists). On top of it:
--   scope = 'role'   scope_key = 'sdr' | 'ae' | 'general'  -> every rep of that type
--   scope = 'member' scope_key = <auth user id>             -> one person, wins over the role
-- Each allowed_*_fields column is independent: NULL inherits from the level below
-- (person -> role -> company), an array (even empty) replaces it for that object.
-- Service role only, same as company_feature_flags (051): the API checks owner/admin.
-- Rollback: 065_crm_field_permissions.down.sql

BEGIN;

CREATE TABLE IF NOT EXISTS crm_field_permissions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  connection_id UUID NOT NULL REFERENCES crm_connections(id) ON DELETE CASCADE,
  scope TEXT NOT NULL CHECK (scope IN ('role', 'member')),
  scope_key TEXT NOT NULL,
  allowed_deal_fields TEXT[],
  allowed_contact_fields TEXT[],
  allowed_company_fields TEXT[],
  allowed_line_item_fields TEXT[],
  updated_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT crm_field_permissions_scope_unique UNIQUE (connection_id, scope, scope_key),
  CONSTRAINT crm_field_permissions_role_key_check
    CHECK (scope <> 'role' OR scope_key IN ('sdr', 'ae', 'general'))
);

CREATE INDEX IF NOT EXISTS idx_crm_field_permissions_company
  ON crm_field_permissions (company_id);

ALTER TABLE crm_field_permissions ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    REVOKE ALL ON crm_field_permissions FROM anon;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON crm_field_permissions FROM authenticated;
  END IF;
END $$;

COMMIT;
