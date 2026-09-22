# Informe F06

Estado: la transición de una señal está en `feat/vocify-v1`. No está cerrada.

## Entregado

| Pieza | Prueba |
|---|---|
| `POST /api/v1/today/{id}/resolve` y `PATCH` para deshacer. El mismo `request_id` devuelve la misma transición. Una versión vieja responde 409. A los 5 segundos el deshacer se rechaza y no nombra una llamada | `tests/hoy/test_actions.py` |
| Dos escrituras de la misma versión dejan una sola ganadora | Postgres aislado en el mismo archivo |

No hay migración nueva: usa `previous_status`, `last_action_request_id` y `undo_deadline` de `043`.

## No verificado

- No hay cola de llamadas, ni tarjeta con deshacer en la pantalla, ni conexión con el marcador.
- El deshacer no se recorrió en el navegador.
- F05 sigue sin disparar el día a las 08:00 y sin leer tareas del CRM.
