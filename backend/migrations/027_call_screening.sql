-- 027_call_screening.sql
--
-- call_disposition on outbound_calls: result of every dialer-placed call
-- (Twilio dial status or post-transcript screening).
-- screening_outcome on memos: denormalized copy for connected/voicemail/no_response
-- memos only (missed calls never get a memo row).

BEGIN;

ALTER TABLE outbound_calls
  ADD COLUMN IF NOT EXISTS call_disposition TEXT
    CHECK (call_disposition IN (
      'connected', 'voicemail', 'no_response',
      'busy', 'no_answer', 'failed', 'canceled'
    ));

ALTER TABLE memos
  ADD COLUMN IF NOT EXISTS screening_outcome TEXT
    CHECK (screening_outcome IN ('connected', 'voicemail', 'no_response'));

COMMIT;
