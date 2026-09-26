-- Vocify · consultas de salud por objetivo (Lista 2, E9)
-- Solo lectura. Sustituye :company_id por el UUID de la empresa (p. ej. el de staging).
-- Ejemplo: en el SQL editor de Supabase, busca el id con
--   SELECT id, name FROM companies WHERE name ILIKE '%vocify%';
-- y reemplaza :company_id manualmente o usa una variable de tu cliente.

-- =============================================================================
-- Objetivo 1 · Vocify en cada interacción
-- % de conversaciones con inteligencia C04 vigente, por canal
-- Cuenta C04 con status ready o partial (partial también tiene hechos con evidencia: dolor,
-- reunión). 'intelligence_v3' es PROMPT_VERSION de backend/app/services/intelligence/extract.py:
-- SQL no puede leer esa constante, así que al subir de versión hay que cambiarla aquí.
-- «Vigente» en la app también exige input_revision == revision_for_memo(memo), un hash que
-- calcula Python; en SQL solo se comprueba que exista, así que esto es un techo, no el dato exacto.
-- =============================================================================
SELECT
  COALESCE(interaction_kind, 'unknown') AS channel,
  COUNT(*) AS conversations,
  COUNT(*) FILTER (
    WHERE extraction->'intelligence'->>'status' IN ('ready', 'partial')
      AND extraction->'intelligence'->>'prompt_version' = 'intelligence_v3'
      AND COALESCE(extraction->'intelligence'->>'input_revision', '') <> ''
  ) AS with_intelligence,
  ROUND(
    100.0 * COUNT(*) FILTER (
      WHERE extraction->'intelligence'->>'status' IN ('ready', 'partial')
        AND extraction->'intelligence'->>'prompt_version' = 'intelligence_v3'
        AND COALESCE(extraction->'intelligence'->>'input_revision', '') <> ''
    ) / NULLIF(COUNT(*), 0),
    1
  ) AS pct_with_intelligence
FROM memos
WHERE company_id = :company_id
  AND transcript IS NOT NULL
  AND btrim(transcript) <> ''
  AND COALESCE(screening_outcome, '') NOT IN ('voicemail', 'no_response')
GROUP BY 1
ORDER BY conversations DESC;

-- =============================================================================
-- Objetivo 2 · CRM casi solo
-- % escritas en el CRM (approved) y confirmaciones pendientes con más de 2 días
-- =============================================================================
SELECT
  COUNT(*) AS conversations,
  COUNT(*) FILTER (WHERE status = 'approved') AS approved_in_crm,
  ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'approved') / NULLIF(COUNT(*), 0), 1) AS pct_approved
FROM memos
WHERE company_id = :company_id
  AND transcript IS NOT NULL
  AND btrim(transcript) <> ''
  AND COALESCE(screening_outcome, '') NOT IN ('voicemail', 'no_response');

SELECT
  COUNT(*) AS confirm_pending_over_2d
FROM action_signals
WHERE company_id = :company_id
  AND type = 'confirm_pending'
  AND status = 'pending'
  AND created_at < NOW() - INTERVAL '2 days';

-- =============================================================================
-- Objetivo 3 · Admin (follow-up y preparación)
-- Borradores abiertos (ready/generating) y edición media de los enviados
-- =============================================================================
SELECT
  COUNT(*) FILTER (WHERE followup->>'status' IN ('ready', 'generating')) AS open_drafts,
  COUNT(*) FILTER (WHERE followup->>'status' = 'sent') AS sent_drafts,
  ROUND(AVG((followup->>'edit_ratio')::numeric) FILTER (WHERE followup->>'status' = 'sent'), 3) AS avg_edit_ratio
FROM memos
WHERE company_id = :company_id
  AND followup IS NOT NULL;

-- =============================================================================
-- Objetivo 4 · Coaching
-- Adherencia por semana (lunes a domingo, hora de Madrid) de las últimas 8 semanas.
-- Un memo reevaluado tiene una fila por input_revision: solo cuenta la más reciente.
-- =============================================================================
WITH latest AS (
  SELECT DISTINCT ON (ms.memo_id)
    ms.memo_id,
    ms.created_at,
    ms.score
  FROM memo_scores ms
  JOIN memos m ON m.id = ms.memo_id
  WHERE m.company_id = :company_id
  ORDER BY ms.memo_id, ms.created_at DESC, ms.revision_seq DESC
)
SELECT
  date_trunc('week', created_at AT TIME ZONE 'Europe/Madrid')::date AS week_start_madrid,
  COUNT(*) AS scored_memos,
  COUNT(*) FILTER (WHERE score->>'adherence' IS NOT NULL) AS with_adherence,
  ROUND(AVG((score->>'adherence')::numeric) FILTER (WHERE score->>'adherence' IS NOT NULL), 3)
    AS adherence_avg
FROM latest
WHERE created_at >= (date_trunc('week', NOW() AT TIME ZONE 'Europe/Madrid') - INTERVAL '7 weeks')
                    AT TIME ZONE 'Europe/Madrid'
GROUP BY 1
ORDER BY 1 DESC;

-- No hay columna de «visto» en post_interaction_briefs (solo memo_id, input_revision,
-- status, body, created_at). No se puede medir briefs posteriores vistos sin instrumentar UI.
