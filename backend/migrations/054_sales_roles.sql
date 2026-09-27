-- Lista 3 (T1): commercial type per member (SDR/AE/General), SDR→AE routing, and
-- per-member activity visibility. NULL sales_role behaves as "general" (today's
-- behavior). visibility defaults to "own" (today's behavior); "team" additionally
-- grants read of the team's activity, with no management permissions.
-- Rollback: 054_sales_roles.down.sql

BEGIN;

ALTER TABLE company_members
  ADD COLUMN IF NOT EXISTS sales_role TEXT,
  ADD COLUMN IF NOT EXISTS handoff_ae_user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'own';

ALTER TABLE company_members
  DROP CONSTRAINT IF EXISTS company_members_sales_role_check;

ALTER TABLE company_members
  ADD CONSTRAINT company_members_sales_role_check
  CHECK (sales_role IS NULL OR sales_role IN ('sdr', 'ae', 'general'));

ALTER TABLE company_members
  DROP CONSTRAINT IF EXISTS company_members_visibility_check;

ALTER TABLE company_members
  ADD CONSTRAINT company_members_visibility_check
  CHECK (visibility IN ('own', 'team'));

-- A SDR cannot route their own handoffs to themselves.
ALTER TABLE company_members
  DROP CONSTRAINT IF EXISTS company_members_handoff_not_self_check;

ALTER TABLE company_members
  ADD CONSTRAINT company_members_handoff_not_self_check
  CHECK (handoff_ae_user_id IS NULL OR handoff_ae_user_id <> user_id);

CREATE INDEX IF NOT EXISTS idx_company_members_handoff_ae
  ON company_members (handoff_ae_user_id);

-- The sales role chosen at invite time, copied to company_members on acceptance.
ALTER TABLE company_invitations
  ADD COLUMN IF NOT EXISTS sales_role TEXT;

ALTER TABLE company_invitations
  DROP CONSTRAINT IF EXISTS company_invitations_sales_role_check;

ALTER TABLE company_invitations
  ADD CONSTRAINT company_invitations_sales_role_check
  CHECK (sales_role IS NULL OR sales_role IN ('sdr', 'ae', 'general'));

COMMIT;
