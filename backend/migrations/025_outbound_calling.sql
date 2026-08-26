-- 025_outbound_calling.sql
--
-- Outbound calling through Twilio with the SDR's own number as caller ID.
--
--   user_caller_ids  — one row per (user, phone number) verified with Twilio's
--                      OutgoingCallerIds resource. Twilio enforces ownership;
--                      this table is how the voice webhook decides whether a
--                      client is allowed to present a given number.
--   outbound_calls   — created by the voice webhook keyed on the parent (client)
--                      leg CallSid, which is the same CallSid the recording
--                      callback reports. Carries the CRM association from dial
--                      time through to the recording arriving minutes later.
--
-- memos.source gains 'vocify_call' so calls placed by Vocify are
-- distinguishable from recordings fetched out of HubSpot ('hubspot_call').

BEGIN;

CREATE TABLE IF NOT EXISTS user_caller_ids (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  phone_number TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'verified', 'failed')),
  label TEXT,
  is_default BOOLEAN NOT NULL DEFAULT FALSE,
  -- Twilio validation-call CallSid; correlates status callbacks to one attempt.
  twilio_validation_sid TEXT,
  verified_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, phone_number)
);

CREATE INDEX IF NOT EXISTS idx_user_caller_ids_user
  ON user_caller_ids (user_id, status);

-- The voice webhook looks numbers up by number alone (it only knows the
-- Twilio identity + requested caller ID), so this lookup must be indexed.
CREATE INDEX IF NOT EXISTS idx_user_caller_ids_number
  ON user_caller_ids (phone_number);

CREATE INDEX IF NOT EXISTS idx_user_caller_ids_validation_sid
  ON user_caller_ids (twilio_validation_sid)
  WHERE twilio_validation_sid IS NOT NULL;

CREATE TABLE IF NOT EXISTS outbound_calls (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  twilio_call_sid TEXT NOT NULL UNIQUE,
  from_number TEXT NOT NULL,
  to_number TEXT NOT NULL,
  hubspot_hub_id TEXT,
  hubspot_contact_id TEXT,
  hubspot_deal_id TEXT,
  hubspot_engagement_id TEXT,
  recording_sid TEXT,
  recording_path TEXT,
  recording_duration INTEGER,
  memo_id UUID REFERENCES memos(id) ON DELETE SET NULL,
  status TEXT NOT NULL DEFAULT 'dialing'
    CHECK (status IN ('dialing', 'recorded', 'logged', 'failed')),
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_outbound_calls_user
  ON outbound_calls (user_id, created_at DESC);

ALTER TABLE user_caller_ids ENABLE ROW LEVEL SECURITY;
ALTER TABLE outbound_calls ENABLE ROW LEVEL SECURITY;

ALTER TABLE memos DROP CONSTRAINT IF EXISTS memos_source_check;
ALTER TABLE memos ADD CONSTRAINT memos_source_check
  CHECK (source IN (
    'web', 'voice_memo', 'whatsapp', 'unipile', 'hubspot_call', 'vocify_call'
  ));

-- Private bucket: call audio is personal data under RGPD and must not be
-- reachable by URL alone. HubSpot playback uses short-lived signed URLs.
INSERT INTO storage.buckets (id, name, public)
VALUES ('call-recordings', 'call-recordings', FALSE)
ON CONFLICT (id) DO NOTHING;

COMMIT;
