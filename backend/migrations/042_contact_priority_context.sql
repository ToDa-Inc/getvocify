-- F04: cached CRM context per company, connection and contact. deal_id '' means no deal.

CREATE TABLE IF NOT EXISTS contact_priority_context (
  company_id UUID NOT NULL,
  connection_id TEXT NOT NULL,
  contact_id TEXT NOT NULL,
  deal_id TEXT NOT NULL DEFAULT '',
  owner_user_id UUID,
  owner_ambiguous BOOLEAN NOT NULL DEFAULT false,
  coverage TEXT NOT NULL,
  history_complete BOOLEAN NOT NULL DEFAULT false,
  observed_at TIMESTAMPTZ,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (company_id, connection_id, contact_id, deal_id)
);
