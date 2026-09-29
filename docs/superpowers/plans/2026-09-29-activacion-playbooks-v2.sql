-- Vocify staging · Playbooks v2 (la pantalla nueva de Proceso de venta)
-- company_id Vocify en staging: 70b7ffd2-c360-4d4f-a339-4affec769f7a
-- No ejecutar desde CI ni desde el agente: lo ejecuta el founder en Supabase (SQL editor).
--
-- ORDEN:
--   1. PARTE A (migraciones 066 y 067). OBLIGATORIA en cuanto se despliegue este código:
--      el editor lee playbook_versions.updated_at y sin la 066 no carga (ni el nuevo ni el viejo).
--      Cada migración tiene su .down.sql en backend/migrations/.
--   2. Desplegar staging.
--   3. La pantalla nueva no lleva flag: sale para todos en cuanto se despliega
--      (Proceso de venta para el Head of Sales, pestaña Playbook para el comercial).
--   4. PARTE B (opcional): el enrutado por regla. Solo cuando haya dos playbooks publicados de un
--      mismo rol (p. ej. Llamada en frío e Inbound para SDR). Sin él, SDR → Llamada en frío y
--      AE → Demo y cierre, como hoy.
--   5. Para ver el % por paso hace falta PLAYBOOK_OBSERVATIONS_ENABLED (Lista 3), después de correr
--      las evals de intelligence_v4.

-- ─── PARTE A · migraciones ────────────────────────────────────────────────────────────────

BEGIN;

-- 066_playbook_draft_autosave: el borrador se guarda en la misma fila y se detecta si otra
-- persona lo cambió (409 stale_draft).
ALTER TABLE playbook_versions
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

UPDATE playbook_versions SET updated_at = created_at;

CREATE OR REPLACE FUNCTION playbook_versions_touch_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $touch$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$touch$;

DROP TRIGGER IF EXISTS playbook_versions_updated_at ON playbook_versions;
CREATE TRIGGER playbook_versions_updated_at
  BEFORE UPDATE ON playbook_versions
  FOR EACH ROW EXECUTE FUNCTION playbook_versions_touch_updated_at();

-- 067_playbook_rules: nombre del tipo de llamada y la regla de a qué llamadas se aplica.
ALTER TABLE playbooks
  ADD COLUMN IF NOT EXISTS label TEXT,
  ADD COLUMN IF NOT EXISTS applies_to JSONB;

COMMIT;

-- ─── PARTE B · flags (opcional) ───────────────────────────────────────────────────────────

-- BEGIN;
-- INSERT INTO company_feature_flags (company_id, flag, enabled) VALUES
--   -- Catálogo de tipos de llamada, «Se aplica a», enrutado por regla y «Evaluada como · cambiar»
--   ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'PLAYBOOK_ROUTING_ENABLED', true)
-- ON CONFLICT (company_id, flag) DO UPDATE
--   SET enabled = EXCLUDED.enabled, updated_at = NOW();
-- COMMIT;

-- Marcha atrás: PLAYBOOK_ROUTING_ENABLED = false vuelve al enrutado por rol. Las migraciones se
-- deshacen con backend/migrations/067_playbook_rules.down.sql y 066_playbook_draft_autosave.down.sql
-- (en ese orden), pero el código desplegado necesita la 066.
