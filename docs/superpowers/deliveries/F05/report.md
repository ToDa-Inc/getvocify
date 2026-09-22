# Informe F05

Estado: el motor puro de señales está en `feat/vocify-v1`. No está cerrada.

## Entregado

| Pieza | Prueba |
|---|---|
| `signals_for_contact`, `rank_cards`, `reconcile`, `reason`, `due_label` con los umbrales de S: 10 días, siete tarjetas, un compromiso futuro calla el enfriamiento | `tests/hoy/test_signals.py` |
| Una objeción `resolved` o un interés desconocido no abre tarjeta, aunque quede texto legacy | el mismo archivo |
| Reconciliación: descarte permanece, fuente caída no resuelve, snooze vencido reabre solo si sigue aplicando, dos escrituras dejan una fila | `tests/hoy/test_reconcile.py` 3 passed, Postgres aislado |
| `GET /api/v1/today`: un día local, una ejecución; una tarea manual se une solo con vínculo explícito; el pulso queda vacío si falta una fuente | `tests/hoy/test_schedule.py` 5 passed, Postgres aislado |
| Inicio: Hoy bajo el saludo, grabación después, historial al final. El vacío de prioridades no se repite. «Nada urgente» solo con cobertura completa | `src/lib/today.test.ts` 4 passed; `tsc --noEmit` |

`rank_cards` no sustituye a `rank_candidates` de F04.

## No verificado

- No hay un proceso que dispare la ejecución a las 08:00. El `GET` todavía no lee tareas del CRM.
- El inicio no se recorrió en el navegador: Reticle no tiene sesión en este worktree.
- La migración no está aplicada en una base compartida.
- F04 sigue abierta: el recorrido de páginas no usa el token de la conexión, y el inicio no se recorrió en el navegador.
