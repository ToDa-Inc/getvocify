-- 029_telnyx_carrier.sql
--
-- Telnyx as a second outbound carrier behind CALLING_PROVIDER.
--
--   outbound_calls.carrier / carrier_call_id / provider_state
--   user_caller_ids.verification_sid (was twilio_validation_sid)
--   user_telephony_credentials — per-user Telnyx SIP credential mapping
--
-- RLS on user_telephony_credentials matches user_caller_ids / outbound_calls:
-- ENABLE only, no policies (deny-all for roles subject to RLS; service role bypasses).

BEGIN;

ALTER TABLE outbound_calls
  ADD COLUMN IF NOT EXISTS carrier TEXT NOT NULL DEFAULT 'twilio';

ALTER TABLE outbound_calls
  RENAME COLUMN twilio_call_sid TO carrier_call_id;

ALTER TABLE user_caller_ids
  RENAME COLUMN twilio_validation_sid TO verification_sid;

DROP INDEX IF EXISTS idx_user_caller_ids_validation_sid;
CREATE INDEX IF NOT EXISTS idx_user_caller_ids_verification_sid
  ON user_caller_ids (verification_sid)
  WHERE verification_sid IS NOT NULL;

ALTER TABLE outbound_calls
  ADD COLUMN IF NOT EXISTS provider_state JSONB NOT NULL DEFAULT '{}';

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
