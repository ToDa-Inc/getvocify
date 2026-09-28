-- Lista 4 (T2, E8): follow-up cadence for the SDR's Hoy.
--   companies.followup_cadence: the Head of Sales' own waits per stopper, {stopper: days}
--     (e.g. {"price": 5, "timing": 30}). NULL = E8's defaults. The app validates keys and
--     1..90 days (app/services/hoy/cadence.py parse_overrides) and ignores anything else.
--   memos.followup_at: the date the rep picked after the call; it beats the cadence.
--   memos.rep_outcome: the outcome the rep recorded after the call. not_interested and
--     disqualified (and meeting_booked) never bring the contact back as a follow-up.
-- T2 only reads the memo columns (tolerating their absence); T4 writes them.
-- Rollback: 062_sdr_followup_cadence.down.sql

BEGIN;

ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS followup_cadence JSONB NULL;

ALTER TABLE companies
  DROP CONSTRAINT IF EXISTS companies_followup_cadence_check;

ALTER TABLE companies
  ADD CONSTRAINT companies_followup_cadence_check
  CHECK (followup_cadence IS NULL OR jsonb_typeof(followup_cadence) = 'object');

ALTER TABLE memos
  ADD COLUMN IF NOT EXISTS followup_at TIMESTAMPTZ NULL;

ALTER TABLE memos
  ADD COLUMN IF NOT EXISTS rep_outcome TEXT NULL;

ALTER TABLE memos
  DROP CONSTRAINT IF EXISTS memos_rep_outcome_check;

ALTER TABLE memos
  ADD CONSTRAINT memos_rep_outcome_check
  CHECK (rep_outcome IS NULL OR rep_outcome IN ('meeting_booked', 'follow_up', 'not_interested', 'disqualified'));

COMMIT;
