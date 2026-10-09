-- Drops the callback-after-days column and its check.

BEGIN;

ALTER TABLE companies
  DROP CONSTRAINT IF EXISTS companies_callback_after_days_check;

ALTER TABLE companies
  DROP COLUMN IF EXISTS callback_after_days;

COMMIT;
