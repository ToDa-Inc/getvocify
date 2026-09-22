# Informe F06

Estado: la transición de una señal está en `feat/vocify-v1`. No está cerrada.

## Entregado

| Pieza | Prueba |
|---|---|
| `POST /api/v1/today/{id}/resolve` y `PATCH` para deshacer. El mismo `request_id` devuelve la misma transición. Una versión vieja responde 409. A los 5 segundos el deshacer se rechaza y no nombra una llamada | `tests/hoy/test_actions.py` |
| Dos escrituras de la misma versión dejan una sola ganadora | Postgres aislado en el mismo archivo |
| Cola: buzón y no respuesta avanzan aunque haya memo; conversación abre ese memo; fallo se queda en el contacto | `shared/ui/queue.test.js` 4 passed |

No hay migración nueva: usa `previous_status`, `last_action_request_id` y `undo_deadline` de `043`.

## No verificado

- La cola no está conectada al marcador de la extensión ni a los botones de Hoy.
- El deshacer no se recorrió en el navegador.
- F05 sigue sin disparar el día a las 08:00 y sin leer tareas del CRM.
