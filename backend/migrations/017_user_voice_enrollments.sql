-- Per-user Speechmatics speaker identifiers for Call Copilot (rep voice enrollment).
-- Identifiers are opaque voice representations — treat as sensitive biometric-like data.

CREATE TABLE IF NOT EXISTS user_voice_enrollments (
  user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  rep_label TEXT NOT NULL DEFAULT 'Salesperson',
  speaker_identifiers JSONB NOT NULL DEFAULT '[]'::jsonb,
  sample_count INT NOT NULL DEFAULT 1,
  consent_version TEXT NOT NULL,
  consented_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT user_voice_enrollments_identifiers_array
    CHECK (jsonb_typeof(speaker_identifiers) = 'array'),
  CONSTRAINT user_voice_enrollments_sample_count_positive
    CHECK (sample_count > 0)
);

ALTER TABLE user_voice_enrollments ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_voice_enrollments_select_own ON user_voice_enrollments;
CREATE POLICY user_voice_enrollments_select_own
  ON user_voice_enrollments FOR SELECT
  USING (auth.uid() = user_id);

DROP POLICY IF EXISTS user_voice_enrollments_insert_own ON user_voice_enrollments;
CREATE POLICY user_voice_enrollments_insert_own
  ON user_voice_enrollments FOR INSERT
  WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS user_voice_enrollments_update_own ON user_voice_enrollments;
CREATE POLICY user_voice_enrollments_update_own
  ON user_voice_enrollments FOR UPDATE
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS user_voice_enrollments_delete_own ON user_voice_enrollments;
CREATE POLICY user_voice_enrollments_delete_own
  ON user_voice_enrollments FOR DELETE
  USING (auth.uid() = user_id);

CREATE OR REPLACE FUNCTION set_user_voice_enrollments_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS user_voice_enrollments_updated_at ON user_voice_enrollments;
CREATE TRIGGER user_voice_enrollments_updated_at
  BEFORE UPDATE ON user_voice_enrollments
  FOR EACH ROW
  EXECUTE FUNCTION set_user_voice_enrollments_updated_at();
