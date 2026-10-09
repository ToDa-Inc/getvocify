# Informe F04

Estado: **DONE** — los ocho criterios de aceptación del plan tienen prueba automatizada ejecutada en cierre.

## Criterio → prueba

| Criterio | Prueba |
|---|---|
| Dolor reciente antes de «nunca llamado» | `tests/hoy/test_priority.py::test_recent_pain_without_a_meeting_outranks_a_complete_never_called` |
| Reunión acordada no es captación | `tests/hoy/test_priority.py::test_agreed_meeting_is_not_a_prospecting_call_and_incomplete_history_is_not_never_called` |
| Deal cerrado fuera de la lista activa | `tests/hoy/test_priority.py::test_two_connections_and_a_closed_deal_stay_apart` |
| Candidatos dentro de la asignación | `tests/hoy/test_priority_http.py::test_rows_drive_empty_partial_and_the_personal_list`; `tests/hoy/test_priority_context.py::test_an_ambiguous_email_stays_out_and_a_shared_name_does_not_assign` |
| Incompleto ≠ sin llamadas | `tests/hoy/test_priority_context.py::test_an_unfinished_page_from_either_crm_is_not_never_called`; ranking `history_partial` en `test_priority.py` |
| Cambio de fuente explicable | `tests/hoy/test_priority.py::test_turning_on_recent_pain_changes_tier_and_reason` |
| Vacío completo, sin asignados y error CRM distintos | `tests/hoy/test_priority.py::test_empty_states_are_distinct`; `tests/hoy/test_priority_http.py::test_a_complete_empty_crm_is_not_the_same_as_no_priority_candidates`; `test_no_connection_is_not_an_empty_complete_list`; `test_forbidden_fetch_is_not_an_empty_complete_list`; `node --test src/lib/contact-priorities.test.ts` |
| Parcial no «nunca llamado»; deals separados | `tests/hoy/test_priority_http.py::test_a_folded_unfinished_page_is_what_the_route_returns`; deal cerrado vs abierto arriba |

## Comandos de cierre

```text
cd backend && .venv/bin/python -m pytest tests/hoy/test_priority.py tests/hoy/test_priority_context.py tests/hoy/test_priority_http.py -q
node --test src/lib/contact-priorities.test.ts
npm run build
```

## Limitaciones (no bloquean DoD)

- El `GET` usa cliente Supabase falso en HTTP tests; no hay instancia remota en CI local.
- Lectura asignada real usa `access_token` de la conexión; fallo de transporte no sustituye caché (cubierto en tests de `collect_assigned` / fold).
- HubSpot sin `portal_id` no expone URL de contactos (`test_empty_states_are_distinct`).
- Verificación Reticle de UI no ejecutada en este cierre; estados web cubiertos por `contact-priorities.test.ts` y contrato HTTP de claves estables.
