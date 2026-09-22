# Informe F09

Estado: **cerrada** en `feat/vocify-v1` (DoD de aceptación, sin worker LLM ni `INTELLIGENCE_WORKER_PUBLISH`).

## Criterio → prueba

| Criterio | Prueba |
|---|---|
| Cada observación tiene evidencia | `tests/intelligence/test_score_assembly.py::test_met_without_evidence_does_not_publish_a_mark`; `tests/coaching/test_scoring.py::test_a_citation_that_is_not_in_the_evidence_is_not_published` |
| Llamada fácil vs objeción trabajada | `tests/coaching/test_eval_cases.py::test_an_easy_meeting_does_not_outrank_a_handled_objection` |
| Sin playbook → «Falta configurar el proceso» | `src/lib/coaching-score.test.ts` (título `coachingSetupTitle` ES) |
| Sin evidencia suficiente, sin cero ficticio | `tests/coaching/test_metrics.py`; `src/lib/coaching-score.test.ts`; `tests/coaching/test_eval_cases.py::test_ambiguity_and_silence_do_not_invent_a_mark` |
| Adherencia = numerador / denominador | `tests/coaching/test_metrics.py::test_adherence_is_met_steps_over_applicable_steps` |
| Dataset 20 casos (no producto) | `tests/coaching/test_eval_cases.py` + `backend/evals/F09/cases.json` |
| Texto principal concreto (catálogo solo en títulos) | `src/lib/coaching-score.test.ts`; `tests/coaching/test_briefs.py` (sin inventar strength) |
| Misma evidencia, CRM distinto → mismo `value`/adherencia | `tests/coaching/test_scoring.py`; `tests/intelligence/test_score_assembly.py`; eval `c01`/`c05` |
| Estados B3 distintos, sin ceros inventados | `tests/coaching/test_eval_cases.py::test_edge_states_stay_distinct_without_a_fictitious_zero`; `tests/coaching/test_scoring.py::test_a_missing_or_ambiguous_playbook_has_no_mark` |
| CRM tardío en reporting, score intacto | `tests/team_insights/test_adherence_crm_outcomes.py::test_late_crm_outcome_updates_reporting_without_touching_score_parts` |

## Comandos de cierre

```bash
cd backend && .venv/bin/python -m pytest tests/coaching/test_metrics.py tests/coaching/test_scoring.py tests/coaching/test_eval_cases.py tests/intelligence/test_score_assembly.py tests/team_insights/test_adherence_crm_outcomes.py -q
node --test src/lib/coaching-score.test.ts
npm run build
```

Resultado: 65 passed (módulo coaching + hooks relacionados); 3 passed `coaching-score.test.ts`; `vite build` OK.

## Bloqueos

Ninguno para el DoD de aceptación. El scoring determinista post-extracción no usa modelo en runtime; eval LLM de las 20 conversaciones queda fuera de este cierre (no requiere worker flag).

## Entregado (resumen técnico)

- `compute_adherence` / agregación por conteos (`metrics.py`).
- Ensamblado y persistencia (`scoring.py`, `score_assembly.py`, hooks post-extracción).
- `GET /api/v1/memos/{id}/score` (lectura almacenada).
- UI `coachingSurface` / `CoachingScore` + `useMemoScore`.
