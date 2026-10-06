-- F17: sales roles (sdr / ae / general) on members and invitations.
-- Rollback: 055_sales_roles.down.sql

BEGIN;

ALTER TABLE company_members
  ADD COLUMN IF NOT EXISTS sales_role TEXT NOT NULL DEFAULT 'general';

ALTER TABLE company_members
  DROP CONSTRAINT IF EXISTS company_members_sales_role_check;

ALTER TABLE company_members
  ADD CONSTRAINT company_members_sales_role_check
  CHECK (sales_role IN ('sdr', 'ae', 'general'));

ALTER TABLE company_invitations
  ADD COLUMN IF NOT EXISTS sales_role TEXT NOT NULL DEFAULT 'general';

ALTER TABLE company_invitations
  DROP CONSTRAINT IF EXISTS company_invitations_sales_role_check;

ALTER TABLE company_invitations
  ADD CONSTRAINT company_invitations_sales_role_check
  CHECK (sales_role IN ('sdr', 'ae', 'general'));

COMMIT;
