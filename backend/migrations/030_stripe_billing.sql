-- Stripe seat billing on company workspaces.

ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT,
  ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT,
  ADD COLUMN IF NOT EXISTS billing_status TEXT NOT NULL DEFAULT 'none',
  ADD COLUMN IF NOT EXISTS billing_interval TEXT,
  ADD COLUMN IF NOT EXISTS access_mode TEXT NOT NULL DEFAULT 'open';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'companies_billing_status_check'
  ) THEN
    ALTER TABLE companies
      ADD CONSTRAINT companies_billing_status_check
      CHECK (billing_status IN (
        'none', 'active', 'trialing', 'past_due', 'canceled', 'unpaid', 'incomplete'
      ));
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'companies_billing_interval_check'
  ) THEN
    ALTER TABLE companies
      ADD CONSTRAINT companies_billing_interval_check
      CHECK (billing_interval IS NULL OR billing_interval IN ('monthly', 'yearly'));
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'companies_access_mode_check'
  ) THEN
    ALTER TABLE companies
      ADD CONSTRAINT companies_access_mode_check
      CHECK (access_mode IN ('open', 'paywalled', 'unlocked'));
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_companies_stripe_customer
  ON companies (stripe_customer_id)
  WHERE stripe_customer_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS stripe_webhook_events (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
