# Informe F07

Estado: C07 empezado en `feat/vocify-v1`. No cerrado. Un turno repetido es una fila en `copilot_web_turns` y otro usuario no la comparte. El arranque usa ese almacén. La migración `041` no está aplicada en una base compartida. No hay panel de chat ni compositor de voz.

## Entregado

| Pieza | Commit | Prueba |
|---|---|---|
| Mismo `client_turn_id` devuelve el mismo turno; un contacto distinto no recibe la escritura; un resultado incierto no se reintenta | commits previos de la rama | `tests/crm_copilot/test_web_turns.py` |
| POST pendiente responde 202; otro usuario no lee el turno | commits previos de la rama | `tests/crm_copilot/test_ask_http.py` |
| Repetir el turno deja una fila y el texto original; otro usuario es otra fila | este commit | `tests/crm_copilot/test_web_turns.py` contra PostgreSQL |

## No verificado

- Sin pasar por el arranque, los tests HTTP siguen usando memoria.
- No hay `AskPanel` ni recorrido en el navegador.
