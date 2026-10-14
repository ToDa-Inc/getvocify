-- What live help did during a call, one row per turn check and per card, so a call can be reviewed afterwards
-- from facts instead of from a recording of the rep reading the cards aloud: what the prospect said, which
-- objection the turn check named, which playbook answer the card followed, which provider wrote the line
-- (the direct one or the OpenRouter backup), how long it took, and the line itself.
-- Small on purpose: the prospect's words are cut to 300 characters and the rolling transcript is not stored
-- (the call's own transcript has it). Rows older than 90 days are deleted by the app (at most once an hour).
-- Written after the response is sent; the app does nothing until this table exists. Service role only.
-- Rollback: 078_live_assist_events.down.sql

BEGIN;

CREATE TABLE IF NOT EXISTS live_assist_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
  -- turn: the check that runs when the prospect pauses; suggest: the card's answer.
  kind TEXT NOT NULL CHECK (kind IN ('turn', 'suggest')),
  sales_motion_key TEXT,
  call_mode TEXT,
  -- The prospect's latest words, at most 300 characters.
  latest_turn TEXT,
  -- turn: what the check said. objection: none | price | timing | ... | custom (a playbook entry of the team's own).
  finished BOOLEAN,
  objection TEXT,
  entry_id TEXT,
  check_ms INTEGER,
  -- suggest: what the card was asked to answer, and what it did.
  objection_type TEXT,
  is_objection BOOLEAN,
  source_id TEXT,
  say_this TEXT,
  -- direct:<model> | openrouter:<model>
  provider TEXT,
  latency_ms INTEGER,
  restarted BOOLEAN,
  error TEXT,
  playbook_version_id TEXT,
  capture_id TEXT,
  -- Which prompt and which deployment wrote it, to compare changes over time.
  prompt_version TEXT,
  build TEXT
);

CREATE INDEX IF NOT EXISTS idx_live_assist_events_user_time ON live_assist_events (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_live_assist_events_time ON live_assist_events (created_at);

ALTER TABLE live_assist_events ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    REVOKE ALL ON live_assist_events FROM anon;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON live_assist_events FROM authenticated;
  END IF;
END $$;

COMMIT;
