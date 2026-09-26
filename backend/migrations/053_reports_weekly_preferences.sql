-- F13.04 / F15.05: per-person opt-outs for the daily, weekly and team reports (no row = all on),
-- and the moment a meeting write happened so the bell can say when Vocify moved a stage.
-- Existing meeting_writes rows keep created_at NULL: their real time is unknown and the bell
-- hides them rather than inventing one. Service role only, like company_feature_flags.
-- Rollback: 053_reports_weekly_preferences.down.sql

BEGIN;

CREATE TABLE IF NOT EXISTS report_preferences (
  user_id UUID PRIMARY KEY,
  daily_enabled BOOLEAN NOT NULL DEFAULT true,
  weekly_enabled BOOLEAN NOT NULL DEFAULT true,
  team_enabled BOOLEAN NOT NULL DEFAULT true,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE report_preferences ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    REVOKE ALL ON report_preferences FROM anon;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON report_preferences FROM authenticated;
  END IF;
END $$;

-- Added without a default first so existing rows stay NULL, then new rows get now().
ALTER TABLE meeting_writes ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ;
ALTER TABLE meeting_writes ALTER COLUMN created_at SET DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_meeting_writes_created_at
  ON meeting_writes (created_at)
  WHERE stage_changed;

COMMIT;
