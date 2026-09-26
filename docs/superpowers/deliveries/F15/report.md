# Informe F15

Estado: **DONE** (código y tests) — verificación en navegador sobre staging pendiente del controlador.

## Criterio de aceptación (DoD)

| Criterio | Resultado | Prueba |
|---|---|---|
| Métricas trazables a memos u observaciones CRM | pass | `tests/team_insights/test_adherence_filters.py::test_activity_counts_trace_to_company_memos`, `test_adherence_crm_outcomes.py::test_loader_attaches_observations_for_adherence` |
| Conectadas sin buzón ni intento suelto | pass | `tests/team_insights/test_aggregate.py` |
| Meeting acordado ≠ venta CRM | pass | `tests/team_insights/test_aggregate.py::test_meeting_agreed_does_not_increment_crm_won` |
| Adherencia/cobertura alineadas con origen | pass | `tests/team_insights/test_aggregate.py`, `test_adherence_filters.py`, `test_objections.py` |
| Member 403 sin cifras | pass | `tests/team_insights/test_permissions.py` |
| Chat no amplía ámbito por texto | pass | `tests/team_insights/test_permissions.py` |
| Informes usan `adherence_crm_outcomes` | pass | `tests/team_insights/test_adherence_crm_outcomes.py::test_scheduled_report_outcomes_match_team_crm_helper` |
| Muestra 1–4: aviso y sin tasa concluyente | pass | `tests/team_insights/test_aggregate.py` (`sample_limited`), `src/lib/team-insights.test.ts` |
| Sin leaderboard/scorecard | pass | `src/lib/team-insights.test.ts` |
| Bloques A14 + tabla; filtros/chat mismo alcance | **pass (código/tests)** | Tablas `sr-only` en componentes; paridad en `test_channels.py`; **Reticle en staging pendiente** |
| Competidores con nombre (flag) | pass | `test_competitors.py` |
| Dedupe deal y atribución | pass | `tests/team_insights/test_outcomes.py`, `src/lib/team-insights.test.ts` |
| Estados vacíos/parciales sin cero ficticio | pass | `tests/team_insights/test_aggregate.py`, `test_adherence_crm_outcomes.py`, `src/lib/team-insights.test.ts` |

## Comandos al cierre (E8)

- `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider` → **1554 passed**
- `node --experimental-strip-types --test src/lib/*.test.ts` → **0 fallos**
- `npm run build` / `vite build` → ok

## Pendiente operativo

- Recorrido manual `/dashboard/insights` en staging (filtros → bloques → tablas; competidores con flag).

## Entregado (resumen técnico)

- Backend: `team_insights/{aggregate,outcomes,objections,competitors}.py`, `GET /api/v1/team/adherence`, migración 049, informes vía `team_adherence`.
- Ask: `get_team_metrics` paridad demostrada; competidores gated por `TEAM_COMPETITORS_ENABLED`.
- Web: `/dashboard/insights`, tablas accesibles A14, competidores en tarjeta Objeciones (flag).
- Sin CRM en vivo en pruebas; sin leaderboard; adherencia pooled; semana Europe/Madrid.
