-- Vocify staging · Playbooks v2 (la pantalla nueva de Proceso de venta)
-- company_id Vocify en staging: 70b7ffd2-c360-4d4f-a339-4affec769f7a
-- No ejecutar desde CI ni desde el agente: lo ejecuta el founder en Supabase (SQL editor).
--
-- ORDEN:
--   1. PARTE A (migraciones 066, 067, 068 y 069). OBLIGATORIA en cuanto se despliegue este código:
--      el editor lee playbook_versions.updated_at y .qualification: sin la 066 o la 068 no carga (ni el nuevo ni el viejo).
--      La 069 (pausar/eliminar) la leen la lista y el editor: sin ella la lista de playbooks falla.
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

-- 068_playbook_three_layers: cualificación por versión y «Vuestra empresa» (una fila por empresa).
-- Sin la 068 el editor no carga (lee playbook_versions.qualification).
ALTER TABLE playbook_versions
  ADD COLUMN IF NOT EXISTS qualification JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE IF NOT EXISTS company_sales_knowledge (
  company_id UUID PRIMARY KEY,
  data JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_id TEXT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION company_sales_knowledge_touch_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $touch$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$touch$;

DROP TRIGGER IF EXISTS company_sales_knowledge_updated_at ON company_sales_knowledge;
CREATE TRIGGER company_sales_knowledge_updated_at
  BEFORE UPDATE ON company_sales_knowledge
  FOR EACH ROW EXECUTE FUNCTION company_sales_knowledge_touch_updated_at();

-- 069_playbook_pause_archive: pausar, reanudar y eliminar (con deshacer) un tipo de llamada.
ALTER TABLE playbooks
  ADD COLUMN IF NOT EXISTS paused_version_id UUID NULL,
  ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ NULL,
  ADD COLUMN IF NOT EXISTS archived_state TEXT NULL;

CREATE OR REPLACE FUNCTION publish_playbook_version(p_version UUID)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
  pb UUID;
BEGIN
  SELECT playbook_id INTO pb FROM playbook_versions WHERE id = p_version FOR UPDATE;
  IF pb IS NULL THEN
    RAISE EXCEPTION 'playbook version not found';
  END IF;
  PERFORM 1 FROM playbooks WHERE id = pb FOR UPDATE;
  UPDATE playbook_versions SET status = 'published' WHERE id = p_version;
  UPDATE playbooks
  SET active_version_id = p_version,
      paused_version_id = NULL,
      archived_at = NULL,
      archived_state = NULL
  WHERE id = pb;
  RETURN p_version;
END;
$$;

CREATE OR REPLACE FUNCTION publish_playbook_motion(p_company UUID, p_motion TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $publish_motion$
DECLARE
  pb UUID;
  ver UUID;
BEGIN
  SELECT id INTO pb FROM playbooks
  WHERE company_id = p_company AND sales_motion_key = p_motion
  FOR UPDATE;

  IF pb IS NULL THEN
    RETURN 'not_a_draft';
  END IF;

  IF EXISTS (
    SELECT 1 FROM playbook_imports i
    WHERE i.playbook_id = pb
      AND COALESCE(jsonb_array_length(i.draft->'contradictions'), 0) > 0
      AND i.created_at = (
        SELECT max(created_at) FROM playbook_imports WHERE playbook_id = pb
      )
  ) THEN
    RETURN 'contradiction';
  END IF;

  SELECT id INTO ver FROM playbook_versions
  WHERE playbook_id = pb AND status = 'draft'
  ORDER BY created_at DESC
  LIMIT 1
  FOR UPDATE;

  IF ver IS NULL THEN
    RETURN 'not_a_draft';
  END IF;

  PERFORM publish_playbook_version(ver);
  UPDATE playbooks
  SET paused_version_id = NULL, archived_at = NULL, archived_state = NULL
  WHERE id = pb;
  RETURN 'published:' || ver::text;
END;
$publish_motion$;

CREATE OR REPLACE FUNCTION list_playbook_motions(p_company UUID)
RETURNS TABLE (sales_motion_key TEXT, motion_status TEXT)
LANGUAGE sql
STABLE
AS $list_motions$
  SELECT motion_key AS sales_motion_key, motion_status
  FROM (
    SELECT p.sales_motion_key AS motion_key,
      CASE
        WHEN p.active_version_id IS NOT NULL THEN 'published'
        WHEN p.paused_version_id IS NOT NULL THEN 'paused'
        WHEN EXISTS (
          SELECT 1 FROM playbook_versions v
          WHERE v.playbook_id = p.id AND v.status = 'draft'
        ) THEN 'draft'
        ELSE 'missing'
      END AS motion_status
    FROM playbooks p
    WHERE p.company_id = p_company
      AND p.archived_at IS NULL
    UNION
    SELECT t.type_key,
      'missing'
    FROM interaction_types t
    WHERE t.company_id = p_company
      AND t.active
      AND NOT EXISTS (
        SELECT 1 FROM playbooks p
        WHERE p.company_id = t.company_id AND p.sales_motion_key = t.type_key
      )
  ) listed;
$list_motions$;

CREATE OR REPLACE FUNCTION add_interaction_type(p_company UUID, p_key TEXT, p_name TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $add_type$
BEGIN
  IF btrim(p_key) = '' THEN
    RETURN 'empty';
  END IF;
  INSERT INTO interaction_types (company_id, type_key, name)
  VALUES (p_company, btrim(p_key), COALESCE(NULLIF(btrim(p_name), ''), btrim(p_key)))
  ON CONFLICT (company_id, type_key) DO UPDATE SET active = true;
  UPDATE playbooks
  SET archived_at = NULL, paused_version_id = NULL, archived_state = NULL
  WHERE company_id = p_company
    AND sales_motion_key = btrim(p_key)
    AND archived_at IS NOT NULL;
  RETURN btrim(p_key);
END;
$add_type$;

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
-- (en ese orden; la 069 y la 068 antes, con 069_playbook_pause_archive.down.sql y 068_playbook_three_layers.down.sql),
-- pero el código desplegado necesita la 066, la 068 y la 069.
