-- 029_telnyx_carrier.sql
--
-- Additive Telnyx columns. Does NOT rename twilio_call_sid /
-- twilio_validation_sid — Railway and local :8888 still use those names.
--
-- Paste this whole file into the Supabase SQL editor and run it.
-- Safe to re-run.

BEGIN;

ALTER TABLE outbound_calls
  ADD COLUMN IF NOT EXISTS carrier TEXT NOT NULL DEFAULT 'twilio';

ALTER TABLE outbound_calls
  ADD COLUMN IF NOT EXISTS carrier_call_id TEXT;

ALTER TABLE outbound_calls
  ADD COLUMN IF NOT EXISTS provider_state JSONB NOT NULL DEFAULT '{}';

UPDATE outbound_calls
SET carrier_call_id = twilio_call_sid
WHERE carrier_call_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS outbound_calls_carrier_call_id_uidx
  ON outbound_calls (carrier_call_id)
  WHERE carrier_call_id IS NOT NULL;

ALTER TABLE user_caller_ids
  ADD COLUMN IF NOT EXISTS verification_sid TEXT;

UPDATE user_caller_ids
SET verification_sid = twilio_validation_sid
WHERE verification_sid IS NULL
  AND twilio_validation_sid IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_user_caller_ids_verification_sid
  ON user_caller_ids (verification_sid)
  WHERE verification_sid IS NOT NULL;

CREATE OR REPLACE FUNCTION vocify_sync_outbound_call_ids()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.carrier_call_id IS NULL AND NEW.twilio_call_sid IS NOT NULL THEN
    NEW.carrier_call_id := NEW.twilio_call_sid;
  END IF;
  IF NEW.twilio_call_sid IS NULL AND NEW.carrier_call_id IS NOT NULL THEN
    NEW.twilio_call_sid := NEW.carrier_call_id;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_vocify_sync_outbound_call_ids ON outbound_calls;
CREATE TRIGGER trg_vocify_sync_outbound_call_ids
  BEFORE INSERT OR UPDATE ON outbound_calls
  FOR EACH ROW
  EXECUTE FUNCTION vocify_sync_outbound_call_ids();

CREATE OR REPLACE FUNCTION vocify_sync_caller_id_sids()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.verification_sid IS NULL AND NEW.twilio_validation_sid IS NOT NULL THEN
    NEW.verification_sid := NEW.twilio_validation_sid;
  END IF;
  IF NEW.twilio_validation_sid IS NULL AND NEW.verification_sid IS NOT NULL THEN
    NEW.twilio_validation_sid := NEW.verification_sid;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_vocify_sync_caller_id_sids ON user_caller_ids;
CREATE TRIGGER trg_vocify_sync_caller_id_sids
  BEFORE INSERT OR UPDATE ON user_caller_ids
  FOR EACH ROW
  EXECUTE FUNCTION vocify_sync_caller_id_sids();

CREATE TABLE IF NOT EXISTS user_telephony_credentials (
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  provider TEXT NOT NULL CHECK (provider IN ('telnyx')),
  credential_id TEXT NOT NULL,
  sip_username TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, provider),
  UNIQUE (sip_username)
);

ALTER TABLE user_telephony_credentials ENABLE ROW LEVEL SECURITY;

COMMIT;
