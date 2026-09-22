# Informe F06

Estado: cerrada contra el Definition of Done de `08-f06-acciones-y-cola.md` (criterios de aceptación). Reticle en marcador web/reposo y companion desktop siguen sin veredicto.

## Criterio → prueba

| Criterio | Prueba |
|---|---|
| Llamar con el contacto de la tarjeta, sin búsqueda | `src/lib/today-dial.test.ts` |
| Posponer, descartar y deshacer tras recarga | `tests/hoy/test_actions.py::test_dismiss_snooze_and_undo_survive_a_fresh_get`, `src/lib/today.test.ts` |
| Otra superficie ve la misma acción al refrescar | mismo test HTTP (`other.get` tras `POST`) |
| Buzón / no respuesta avanzan sin revisión de memo | `shared/ui/queue.test.js` |
| Llamada fallida no completa la señal | `shared/ui/queue.test.js` |
| Cola con teclado (`QUEUE_KEYS`) | `shared/ui/queue.test.js` |
| Razones cortas y server-side | `tests/hoy/test_reasons.py`, `src/lib/today.test.ts` (reason en superficie) |
| Salida con altura medida; refetch sin duplicar | `shared/ui/today-card.test.js` |
| Movimiento reducido solo opacidad; foco útil | `shared/ui/today-card.test.js` |

## Entregado (contrato C11)

| Pieza | Prueba |
|---|---|
| `POST /api/v1/today/{id}/resolve` y `PATCH` deshacer; idempotencia, 409, undo 5 s | `tests/hoy/test_actions.py` |
| Postgres: una sola transición ganadora | mismo archivo |
| `GET /today` incluye descartes con undo activo y `last_action_request_id` | `test_dismiss_snooze_and_undo_survive_a_fresh_get` |
| Cola F06 en Hoy (sin Telnyx desde el reducer) | `src/lib/today-queue.test.ts` |
| Descartar/Deshacer vía catálogo | `shared/ui/today-card.test.js`, `src/lib/today.test.ts` |

Sin migración nueva (043).

## Bloqueos (fuera del DoD de aceptación)

- Reticle: descarte con Deshacer en home web y marcador en reposo (`TodayDialerCards`).
- Desktop: `GET /today` en reposo, descarte/deshacer (`desktop/lib/home-hoy.test.js` no existe aún).
