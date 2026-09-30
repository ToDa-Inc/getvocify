-- A rep's connected calendar (Recall.ai Calendar V2). Recall holds the OAuth refresh token
-- and keeps the events synced; we keep which Recall calendar belongs to whom, its status,
-- and the rep's switch for whether the Vocify bot joins their meetings. One calendar per
-- rep: connecting again replaces the previous one. Service role only, like report_preferences.
-- Rollback: 070_calendar_connections.down.sql

BEGIN;

CREATE TABLE IF NOT EXISTS calendar_connections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  platform TEXT NOT NULL CHECK (platform IN ('google_calendar', 'microsoft_outlook')),
  recall_calendar_id UUID NOT NULL UNIQUE,
  email TEXT,
  status TEXT NOT NULL DEFAULT 'connecting' CHECK (status IN ('connecting', 'connected', 'disconnected')),
  auto_join BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE calendar_connections ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    REVOKE ALL ON calendar_connections FROM anon;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON calendar_connections FROM authenticated;
  END IF;
END $$;

COMMIT;
