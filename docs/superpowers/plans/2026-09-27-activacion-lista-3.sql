-- Vocify staging · Lista 3 (roles SDR/AE/General, traspaso, Head of Sales)
-- company_id Vocify en staging: 70b7ffd2-c360-4d4f-a339-4affec769f7a
-- No ejecutar desde CI ni desde el agente: lo ejecuta el founder en Supabase.
--
-- ORDEN:
--   1. Aplicar las migraciones 054–061 (cada una tiene su .down.sql):
--      054_sales_roles, 055_playbook_goal, 056_deal_handoffs, 057_callback_after_days,
--      058_sales_strategy, 059_company_onboarding, 060_brief_seen, 061_memos_source_recall.
--      El código funciona sin ellas (cae al comportamiento anterior), pero las features no se ven.
--   2. Asignar tipo a cada comercial en Ajustes → Equipo (SDR / AE / General) y el AE de cada SDR.
--   3. Encender los flags de abajo.

BEGIN;

INSERT INTO company_feature_flags (company_id, flag, enabled) VALUES
  -- Roles, reparto y traspaso (T1–T4)
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'SALES_ROLES_ENABLED', true),
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'HANDOFF_ENABLED', true),
  -- Hoy por rol (T5, T6)
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'HOY_LEAD_TIERS_ENABLED', true),
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'HOY_AE_DEALS_ENABLED', true),
  -- Follow-up por flujo y estrategia de ventas (T8)
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'FOLLOWUP_BY_FLOW_ENABLED', true),
  -- Onboarding del Head of Sales (T9)
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'ONBOARDING_WIZARD_ENABLED', true),
  -- Coaching (T10, T11)
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'SCORING_OBJECTION_CREDIT_ENABLED', true),
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'DEBRIEF_V2_ENABLED', true),
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'PLAYBOOK_TAB_ENABLED', true),
  -- Informes y campana (T12)
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'REPORTING_BY_FLOW_ENABLED', true),
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'BELL_TASKS_ENABLED', true),
  -- Head of Sales (T13)
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'MANAGER_HOME_ENABLED', true)
ON CONFLICT (company_id, flag) DO UPDATE
  SET enabled = EXCLUDED.enabled, updated_at = NOW();

-- Se dejan APAGADOS hasta tener lo externo:
-- HANDOFF_CRM_OWNER_ENABLED: cambia el owner del deal/contacto en el CRM al AE. Encender
--   cuando los AEs tengan su owner mapeado en HubSpot/Pipedrive y se haya probado con un deal.
-- FOLLOWUP_SEND_ENABLED: envía el follow-up por Resend («{Nombre} vía Vocify», reply-to el
--   comercial). Requiere RESEND_API_KEY y dominio remitente verificado.
-- PLAYBOOK_OBSERVATIONS_ENABLED: C04 v4 (un paso del playbook = cumplido/fallado con cita, y
--   competidores con nombre). Sin él no hay adherencia, pasos fallados, checklist ni competidores.
--   Encender SOLO después de: (1) publicar el playbook con pasos reales en Ajustes -> Proceso y
--   (2) correr los evals 3 veces en verde:  python -u scripts/eval_intelligence.py --v4 --out ...
--   Para releer conversaciones pasadas con v4: scripts/backfill_intelligence.py (tiene coste LLM).
-- RECALL_BOT_ENABLED: bot para Zoom/Meet/Teams. Requiere RECALL_API_KEY, RECALL_REGION,
--   RECALL_WEBHOOK_SECRET y registrar el webhook https://<api>/webhooks/recall en Recall.

COMMIT;

-- =============================================================================
-- Inversa: volver al valor global
-- DELETE FROM company_feature_flags
--  WHERE company_id = '70b7ffd2-c360-4d4f-a339-4affec769f7a'
--    AND flag IN ('SALES_ROLES_ENABLED','HANDOFF_ENABLED','HOY_LEAD_TIERS_ENABLED',
--      'HOY_AE_DEALS_ENABLED','FOLLOWUP_BY_FLOW_ENABLED','ONBOARDING_WIZARD_ENABLED',
--      'SCORING_OBJECTION_CREDIT_ENABLED','DEBRIEF_V2_ENABLED','PLAYBOOK_TAB_ENABLED',
--      'REPORTING_BY_FLOW_ENABLED','BELL_TASKS_ENABLED','MANAGER_HOME_ENABLED');
