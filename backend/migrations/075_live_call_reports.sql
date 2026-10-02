-- How each live call's transcription performed: lag per side and provider, and, while
-- LIVE_COMPARE_DEEPGRAM is on, Speechmatics' and Deepgram's text for the same call.
-- Written by the live service only (service role). Rollback: 075_live_call_reports.down.sql

CREATE TABLE IF NOT EXISTS live_call_reports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  report JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS live_call_reports_user_created ON live_call_reports (user_id, created_at DESC);

ALTER TABLE live_call_reports ENABLE ROW LEVEL SECURITY;
