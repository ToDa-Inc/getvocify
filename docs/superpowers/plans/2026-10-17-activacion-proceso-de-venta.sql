-- Vocify · Proceso de venta editable (17 oct 2026)
-- Lo ejecuta el founder en Supabase (SQL editor), no el agente ni CI.
-- Spec: docs/superpowers/specs/2026-10-17-proceso-de-venta-editable-design.md
--
-- ORDEN (cada parte es su propio bloque; ejecútalas una a una)
--   A. Tablas (migración 084). Idempotente. Hasta que existan, la API responde 503 `not_activated` y nada más cambia.
--   B. Comprobación: debe devolver 2 filas.
--   C. Flags de UNA empresa de prueba. El proceso editable necesita tres: SALES_PROCESS_ENABLED (el proceso y los tipos
--      por miembro), INTELLIGENCE_CALL_READING_ENABLED (el tipo de cada llamada lo decide la lectura de la llamada) y
--      SALES_ROLES_ENABLED (para que el rol SDR/AE que leen coaching e informes se derive de los tipos de cada miembro).
--   D. Rellenar el proceso y los tipos de los miembros de ESA empresa desde lo que ya tiene (sus tipos creados y el rol
--      de cada miembro). Opcional y repetible: una empresa nueva no lo necesita.
-- NÚMERO: 084 (081 demo_profiles, 082 live_assist_events_brain, 083 playbook_assistant). Si alguien añade otra 084, renumerar.

-- ===================== PARTE A · tablas =====================

BEGIN;

CREATE TABLE IF NOT EXISTS company_sales_process (
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  sales_motion_key TEXT NOT NULL,
  position INTEGER NOT NULL,
  stage TEXT NOT NULL CHECK (stage IN ('first_contact', 'deal')),
  PRIMARY KEY (company_id, sales_motion_key)
);

CREATE TABLE IF NOT EXISTS member_interaction_types (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  invitation_id UUID,
  types TEXT[],
  CHECK ((user_id IS NOT NULL) <> (invitation_id IS NOT NULL)),
  UNIQUE (company_id, user_id),
  UNIQUE (company_id, invitation_id)
);

ALTER TABLE company_sales_process ENABLE ROW LEVEL SECURITY;
ALTER TABLE member_interaction_types ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['company_sales_process', 'member_interaction_types'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
      EXECUTE format('REVOKE ALL ON %I FROM anon', t);
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
      EXECUTE format('REVOKE ALL ON %I FROM authenticated', t);
    END IF;
  END LOOP;
END $$;

COMMIT;

-- ===================== PARTE A2 · objetivo de cada interacción y llamadas fuera del funnel (migración 085) =====================
-- Necesaria para la pantalla nueva de Playbook (funnel de ventas y vuestra empresa). Ejecútala justo después de la PARTE A.

BEGIN;

ALTER TABLE company_sales_process ADD COLUMN IF NOT EXISTS goal TEXT;

ALTER TABLE company_sales_process DROP CONSTRAINT IF EXISTS company_sales_process_stage_check;
ALTER TABLE company_sales_process
  ADD CONSTRAINT company_sales_process_stage_check CHECK (stage IN ('first_contact', 'deal', 'other'));

COMMIT;

-- ===================== PARTE B · comprobación (debe devolver 2 filas) =====================
-- SELECT table_name FROM information_schema.tables
--  WHERE table_schema = 'public' AND table_name IN ('company_sales_process', 'member_interaction_types');

-- ===================== PARTE C · flags de una empresa de prueba =====================
-- Sustituye <COMPANY_ID> y quita los «-- ».

-- BEGIN;
-- INSERT INTO company_feature_flags (company_id, flag, enabled) VALUES
--   ('<COMPANY_ID>', 'SALES_PROCESS_ENABLED', true),
--   ('<COMPANY_ID>', 'INTELLIGENCE_CALL_READING_ENABLED', true),
--   ('<COMPANY_ID>', 'SALES_ROLES_ENABLED', true)
-- ON CONFLICT (company_id, flag) DO UPDATE
--   SET enabled = EXCLUDED.enabled, updated_at = NOW();
-- COMMIT;

-- ===================== PARTE D · rellenar una empresa que ya usa Vocify (opcional) =====================
-- Pone en su proceso los tipos que ya tiene, en el orden del catálogo, con el objetivo que decía su rol
-- (SDR = primer contacto, AE = cierre), y da a cada SDR/AE los tipos de su objetivo. Los miembros generales quedan
-- con «todos». No toca nada que ya exista (ON CONFLICT DO NOTHING).

-- BEGIN;
-- INSERT INTO company_sales_process (company_id, sales_motion_key, position, stage)
-- SELECT p.company_id, p.sales_motion_key,
--        (row_number() OVER (PARTITION BY p.company_id ORDER BY coalesce(c.ord, 999), p.sales_motion_key))::int,
--        coalesce(c.stage, 'first_contact')
--   FROM playbooks p
--   LEFT JOIN (VALUES ('discovery', 1, 'first_contact'), ('inbound', 2, 'first_contact'),
--                     ('ae_discovery', 3, 'deal'), ('closing', 4, 'deal'), ('negotiation', 5, 'deal')) AS c(k, ord, stage)
--     ON c.k = p.sales_motion_key
--  WHERE p.company_id = '<COMPANY_ID>' AND p.archived_at IS NULL AND p.sales_motion_key NOT IN ('internal', 'qualification')
-- ON CONFLICT DO NOTHING;
--
-- INSERT INTO member_interaction_types (company_id, user_id, types)
-- SELECT m.company_id, m.user_id, array_agg(s.sales_motion_key ORDER BY s.position)
--   FROM company_members m
--   JOIN company_sales_process s ON s.company_id = m.company_id
--    AND s.stage = CASE m.sales_role WHEN 'sdr' THEN 'first_contact' WHEN 'ae' THEN 'deal' END
--  WHERE m.company_id = '<COMPANY_ID>' AND m.sales_role IN ('sdr', 'ae')
--  GROUP BY m.company_id, m.user_id
-- ON CONFLICT DO NOTHING;
-- COMMIT;

-- ===================== Marcha atrás =====================
-- Apagar SALES_PROCESS_ENABLED devuelve todo a como estaba (el rol SDR/AE sigue guardado en cada miembro).
-- Quitar las tablas (pierde el proceso y los tipos por miembro): backend/migrations/084_sales_process.down.sql
