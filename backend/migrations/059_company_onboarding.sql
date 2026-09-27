-- Lista 3 (T9): the Head of Sales onboarding wizard. `onboarding_completed_at` is set once
-- POST /company/onboarding/complete runs (finished or every step skipped); NULL means the
-- wizard still shows behind ONBOARDING_WIZARD_ENABLED.
-- Rollback: 059_company_onboarding.down.sql

BEGIN;

ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS onboarding_completed_at TIMESTAMPTZ;

COMMIT;
