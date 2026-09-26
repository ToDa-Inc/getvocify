-- Per-company overrides of the global switches in backend/app/config.py, so a feature can be
-- turned on for beta customers one by one. No row = the global env value. `flag` is the
-- Settings attribute name. Service role only: companies is writable by owners/admins through
-- RLS, so overrides live in their own table with RLS on, no policies and no client grants.
-- Rollback: 051_company_feature_flags.down.sql

BEGIN;

CREATE TABLE IF NOT EXISTS company_feature_flags (
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  flag TEXT NOT NULL CHECK (flag ~ '^[A-Z][A-Z0-9_]*$'),
  enabled BOOLEAN NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (company_id, flag)
);

ALTER TABLE company_feature_flags ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    REVOKE ALL ON company_feature_flags FROM anon;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON company_feature_flags FROM authenticated;
  END IF;
END $$;

COMMIT;
