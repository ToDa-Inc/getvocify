-- Lista 3 (T8/D10): the Head of Sales's sales strategy, free text. Entered on Settings ->
-- Offer, edited only by owner/admin, read as context by follow-up (D9), briefs and Ask.
-- Rollback: 058_sales_strategy.down.sql

BEGIN;

ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS sales_strategy TEXT;

COMMIT;
