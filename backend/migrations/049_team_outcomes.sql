-- F15: one observation per company, connection, deal and time seen. History is appended, not rewritten.

CREATE TABLE IF NOT EXISTS team_outcome_observations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL,
  connection_id TEXT NOT NULL,
  deal_id TEXT NOT NULL,
  status TEXT NOT NULL,
  owner_user_id UUID,
  attribution TEXT NOT NULL,
  amount NUMERIC,
  currency TEXT,
  closed_at TIMESTAMPTZ,
  observed_at TIMESTAMPTZ NOT NULL,
  UNIQUE (company_id, connection_id, deal_id, observed_at)
);
