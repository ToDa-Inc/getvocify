-- Vocify staging · activación de flags Lista 2 (E9)
-- company_id Vocify en staging: 70b7ffd2-c360-4d4f-a339-4affec769f7a
-- No ejecutar desde CI ni desde el agente: lo ejecuta el founder en Supabase.
-- Tabla: company_feature_flags (migración 051_company_feature_flags.sql)

BEGIN;

-- Inteligencia y pipeline común
INSERT INTO company_feature_flags (company_id, flag, enabled) VALUES
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'INTELLIGENCE_EXTRACT_ENABLED', true),
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'COMMITMENT_TASKS_ENABLED', true),
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'DEAL_STAGE_CONFIRM_ENABLED', true),
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'BRIEF_V2_ENABLED', true),
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'FOLLOWUP_ENABLED', true),
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'HOY_CONFIRMATIONS_ENABLED', true),
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'HOY_MEETINGS_ENABLED', true),
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'REP_WORKSPACE_ENABLED', true),
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'TEAM_COMPETITORS_ENABLED', true),
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'TEAM_ADHERENCE_TREND_ENABLED', true),
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'REPORTING_WEEKLY_ENABLED', true),
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'REPORTING_TEAM_ENABLED', true),
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'NOTIFICATIONS_ACTIVITY_ENABLED', true),
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'ASK_VOCIFY_DATA_TOOLS_ENABLED', true),
  ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'ASK_CALL_ACTIONS_ENABLED', true)
ON CONFLICT (company_id, flag) DO UPDATE
  SET enabled = EXCLUDED.enabled, updated_at = NOW();

-- REPORTING_DAILY_EMAIL_ENABLED se deja APAGADO: el flujo de email diario no está
-- revisado por el founder (ver PENDIENTES.md). El informe se genera y sale en la campana.
-- INSERT INTO company_feature_flags (company_id, flag, enabled) VALUES
--   ('70b7ffd2-c360-4d4f-a339-4affec769f7a', 'REPORTING_DAILY_EMAIL_ENABLED', true)
-- ON CONFLICT (company_id, flag) DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = NOW();

COMMIT;

-- =============================================================================
-- Inversa: volver al valor global (DELETE por flag)
-- =============================================================================
-- DELETE FROM company_feature_flags
-- WHERE company_id = '70b7ffd2-c360-4d4f-a339-4affec769f7a'
--   AND flag IN (
--     'INTELLIGENCE_EXTRACT_ENABLED',
--     'COMMITMENT_TASKS_ENABLED',
--     'DEAL_STAGE_CONFIRM_ENABLED',
--     'BRIEF_V2_ENABLED',
--     'FOLLOWUP_ENABLED',
--     'HOY_CONFIRMATIONS_ENABLED',
--     'HOY_MEETINGS_ENABLED',
--     'REP_WORKSPACE_ENABLED',
--     'TEAM_COMPETITORS_ENABLED',
--     'TEAM_ADHERENCE_TREND_ENABLED',
--     'REPORTING_WEEKLY_ENABLED',
--     'REPORTING_TEAM_ENABLED',
--     'NOTIFICATIONS_ACTIVITY_ENABLED',
--     'ASK_VOCIFY_DATA_TOOLS_ENABLED',
--     'ASK_CALL_ACTIONS_ENABLED'
--   );
