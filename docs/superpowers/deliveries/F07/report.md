# Informe F07

Estado: C07 y C08 empezados en `feat/vocify-v1`. No cerrado. Un error de permiso al leer correos no se presenta como bandeja vacía, ni en HubSpot ni en Pipedrive. No hay panel de chat. La migración `041` no está aplicada en una base compartida.

## Entregado

| Pieza | Commit | Prueba |
|---|---|---|
| Mismo `client_turn_id` devuelve el mismo turno; un contacto distinto no recibe la escritura; un resultado incierto no se reintenta | commits previos de la rama | `tests/crm_copilot/test_web_turns.py` |
| POST pendiente responde 202; otro usuario no lee el turno | commits previos de la rama | `tests/crm_copilot/test_ask_http.py` |
| Repetir el turno deja una fila y el texto original; otro usuario es otra fila | `66c4aec` | `tests/crm_copilot/test_web_turns.py` contra PostgreSQL |
| Un 403 de alcance en HubSpot y en Pipedrive es `forbidden`, no una bandeja vacía | este commit | `tests/crm_providers/test_context_contract.py` |

## No verificado

- Sin pasar por el arranque, los tests HTTP siguen usando memoria.
- No hay `AskPanel` ni recorrido en el navegador.
