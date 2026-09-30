-- Vocify staging · Playbooks v2 (la pantalla nueva de Proceso de venta)
-- company_id Vocify en staging: 70b7ffd2-c360-4d4f-a339-4affec769f7a
-- No ejecutar desde CI ni desde el agente: lo ejecuta el founder en Supabase (SQL editor).
--
-- ORDEN:
--   1. PARTE A (una sola migración): ejecutar EN ORDEN, en el editor SQL de Supabase, el archivo
--      backend/migrations/066_playbooks_v2.sql. Sustituye a las antiguas 066, 067, 068 y 069; es idempotente y segura
--      aunque esas ya se hubieran aplicado (pasa lo pausado y lo eliminado al esquema nuevo y borra las columnas viejas).
--      OBLIGATORIA en cuanto se despliegue este código: el editor y la lista leen sus columnas y funciones.
--      Se deshace con backend/migrations/066_playbooks_v2.down.sql (deshacer el despliegue antes).
--   2. Desplegar staging.
--   3. La pantalla nueva no lleva flag: sale para todos en cuanto se despliega
--      (Proceso de venta para el Head of Sales, pestaña Playbook para el comercial).
--   4. PARTE B (opcional): el enrutado por regla. Solo cuando haya dos playbooks publicados de un
--      mismo rol (p. ej. Llamada en frío e Inbound para SDR). Sin él, SDR → Llamada en frío y
--      AE → Demo y cierre, como hoy.
--   5. Para ver el % por paso hace falta PLAYBOOK_OBSERVATIONS_ENABLED (Lista 3), después de correr
--      las evals de intelligence_v4.

-- ─── PARTE A · migración ────────────────────────────────────────────────────────────────
-- Pegar y ejecutar el contenido de backend/migrations/066_playbooks_v2.sql (no hay nada más que copiar aquí).

-- ─── PARTE B · flags (opcional) ───────────────────────────────────────────────────────────

-- BEGIN;
-- INSERT INTO company_feature_flags (company_id, flag, enabled) VALUES
--   -- Catálogo de tipos de llamada, «Se aplica a», enrutado por regla y «Evaluada como · cambiar»
--   ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'PLAYBOOK_ROUTING_ENABLED', true)
-- ON CONFLICT (company_id, flag) DO UPDATE
--   SET enabled = EXCLUDED.enabled, updated_at = NOW();
-- COMMIT;

-- Marcha atrás: PLAYBOOK_ROUTING_ENABLED = false vuelve al enrutado por rol. La migración se deshace con
-- backend/migrations/066_playbooks_v2.down.sql (un playbook pausado vuelve a estar activo), pero el código
-- desplegado necesita la 066_playbooks_v2.
