-- Sales process, part 2 (docs/superpowers/plans/2026-10-18-playbook-funnel-y-empresa.md):
--   goal  what each type of the funnel must achieve ("create interest and agree a meeting").
--   stage also admits 'other': a call outside the sales funnel (customer service...), never scored in coaching.
-- NUMBER: 085 (084 sales_process): if someone else adds a 085, renumber this file.
-- Rollback: 085_sales_process_goal.down.sql

BEGIN;

ALTER TABLE company_sales_process ADD COLUMN IF NOT EXISTS goal TEXT;

ALTER TABLE company_sales_process DROP CONSTRAINT IF EXISTS company_sales_process_stage_check;
ALTER TABLE company_sales_process
  ADD CONSTRAINT company_sales_process_stage_check CHECK (stage IN ('first_contact', 'deal', 'other'));

COMMIT;
