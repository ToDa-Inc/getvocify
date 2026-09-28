-- Drops the follow-up cadence column, the memo follow-up date and outcome, and their checks.

BEGIN;

ALTER TABLE memos
  DROP CONSTRAINT IF EXISTS memos_rep_outcome_check;

ALTER TABLE memos
  DROP COLUMN IF EXISTS rep_outcome;

ALTER TABLE memos
  DROP COLUMN IF EXISTS followup_at;

ALTER TABLE companies
  DROP CONSTRAINT IF EXISTS companies_followup_cadence_check;

ALTER TABLE companies
  DROP COLUMN IF EXISTS followup_cadence;

COMMIT;
