BEGIN;

ALTER TABLE company_members
  DROP CONSTRAINT IF EXISTS company_members_sales_role_check;

ALTER TABLE company_members
  DROP COLUMN IF EXISTS sales_role;

ALTER TABLE company_invitations
  DROP CONSTRAINT IF EXISTS company_invitations_sales_role_check;

ALTER TABLE company_invitations
  DROP COLUMN IF EXISTS sales_role;

COMMIT;
