-- The company a sales demo plays for: while a row is live, live help answers as that company (its offer, what it
-- knows, one approved answer per objection) instead of the user's own playbook. One row per user, replaced by the
-- next demo; it expires by itself. Service role only, like company_feature_flags (051).
-- Rollback: 081_demo_profiles.down.sql

BEGIN;

CREATE TABLE IF NOT EXISTS demo_profiles (
  user_id UUID PRIMARY KEY,
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  profile JSONB NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE demo_profiles ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    REVOKE ALL ON demo_profiles FROM anon;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON demo_profiles FROM authenticated;
  END IF;
END $$;

COMMIT;
