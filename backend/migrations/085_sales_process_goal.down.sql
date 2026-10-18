-- Rollback of 085_sales_process_goal.sql: loses the goals and turns 'other' calls into first-contact ones.
BEGIN;
UPDATE company_sales_process SET stage = 'first_contact' WHERE stage = 'other';
ALTER TABLE company_sales_process DROP CONSTRAINT IF EXISTS company_sales_process_stage_check;
ALTER TABLE company_sales_process
  ADD CONSTRAINT company_sales_process_stage_check CHECK (stage IN ('first_contact', 'deal'));
ALTER TABLE company_sales_process DROP COLUMN IF EXISTS goal;
COMMIT;
