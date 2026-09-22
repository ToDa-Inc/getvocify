# Informe F15

Estado: **BLOCKED** — falta un criterio de aceptación (alcance compartido panel/chat en navegador).

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
| Muestra 1–4: aviso y sin tasa concluyente | pass | `tests/team_insights/test_aggregate.py` (`sample_limited`), `src/lib/team-insights.test.ts` (`sampleLimited` → `winRate` null) |
| Sin leaderboard/scorecard | pass | `src/lib/team-insights.test.ts` (ausencia en fuentes) |
| Bloques A14 + tabla; filtros/chat mismo alcance | **pendiente** | Tablas en componentes verificadas en `src/lib/team-insights.test.ts`; **bloqueador:** sin sesión Reticle en `/dashboard/insights` ni paridad numérica Ask↔panel (herramienta `get_team_metrics` solo devuelve `scope`) |
| Dedupe deal y atribución | pass | `tests/team_insights/test_outcomes.py`, `src/lib/team-insights.test.ts` |
| Estados vacíos/parciales sin cero ficticio | pass | `tests/team_insights/test_aggregate.py`, `test_adherence_crm_outcomes.py`, `src/lib/team-insights.test.ts` |

## Comandos al cierre

- `cd backend && .venv/bin/python -m pytest tests/team_insights tests/reporting -q` → 63 passed
- `npm run build` → ok
- `make test-js` → ok (incl. `src/lib/team-insights.test.ts`)

## Bloqueadores

1. **DoD visual/alcance compartido (criterio A14 + chat):** hace falta `reticle_act_and_wait` en `/dashboard/insights` (filtros → bloques → tablas) y definir si Ask debe devolver los mismos números que el panel además del `scope` autorizado.

## Entregado (resumen técnico)

- Backend: `team_insights/{aggregate,outcomes,objections}.py`, `GET /api/v1/team/adherence`, migración 049, informes diarios vía `_outcomes_for_snapshot` → `adherence_crm_outcomes`.
- Web: `/dashboard/insights`, módulo `src/features/team-insights/`, copy EN/ES desde `product-catalog.ts`.
- Sin CRM en vivo en pruebas; sin leaderboard; adherencia pooled; semana Europe/Madrid.
