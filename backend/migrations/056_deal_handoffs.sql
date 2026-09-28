-- Lista 3 (T3): SDR->AE handoff (D6/D7). One row per active handoff, created when the SDR
-- marks "Reunión agendada" or accepts a meeting proposal (F14) with HANDOFF_ENABLED. While the
-- row is active, the contact leaves the SDR's Hoy and enters the AE's. crm_owner_status records
-- whether the CRM owner change (behind HANDOFF_CRM_OWNER_ENABLED) landed.
-- Rollback: 056_deal_handoffs.down.sql

BEGIN;

CREATE TABLE IF NOT EXISTS deal_handoffs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  connection_id TEXT NOT NULL,
  contact_id TEXT NOT NULL,
  deal_id TEXT,
  sdr_user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  ae_user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  source_memo_id UUID,
  meeting_starts_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'active',
  crm_owner_status TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  closed_at TIMESTAMPTZ
);

ALTER TABLE deal_handoffs
  DROP CONSTRAINT IF EXISTS deal_handoffs_status_check;

ALTER TABLE deal_handoffs
  ADD CONSTRAINT deal_handoffs_status_check
  CHECK (status IN ('active', 'closed', 'cancelled'));

ALTER TABLE deal_handoffs
  DROP CONSTRAINT IF EXISTS deal_handoffs_crm_owner_status_check;

ALTER TABLE deal_handoffs
  ADD CONSTRAINT deal_handoffs_crm_owner_status_check
  CHECK (crm_owner_status IS NULL OR crm_owner_status IN ('done', 'skipped', 'unmapped', 'failed'));

-- One active handoff per contact per connection (D6). A closed/cancelled row does not block a new one.
CREATE UNIQUE INDEX IF NOT EXISTS idx_deal_handoffs_active_unique
  ON deal_handoffs (company_id, connection_id, contact_id)
  WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_deal_handoffs_ae ON deal_handoffs (company_id, ae_user_id, status);
CREATE INDEX IF NOT EXISTS idx_deal_handoffs_sdr ON deal_handoffs (company_id, sdr_user_id, status);

ALTER TABLE deal_handoffs ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    REVOKE ALL ON deal_handoffs FROM anon;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON deal_handoffs FROM authenticated;
  END IF;
END $$;

COMMIT;
