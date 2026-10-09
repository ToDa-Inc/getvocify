-- F05: one Hoy signal per company, user, connection and dedupe key.
-- Action metadata is reserved for F06 undo. A daily run is one row per company and local date.

CREATE TABLE IF NOT EXISTS action_signals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL,
  user_id UUID NOT NULL,
  connection_id TEXT NOT NULL DEFAULT '',
  contact_id TEXT,
  deal_id TEXT,
  memo_id TEXT,
  type TEXT NOT NULL,
  dedupe_key TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL CHECK (status IN ('pending', 'done', 'dismissed', 'snoozed', 'resolved')),
  version INTEGER NOT NULL DEFAULT 1,
  snoozed_until TIMESTAMPTZ,
  previous_status TEXT,
  last_action_request_id TEXT,
  last_action_at TIMESTAMPTZ,
  undo_deadline TIMESTAMPTZ,
  coverage TEXT NOT NULL DEFAULT 'complete',
  observed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (company_id, user_id, connection_id, dedupe_key)
);

CREATE TABLE IF NOT EXISTS hoy_daily_runs (
  company_id UUID NOT NULL,
  local_date DATE NOT NULL,
  status TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (company_id, local_date)
);
