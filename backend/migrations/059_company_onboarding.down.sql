-- Drops the company onboarding completion marker.

BEGIN;

ALTER TABLE companies
  DROP COLUMN IF EXISTS onboarding_completed_at;

COMMIT;
