-- Vocify · Playbook: volcado y perfeccionamiento (16 oct 2026)
-- Lo ejecuta el founder en Supabase (SQL editor), no el agente ni CI. El agente no tiene acceso de DDL.
-- Lo que activa: el asistente del Playbook para owner/admin (preguntas guiadas «Lo que falta», varios documentos a la vez,
-- llamada modelo, «La prueba» y «Mejoras con el uso»). No toca el live coach, ni coaching, ni el CRM.
--
-- ORDEN
--   1. PARTE A: las 3 tablas (migración 083). Idempotente (IF NOT EXISTS): se puede volver a ejecutar.
--      Hasta que existan, la API responde 503 `not_activated` y la pantalla dice «se está activando». Nada falla.
--   2. Comprobar con la consulta de verificación (devuelve las 3 tablas).
--   3. PARTE B: encender PLAYBOOK_ASSISTANT_ENABLED para UNA empresa de prueba. Sin este flag nadie ve nada (404).
--   4. PARTE C: PLAYBOOK_SUCCESS_RATE_ENABLED (success rate y cola de mejoras) SOLO tras la comprobación de viabilidad:
--      backend/evals/outcomes/README.md (hoja de 20 sugerencias etiquetadas a mano: sigue si ≥80% de acuerdo y ≤30% «no se sabe»).
--      Sin este flag el asistente funciona entero; «Mejoras con el uso» solo muestra la cobertura.
--      OJO: una sugerencia solo se puede ligar a su llamada si el evento lleva `capture_id`. Hasta el commit a0ce79dd de Dani
--      (16 oct) ninguno de los 2.804 eventos lo tenía: la hoja saldrá vacía hasta que salga la app de escritorio que envía
--      `call_id` y haya llamadas nuevas con ayuda en directo.
--
-- NÚMERO: esta migración es la 083 (081 es demo_profiles y 082 live_assist_events_brain). Si alguien añade otra 083, renumerar ESTE fichero.
-- Hay que acordarlo con Dani: sus migraciones y las de coaching comparten la carpeta.
--
-- Después de la PARTE C, los veredictos se calculan por lotes (nunca al terminar una llamada): el botón «Actualizar» de la
-- pantalla Mejoras, o  cd backend && .venv/bin/python scripts/refresh_playbook_outcomes.py --company <id> --batches 5

-- ===================== PARTE A · tablas (backend/migrations/083_playbook_assistant.sql) =====================

-- Playbook assistant (docs/superpowers/specs/2026-10-16-playbook-volcado-y-perfeccionamiento-design.md).
-- Three small tables for the Head of Sales' side of the playbook:
--   playbook_assistant_sessions  where the guided questions ("Lo que falta") and the trial left off, so both can be resumed.
--   playbook_review_moments      the improvement queue: real cases copied from the live-help log (which is purged at
--                                90 days) so they survive until the Head of Sales has looked at them.
--   playbook_suggestion_outcomes one verdict per live-help card: did the rep say it, did it settle the objection or doubt.
-- Service role only (the app talks to them from the backend). The app does nothing until these tables exist.
-- A model call's transcript is never stored: it is read, proposals are made, and only what the Head of Sales accepts is kept (in the playbook).
-- NUMBER: 083. 081 is 081_demo_profiles and 082 is 082_live_assist_events_brain: if someone else adds a 083 meanwhile, renumber this file.
-- Rollback: 083_playbook_assistant.down.sql

BEGIN;

CREATE TABLE IF NOT EXISTS playbook_assistant_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('gaps', 'trial')),
  state JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_playbook_assistant_sessions_open
  ON playbook_assistant_sessions (company_id, kind, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS playbook_review_moments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  source TEXT NOT NULL CHECK (source IN ('trial', 'real')),
  sales_motion_key TEXT,
  entry_id TEXT,
  objection_type TEXT,
  client_text TEXT NOT NULL,
  suggestion_text TEXT,
  rep_text TEXT,
  outcome JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'kept', 'corrected', 'dismissed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_playbook_review_moments_open ON playbook_review_moments (company_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS playbook_suggestion_outcomes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  -- The live-help event (live_assist_events.id). No foreign key: that log is purged at 90 days, the verdict is not.
  event_id UUID NOT NULL UNIQUE,
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  observed_at TIMESTAMPTZ NOT NULL,
  capture_id TEXT,
  sales_motion_key TEXT,
  entry_id TEXT,
  source_id TEXT,
  objection_type TEXT,
  used TEXT NOT NULL DEFAULT 'unknown' CHECK (used IN ('used', 'adapted', 'not_used', 'unknown')),
  resolved TEXT NOT NULL DEFAULT 'unknown' CHECK (resolved IN ('resolved', 'not_resolved', 'unknown')),
  resolved_by TEXT CHECK (resolved_by IN ('extraction', 'judge', 'admin')),
  client_text TEXT,
  suggestion_text TEXT,
  rep_text TEXT,
  judged_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_playbook_suggestion_outcomes_window ON playbook_suggestion_outcomes (company_id, observed_at DESC);

ALTER TABLE playbook_assistant_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE playbook_review_moments ENABLE ROW LEVEL SECURITY;
ALTER TABLE playbook_suggestion_outcomes ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'playbook_assistant_sessions', 'playbook_review_moments', 'playbook_suggestion_outcomes'
  ] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
      EXECUTE format('REVOKE ALL ON %I FROM anon', t);
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
      EXECUTE format('REVOKE ALL ON %I FROM authenticated', t);
    END IF;
  END LOOP;
END $$;

COMMIT;

-- ---- Comprobación (debe devolver 3 filas) ----
-- SELECT table_name FROM information_schema.tables
--  WHERE table_schema = 'public'
--    AND table_name IN ('playbook_assistant_sessions', 'playbook_review_moments', 'playbook_suggestion_outcomes');

-- ===================== PARTE B · encender el asistente para una empresa de prueba =====================
-- Sustituye <COMPANY_ID> por la empresa de prueba y quita los «-- ». Solo owner/admin ven la sección.

-- BEGIN;
-- INSERT INTO company_feature_flags (company_id, flag, enabled) VALUES
--   ('<COMPANY_ID>', 'PLAYBOOK_ASSISTANT_ENABLED', true)
-- ON CONFLICT (company_id, flag) DO UPDATE
--   SET enabled = EXCLUDED.enabled, updated_at = NOW();
-- COMMIT;

-- ===================== PARTE C · success rate y cola de mejoras (NO ejecutar todavía) =====================
-- Solo cuando la comprobación de viabilidad dé «SIGUE».

-- BEGIN;
-- INSERT INTO company_feature_flags (company_id, flag, enabled) VALUES
--   ('<COMPANY_ID>', 'PLAYBOOK_SUCCESS_RATE_ENABLED', true)
-- ON CONFLICT (company_id, flag) DO UPDATE
--   SET enabled = EXCLUDED.enabled, updated_at = NOW();
-- COMMIT;

-- ===================== Marcha atrás =====================
-- Apagar: PLAYBOOK_ASSISTANT_ENABLED = false (y PLAYBOOK_SUCCESS_RATE_ENABLED = false) devuelve el Playbook a como estaba.
-- Lo que el asistente guardó en borradores o publicó sigue en el playbook, como cualquier edición.
-- Quitar las tablas (pierde sesiones, cola y veredictos): backend/migrations/083_playbook_assistant.down.sql
