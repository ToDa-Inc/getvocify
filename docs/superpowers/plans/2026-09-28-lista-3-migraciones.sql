-- Vocify · Lista 3 · migraciones 054–061 en orden (pegar en el SQL editor de Supabase)
-- Después: ejecutar 2026-09-27-activacion-lista-3.sql

-- ===================== 054_sales_roles.sql =====================
-- Lista 3 (T1): commercial type per member (SDR/AE/General), SDR→AE routing, and
-- per-member activity visibility. NULL sales_role behaves as "general" (today's
-- behavior). visibility defaults to "own" (today's behavior); "team" additionally
-- grants read of the team's activity, with no management permissions.
-- Rollback: 054_sales_roles.down.sql

BEGIN;

ALTER TABLE company_members
  ADD COLUMN IF NOT EXISTS sales_role TEXT,
  ADD COLUMN IF NOT EXISTS handoff_ae_user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'own';

ALTER TABLE company_members
  DROP CONSTRAINT IF EXISTS company_members_sales_role_check;

ALTER TABLE company_members
  ADD CONSTRAINT company_members_sales_role_check
  CHECK (sales_role IS NULL OR sales_role IN ('sdr', 'ae', 'general'));

ALTER TABLE company_members
  DROP CONSTRAINT IF EXISTS company_members_visibility_check;

ALTER TABLE company_members
  ADD CONSTRAINT company_members_visibility_check
  CHECK (visibility IN ('own', 'team'));

-- A SDR cannot route their own handoffs to themselves.
ALTER TABLE company_members
  DROP CONSTRAINT IF EXISTS company_members_handoff_not_self_check;

ALTER TABLE company_members
  ADD CONSTRAINT company_members_handoff_not_self_check
  CHECK (handoff_ae_user_id IS NULL OR handoff_ae_user_id <> user_id);

CREATE INDEX IF NOT EXISTS idx_company_members_handoff_ae
  ON company_members (handoff_ae_user_id);

-- The sales role chosen at invite time, copied to company_members on acceptance.
ALTER TABLE company_invitations
  ADD COLUMN IF NOT EXISTS sales_role TEXT;

ALTER TABLE company_invitations
  DROP CONSTRAINT IF EXISTS company_invitations_sales_role_check;

ALTER TABLE company_invitations
  ADD CONSTRAINT company_invitations_sales_role_check
  CHECK (sales_role IS NULL OR sales_role IN ('sdr', 'ae', 'general'));

COMMIT;

-- ===================== 055_playbook_goal.sql =====================
-- Lista 3 (T2): the playbook's business objective. Discovery aims at a booked meeting,
-- closing aims at a proposal and close (D4). Not written by the app yet — the app computes
-- the default from sales_motion_key — but reserved for a future per-company override.
-- Rollback: 055_playbook_goal.down.sql

BEGIN;

ALTER TABLE playbooks
  ADD COLUMN IF NOT EXISTS goal TEXT;

COMMIT;

-- ===================== 056_deal_handoffs.sql =====================
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

-- ===================== 057_callback_after_days.sql =====================
-- Lista 3 (T5): how many days after an unanswered call attempt (no_response/voicemail on
-- the screening outcome) Hoy surfaces a "callback_no_answer" card. Default 2, per company.
-- Rollback: 057_callback_after_days.down.sql

BEGIN;

ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS callback_after_days INTEGER NOT NULL DEFAULT 2;

ALTER TABLE companies
  DROP CONSTRAINT IF EXISTS companies_callback_after_days_check;

ALTER TABLE companies
  ADD CONSTRAINT companies_callback_after_days_check
  CHECK (callback_after_days > 0);

COMMIT;

-- ===================== 058_sales_strategy.sql =====================
-- Lista 3 (T8/D10): the Head of Sales's sales strategy, free text. Entered on Settings ->
-- Offer, edited only by owner/admin, read as context by follow-up (D9), briefs and Ask.
-- Rollback: 058_sales_strategy.down.sql

BEGIN;

ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS sales_strategy TEXT;

COMMIT;

-- ===================== 059_company_onboarding.sql =====================
-- Lista 3 (T9): the Head of Sales onboarding wizard. `onboarding_completed_at` is set once
-- POST /company/onboarding/complete runs (finished or every step skipped); NULL means the
-- wizard still shows behind ONBOARDING_WIZARD_ENABLED.
-- Rollback: 059_company_onboarding.down.sql

BEGIN;

ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS onboarding_completed_at TIMESTAMPTZ;

COMMIT;

-- ===================== 060_brief_seen.sql =====================
-- Lista 3 (T12): which post-interaction briefs a rep has already seen in the bell's
-- "Feedback" section. One row per (user_id, memo_id); marking one seen again is a no-op.
-- Rollback: 060_brief_seen.down.sql

BEGIN;

CREATE TABLE IF NOT EXISTS brief_seen (
  user_id UUID NOT NULL,
  memo_id UUID NOT NULL,
  seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, memo_id)
);

ALTER TABLE brief_seen ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    REVOKE ALL ON brief_seen FROM anon;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON brief_seen FROM authenticated;
  END IF;
END $$;

COMMIT;

-- ===================== 061_memos_source_recall.sql =====================
-- T14: Recall.ai meeting bot writes memos.source = 'recall'. Extends
-- memos_source_check (last defined in 037_memo_capture_context.sql) with that value;
-- every value allowed since then stays valid, so existing rows are not rejected.
-- Until this runs, app.services.captures.reserve_capture retries a 23514 check
-- violation with source='web' instead of failing the reservation (see
-- app/services/meetings/recall_bot.py).

BEGIN;

ALTER TABLE memos DROP CONSTRAINT IF EXISTS memos_source_check;
ALTER TABLE memos ADD CONSTRAINT memos_source_check
  CHECK (source IN (
    'web', 'voice_memo', 'whatsapp', 'unipile', 'hubspot_call', 'vocify_call', 'desktop', 'recall'
  ));

COMMIT;
