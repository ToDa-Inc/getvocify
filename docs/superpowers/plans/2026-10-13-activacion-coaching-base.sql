-- Vocify PRODUCCIÓN · base de coaching (13 oct 2026)
-- Lo ejecuta el founder en Supabase (SQL editor), no el agente ni CI.
-- Comprobado en solo lectura el 13 oct: en producción faltan 058, 059, 060, 062 y 063.
-- Todas solo añaden (tabla nueva o columnas que admiten vacío); ninguna borra ni reescribe datos.
-- Cada bloque es su propia transacción (BEGIN/COMMIT) y es idempotente: se puede volver a ejecutar.
--
-- PARTE A (aprobada): lo que coaching necesita.
--   060 brief_seen: el feedback marcado como visto en la campana persiste.
--   062 memos.rep_outcome (+ followup_at, companies.followup_cadence): el resultado que el comercial
--       marca tras la llamada se guarda. Sin esto "Reuniones acordadas" es 0 y no hay veredicto
--       de si el playbook funciona.
--
-- PARTE B (también faltan; ejecutar solo si Dani la da por buena):
--   058 companies.sales_strategy · 059 companies.onboarding_completed_at ·
--   061 memos_source_check admite 'recall' (no se puede comprobar si ya está; fallaría y no
--       cambiaría nada si algún memo tuviera un source fuera de la lista) ·
--   063 crm_configurations.deal_creation_rule (por defecto 'always' = comportamiento actual).
--
-- Comprobación al final: ver la consulta de verificación.

-- ===================== PARTE A =====================

-- ---- backend/migrations/060_brief_seen.sql ----
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

-- ---- backend/migrations/062_sdr_followup_cadence.sql ----
-- Lista 4 (T2, E8): follow-up cadence for the SDR's Hoy.
--   companies.followup_cadence: the Head of Sales' own waits per stopper, {stopper: days}
--     (e.g. {"price": 5, "timing": 30}). NULL = E8's defaults. The app validates keys and
--     1..90 days (app/services/hoy/cadence.py parse_overrides) and ignores anything else.
--   memos.followup_at: the date the rep picked after the call; it beats the cadence.
--   memos.rep_outcome: the outcome the rep recorded after the call. not_interested and
--     disqualified (and meeting_booked) never bring the contact back as a follow-up.
-- T2 only reads the memo columns (tolerating their absence); T4 writes them.
-- Rollback: 062_sdr_followup_cadence.down.sql

BEGIN;

ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS followup_cadence JSONB NULL;

ALTER TABLE companies
  DROP CONSTRAINT IF EXISTS companies_followup_cadence_check;

ALTER TABLE companies
  ADD CONSTRAINT companies_followup_cadence_check
  CHECK (followup_cadence IS NULL OR jsonb_typeof(followup_cadence) = 'object');

ALTER TABLE memos
  ADD COLUMN IF NOT EXISTS followup_at TIMESTAMPTZ NULL;

ALTER TABLE memos
  ADD COLUMN IF NOT EXISTS rep_outcome TEXT NULL;

ALTER TABLE memos
  DROP CONSTRAINT IF EXISTS memos_rep_outcome_check;

ALTER TABLE memos
  ADD CONSTRAINT memos_rep_outcome_check
  CHECK (rep_outcome IS NULL OR rep_outcome IN ('meeting_booked', 'follow_up', 'not_interested', 'disqualified'));

COMMIT;

-- ===================== PARTE B =====================

-- ---- backend/migrations/058_sales_strategy.sql ----
-- Lista 3 (T8/D10): the Head of Sales's sales strategy, free text. Entered on Settings ->
-- Offer, edited only by owner/admin, read as context by follow-up (D9), briefs and Ask.
-- Rollback: 058_sales_strategy.down.sql

BEGIN;

ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS sales_strategy TEXT;

COMMIT;

-- ---- backend/migrations/059_company_onboarding.sql ----
-- Lista 3 (T9): the Head of Sales onboarding wizard. `onboarding_completed_at` is set once
-- POST /company/onboarding/complete runs (finished or every step skipped); NULL means the
-- wizard still shows behind ONBOARDING_WIZARD_ENABLED.
-- Rollback: 059_company_onboarding.down.sql

BEGIN;

ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS onboarding_completed_at TIMESTAMPTZ;

COMMIT;

-- ---- backend/migrations/061_memos_source_recall.sql ----
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

-- ---- backend/migrations/063_deal_creation_rule.sql ----
-- Lista 4 (T4, E11): when Vocify creates a deal in the CRM for a contact that has none.
--   crm_configurations.deal_creation_rule, chosen by the Head of Sales in Ajustes -> CRM:
--     always               today's behaviour (default): approving a call may create the deal;
--     meeting_booked       only when the rep marks the call "Reunión agendada";
--     follow_up_or_meeting also when the rep marks it "Seguimiento";
--     never                Vocify never creates deals, it only updates the contact.
--   A deal that already exists is always updated. The backend applies the rule on approve
--   (skip_deal), not only the UI - only with AFTER_CALL_FLOW_ENABLED on for the company.
-- Rollback: 063_deal_creation_rule.down.sql

BEGIN;

ALTER TABLE crm_configurations
  ADD COLUMN IF NOT EXISTS deal_creation_rule TEXT NOT NULL DEFAULT 'always';

ALTER TABLE crm_configurations
  DROP CONSTRAINT IF EXISTS crm_configurations_deal_creation_rule_check;

ALTER TABLE crm_configurations
  ADD CONSTRAINT crm_configurations_deal_creation_rule_check
  CHECK (deal_creation_rule IN ('always', 'meeting_booked', 'follow_up_or_meeting', 'never'));

COMMIT;

-- ===================== VERIFICACIÓN =====================
SELECT
  to_regclass('public.brief_seen') IS NOT NULL AS brief_seen,
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'memos' AND column_name = 'rep_outcome') AS memos_rep_outcome,
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'sales_strategy') AS sales_strategy,
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'crm_configurations' AND column_name = 'deal_creation_rule') AS deal_creation_rule;
