-- 026_dialer.sql
--
-- answered_at is the moment the prospect picked up. recording_duration is the
-- recording length and is unknown until Twilio's recording callback fires
-- minutes later; the dialer needs the answer timestamp at answer time.

BEGIN;

ALTER TABLE outbound_calls
  ADD COLUMN IF NOT EXISTS answered_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_outbound_calls_contact
  ON outbound_calls (user_id, hubspot_contact_id, created_at DESC);

COMMIT;
