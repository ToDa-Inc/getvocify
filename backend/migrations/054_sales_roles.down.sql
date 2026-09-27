-- Drops the commercial type, SDR->AE routing and visibility columns added in
-- 054_sales_roles.sql.

BEGIN;

ALTER TABLE company_invitations
  DROP CONSTRAINT IF EXISTS company_invitations_sales_role_check;
ALTER TABLE company_invitations
  DROP COLUMN IF EXISTS sales_role;

DROP INDEX IF EXISTS idx_company_members_handoff_ae;

ALTER TABLE company_members
  DROP CONSTRAINT IF EXISTS company_members_handoff_not_self_check;
ALTER TABLE company_members
  DROP CONSTRAINT IF EXISTS company_members_visibility_check;
ALTER TABLE company_members
  DROP CONSTRAINT IF EXISTS company_members_sales_role_check;

ALTER TABLE company_members
  DROP COLUMN IF EXISTS visibility,
  DROP COLUMN IF EXISTS handoff_ae_user_id,
  DROP COLUMN IF EXISTS sales_role;

COMMIT;
