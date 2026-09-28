-- Vocify staging · Lista 4 (flujo y dashboard del SDR, Hoy por bloques del AE y del General)
-- company_id Vocify en staging: 70b7ffd2-c360-4d4f-a339-4affec769f7a
-- No ejecutar desde CI ni desde el agente: lo ejecuta el founder en Supabase.
--
-- ORDEN:
--   1. Tener aplicada la Lista 3 (migraciones 054–061 y su SQL de activación): los bloques de
--      Hoy leen sales_role, los traspasos y callback_after_days.
--   2. Aplicar las migraciones 062 y 063 (cada una tiene su .down.sql):
--      062_sdr_followup_cadence (companies.followup_cadence, memos.followup_at, memos.rep_outcome),
--      063_deal_creation_rule (crm_configurations.deal_creation_rule, por defecto 'always').
--      El código funciona sin ellas (cae al comportamiento anterior), pero las features no se ven.
--   3. Encender los flags de abajo.
--   4. Head of Sales: revisar en Ajustes → CRM «Crear el deal en el CRM» (por defecto «siempre»,
--      lo de hoy) y en Ajustes → Oferta la «Cadencia de seguimiento» (vacía = esperas por defecto).
--
-- La navegación nueva (Preguntar y Llamar arriba, Grabaciones, Coach, Ajustes del comercial,
-- sin Copiloto) no lleva flag: ya está activa en cuanto se despliega.

BEGIN;

INSERT INTO company_feature_flags (company_id, flag, enabled) VALUES
  -- Hoy por bloques: SDR Tareas/Seguimiento/Nuevos, AE Demos/Tareas/Seguimiento, General los cuatro,
  -- con la cadencia de seguimiento por freno (T2, T8)
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'HOY_SDR_SECTIONS_ENABLED', true),
  -- Brief con gancho de empresa, dashboard y extensión (T3). Necesita BRIEF_V2_ENABLED (ya encendido en staging)
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'BRIEF_COMPANY_HOOK_ENABLED', true),
  -- Al colgar en Hoy: propuesta, resultado, regla lead→deal y follow-up (T4)
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'AFTER_CALL_FLOW_ENABLED', true)
ON CONFLICT (company_id, flag) DO UPDATE
  SET enabled = EXCLUDED.enabled, updated_at = NOW();

COMMIT;

-- Marcha atrás: poner enabled = false en los tres flags. Hoy vuelve a la lista de antes y los
-- seguimientos ya creados se ocultan; el brief y el panel al colgar vuelven a lo anterior.
