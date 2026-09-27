-- Lista 3 (T5): how many days after an unanswered call attempt (no_response/voicemail on
-- the screening outcome) Hoy surfaces a "callback_no_answer" card. Default 2, per company.
-- Rollback: 057_callback_after_days.down.sql

BEGIN;

ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS callback_after_days INTEGER NOT NULL DEFAULT 2;

ALTER TABLE companies
  DROP CONSTRAINT IF EXISTS companies_callback_after_days_check;

ALTER TABLE companies
  ADD CONSTRAINT companies_callback_after_days_check
  CHECK (callback_after_days > 0);

COMMIT;
