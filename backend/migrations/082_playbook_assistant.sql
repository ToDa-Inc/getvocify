-- Playbook assistant (docs/superpowers/specs/2026-10-16-playbook-volcado-y-perfeccionamiento-design.md).
-- Three small tables for the Head of Sales' side of the playbook:
--   playbook_assistant_sessions  where the guided questions ("Lo que falta") and the trial left off, so both can be resumed.
--   playbook_review_moments      the improvement queue: real cases copied from the live-help log (which is purged at
--                                90 days) so they survive until the Head of Sales has looked at them.
--   playbook_suggestion_outcomes one verdict per live-help card: did the rep say it, did it settle the objection or doubt.
-- Service role only (the app talks to them from the backend). The app does nothing until these tables exist.
-- A model call's transcript is never stored: it is read, proposals are made, and only what the Head of Sales accepts is kept (in the playbook).
-- NUMBER: 082. 081 is taken by 081_demo_profiles (and there are two 080_*): if someone else adds a 082 meanwhile, renumber this file.
-- Rollback: 082_playbook_assistant.down.sql

BEGIN;

CREATE TABLE IF NOT EXISTS playbook_assistant_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('gaps', 'trial')),
  state JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_playbook_assistant_sessions_open
  ON playbook_assistant_sessions (company_id, kind, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS playbook_review_moments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  source TEXT NOT NULL CHECK (source IN ('trial', 'real')),
  sales_motion_key TEXT,
  entry_id TEXT,
  objection_type TEXT,
  client_text TEXT NOT NULL,
  suggestion_text TEXT,
  rep_text TEXT,
  outcome JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'kept', 'corrected', 'dismissed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_playbook_review_moments_open ON playbook_review_moments (company_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS playbook_suggestion_outcomes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  -- The live-help event (live_assist_events.id). No foreign key: that log is purged at 90 days, the verdict is not.
  event_id UUID NOT NULL UNIQUE,
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  observed_at TIMESTAMPTZ NOT NULL,
  capture_id TEXT,
  sales_motion_key TEXT,
  entry_id TEXT,
  source_id TEXT,
  objection_type TEXT,
  used TEXT NOT NULL DEFAULT 'unknown' CHECK (used IN ('used', 'adapted', 'not_used', 'unknown')),
  resolved TEXT NOT NULL DEFAULT 'unknown' CHECK (resolved IN ('resolved', 'not_resolved', 'unknown')),
  resolved_by TEXT CHECK (resolved_by IN ('extraction', 'judge', 'admin')),
  client_text TEXT,
  suggestion_text TEXT,
  rep_text TEXT,
  judged_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_playbook_suggestion_outcomes_window ON playbook_suggestion_outcomes (company_id, observed_at DESC);

ALTER TABLE playbook_assistant_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE playbook_review_moments ENABLE ROW LEVEL SECURITY;
ALTER TABLE playbook_suggestion_outcomes ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'playbook_assistant_sessions', 'playbook_review_moments', 'playbook_suggestion_outcomes'
  ] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
      EXECUTE format('REVOKE ALL ON %I FROM anon', t);
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
      EXECUTE format('REVOKE ALL ON %I FROM authenticated', t);
    END IF;
  END LOOP;
END $$;

COMMIT;
