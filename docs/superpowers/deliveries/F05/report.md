# Informe F05

Estado: el motor puro de señales está en `feat/vocify-v1`. No está cerrada.

## Entregado

| Pieza | Prueba |
|---|---|
| `signals_for_contact`, `rank_cards`, `reconcile`, `reason`, `due_label` con los umbrales de S: 10 días, siete tarjetas, un compromiso futuro calla el enfriamiento | `tests/hoy/test_signals.py` |
| Una objeción `resolved` o un interés desconocido no abre tarjeta, aunque quede texto legacy | el mismo archivo |
| Reconciliación: descarte permanece, fuente caída no resuelve, snooze vencido reabre solo si sigue aplicando, dos escrituras dejan una fila | `tests/hoy/test_reconcile.py` 3 passed, Postgres aislado |
| `GET /api/v1/today`: un día local, una ejecución; una tarea manual se une solo con vínculo explícito; el pulso queda vacío si falta una fuente | `tests/hoy/test_schedule.py` 5 passed, Postgres aislado |
| `GET /today` reclama `hoy_daily_runs` tras las 08:00 locales vía `claim_if_due`; un fallo de claim no rompe la vista | `tests/hoy/test_schedule.py` |
| `GET /today` usa `brief_preferences.timezone` del usuario para el claim; sin preferencia o lectura fallida, `Europe/Madrid` | `tests/hoy/test_schedule.py` |
| Inicio: Hoy bajo el saludo, grabación después, historial al final. El vacío de prioridades no se repite. «Nada urgente» solo con cobertura completa | `src/lib/today.test.ts` 4 passed; `tsc --noEmit` |

`rank_cards` no sustituye a `rank_candidates` de F04.

## No verificado

- `GET /today` lee las tareas abiertas de la conexión `connected` con el token. Sin conexión, `crm_tasks` queda `unavailable`. Un fallo de lectura deja la tarjeta que ya estaba.
- El esquema de `043` ya está aplicado.
