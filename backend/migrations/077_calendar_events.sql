-- The rep's meetings from their connected calendar (Recall.ai Calendar V2), kept for meeting
-- context: who each meeting is with, matched to HubSpot contacts by email. Feeds the island's
-- heads-up before a meeting and links a desktop recording to its meeting. Written on every
-- calendar sync; rows older than a day are dropped. Service role only, like calendar_connections.
-- Rollback: 077_calendar_events.down.sql

BEGIN;

CREATE TABLE IF NOT EXISTS calendar_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  recall_event_id TEXT NOT NULL UNIQUE,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  start_time TIMESTAMPTZ NOT NULL,
  end_time TIMESTAMPTZ,
  title TEXT,
  meeting_url TEXT,
  -- [{email, name, external, matched, hubspot_contact_id, hubspot_name}], the rep and rooms excluded.
  attendees JSONB NOT NULL DEFAULT '[]'::jsonb,
  -- Deleted, cancelled, or declined by the rep.
  is_deleted BOOLEAN NOT NULL DEFAULT false,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_calendar_events_user_start ON calendar_events (user_id, start_time);

ALTER TABLE calendar_events ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    REVOKE ALL ON calendar_events FROM anon;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON calendar_events FROM authenticated;
  END IF;
END $$;

-- When the meetings were last listed in full (the island refreshes them when this is old).
ALTER TABLE calendar_connections ADD COLUMN IF NOT EXISTS events_synced_at TIMESTAMPTZ;

-- New calendars give meeting context; the bot joins only once the rep switches it on.
ALTER TABLE calendar_connections ALTER COLUMN auto_join SET DEFAULT false;

COMMIT;
