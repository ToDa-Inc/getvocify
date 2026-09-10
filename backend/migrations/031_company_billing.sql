-- Company-level Stripe snapshot. Workspace policy stays on companies
-- (access_mode, seat_limit). Stripe ids and subscription state live here.

ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS access_mode TEXT NOT NULL DEFAULT 'open';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'companies_access_mode_check'
  ) THEN
    ALTER TABLE companies
      ADD CONSTRAINT companies_access_mode_check
      CHECK (access_mode IN ('open', 'paywalled', 'unlocked'));
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS company_billing (
  company_id UUID PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
  stripe_customer_id TEXT,
  stripe_subscription_id TEXT,
  billing_status TEXT NOT NULL DEFAULT 'none',
  billing_interval TEXT,
  quantity INT,
  current_period_end TIMESTAMPTZ,
  cancel_at_period_end BOOLEAN NOT NULL DEFAULT false,
  past_due_since TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT company_billing_status_check CHECK (billing_status IN (
    'none', 'active', 'trialing', 'past_due', 'canceled', 'unpaid', 'incomplete'
  )),
  CONSTRAINT company_billing_interval_check CHECK (
    billing_interval IS NULL OR billing_interval IN ('monthly', 'yearly')
  ),
  CONSTRAINT company_billing_quantity_check CHECK (quantity IS NULL OR quantity >= 1)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_billing_customer
  ON company_billing (stripe_customer_id)
  WHERE stripe_customer_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_billing_subscription
  ON company_billing (stripe_subscription_id)
  WHERE stripe_subscription_id IS NOT NULL;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'companies'
      AND column_name = 'stripe_customer_id'
  ) THEN
    INSERT INTO company_billing (
      company_id,
      stripe_customer_id,
      stripe_subscription_id,
      billing_status,
      billing_interval
    )
    SELECT
      id,
      NULLIF(stripe_customer_id, ''),
      NULLIF(stripe_subscription_id, ''),
      COALESCE(NULLIF(billing_status, ''), 'none'),
      billing_interval
    FROM companies
    WHERE stripe_customer_id IS NOT NULL
       OR stripe_subscription_id IS NOT NULL
       OR COALESCE(billing_status, 'none') <> 'none'
    ON CONFLICT (company_id) DO NOTHING;

    ALTER TABLE companies DROP CONSTRAINT IF EXISTS companies_billing_status_check;
    ALTER TABLE companies DROP CONSTRAINT IF EXISTS companies_billing_interval_check;
    DROP INDEX IF EXISTS idx_companies_stripe_customer;
    ALTER TABLE companies DROP COLUMN IF EXISTS stripe_customer_id;
    ALTER TABLE companies DROP COLUMN IF EXISTS stripe_subscription_id;
    ALTER TABLE companies DROP COLUMN IF EXISTS billing_status;
    ALTER TABLE companies DROP COLUMN IF EXISTS billing_interval;
  END IF;
END $$;
