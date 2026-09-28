# Informe F05

Estado: **DONE** — los diez criterios de aceptación del plan tienen prueba automatizada ejecutada en cierre.

## Criterio → prueba

| Criterio | Prueba |
|---|---|
| Casos de S §5 (señales, ranking, reconcile, reason/due ES+EN) | `tests/hoy/test_signals.py` |
| Compromiso futuro silencia enfriamiento | `test_signals.py::test_a_due_commitment_is_a_card_and_a_future_one_silences_going_cold` |
| Interacción nueva retira señales obsoletas | `test_signals.py::test_ten_silent_days_go_cold_and_a_newer_touch_clears_the_old_one` |
| Descarte permanece tras re-evaluación / trabajo diario | `test_signals.py::test_reconcile_does_not_resurrect_a_dismissed_key_and_resolves_a_stale_pending_one`; `test_reconcile.py::test_same_key_keeps_every_commitment_and_dismissal_survives` |
| Snooze vence y reaparece solo si sigue aplicando | `test_reconcile.py::test_a_down_source_does_not_resolve_and_an_expired_snooze_reopens_only_if_it_still_applies` |
| Dos trabajadores, una fila lógica | `test_reconcile.py::test_two_workers_insert_one_row_and_only_one_reopen_wins`; `test_schedule.py::test_two_workers_claim_one_local_day` |
| Tareas manuales y detectadas, procedencia clara | `test_schedule.py::test_a_manual_task_merges_only_through_an_explicit_link` |
| Fallo lectura CRM no vacía ni resuelve | `test_schedule.py::test_today_reads_the_connected_crm_and_keeps_the_card_if_the_read_fails`; `test_reconcile.py::test_a_down_source_does_not_resolve_and_an_expired_snooze_reopens_only_if_it_still_applies` |
| Onboarding sin actividad, vacío operativo, CRM sin memos Vocify | `src/lib/today.test.ts` (connect, clear, no-activity, CRM-only); `test_schedule.py::test_today_shows_tasks_when_a_reader_is_installed` |
| Fuente parcial conserva tarjetas; pulso incompleto | `src/lib/today.test.ts` (refetch parcial); `test_schedule.py::test_a_manual_task_merges_only_through_an_explicit_link` (build parcial); `test_schedule.py::test_today_keeps_a_pending_card_when_crm_tasks_were_not_read` |

## Comandos de cierre

```text
cd backend && .venv/bin/python -m pytest tests/hoy -q
node --test src/lib/today.test.ts
npm run build
make test-js
```

## Limitaciones (no bloquean DoD)

- Verificación Reticle del inicio web (`TodayPanel`, orden saludo → Hoy → grabación → historial) no ejecutada en este cierre; estados cubiertos por `src/lib/today.test.ts` y contrato `GET /today`.
- Lectura CRM en producción usa token de conexión `connected`; tests usan `MockTransport` / `set_today_fetch`, no un CRM en vivo.
- Migración `043` ya aplicada en entornos con schema al día; este cierre no añade migración.
