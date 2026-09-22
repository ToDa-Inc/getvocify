-- F13: one report per recipient, scope and period. Delivery retries share one idempotency key.

CREATE TABLE IF NOT EXISTS reports (
  id TEXT NOT NULL,
  company_id UUID NOT NULL,
  user_id UUID NOT NULL,
  scope TEXT NOT NULL,
  period_start TIMESTAMPTZ NOT NULL,
  report_type TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  snapshot JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (id),
  UNIQUE (company_id, user_id, scope, period_start, report_type)
);

CREATE TABLE IF NOT EXISTS report_deliveries (
  idempotency_key TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  channel TEXT NOT NULL,
  delivery_status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_attempt_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS report_notifications (
  id TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  user_id UUID NOT NULL,
  read_at TIMESTAMPTZ
);
