-- Migration 037: sales position per member + team metric settings
--
-- Feature: Head of Sales dashboard (docs/features/HEAD_OF_SALES_DASHBOARD_PLAN.md, phase H0).
--
-- company_members.role stays what it is (permissions: owner/admin/member).
-- sales_role is the job the person does (SDR / AE / manager / other) and is what
-- the team dashboard groups and compares by: an SDR is never compared with an AE.
-- started_on lets the dashboard avoid judging a two-week hire against the median.
--
-- companies.sales_settings holds workspace-wide metric thresholds, e.g.
-- {"useful_call_seconds": 60}. Missing keys fall back to defaults in
-- backend/app/services/team_metrics.py.
--
-- Idempotent and additive: nothing dropped or renamed, no data touched.
-- Apply before deploying the code that reads these columns (the API falls back
-- to the old member shape while the columns are missing, but cannot save them).

BEGIN;

ALTER TABLE company_members
  ADD COLUMN IF NOT EXISTS sales_role TEXT NOT NULL DEFAULT 'other';

ALTER TABLE company_members
  DROP CONSTRAINT IF EXISTS company_members_sales_role_check;

ALTER TABLE company_members
  ADD CONSTRAINT company_members_sales_role_check
  CHECK (sales_role IN ('sdr', 'ae', 'manager', 'other'));

ALTER TABLE company_members
  ADD COLUMN IF NOT EXISTS started_on DATE;

ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS sales_settings JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMIT;
