-- Workspace plan on the Stripe snapshot. Seat cap stays on companies.seat_limit.
-- Also create the webhook log if 030 was skipped.

CREATE TABLE IF NOT EXISTS stripe_webhook_events (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE company_billing
  ADD COLUMN IF NOT EXISTS plan_type TEXT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'company_billing_plan_type_check'
  ) THEN
    ALTER TABLE company_billing
      ADD CONSTRAINT company_billing_plan_type_check
      CHECK (plan_type IS NULL OR plan_type IN ('starter', 'pro'));
  END IF;
END $$;
