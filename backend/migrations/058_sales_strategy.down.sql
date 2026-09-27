-- Drops the company sales strategy column.

BEGIN;

ALTER TABLE companies
  DROP COLUMN IF EXISTS sales_strategy;

COMMIT;
