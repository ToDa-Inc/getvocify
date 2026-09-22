# Informe F07

Estado: C07 y C08 empezados en `feat/vocify-v1`. No cerrado. La voz no se envía sola ni crea un memo: cancelar suelta el micrófono y un permiso denegado deja escribir. La pantalla aún no llama al transcriptor, así que el texto hablado no aparece hasta que se pase esa función. No se probó el micrófono en el navegador. La migración `041` no está aplicada en una base compartida.

## Entregado

| Pieza | Commit | Prueba |
|---|---|---|
| Mismo `client_turn_id` devuelve el mismo turno; un contacto distinto no recibe la escritura; un resultado incierto no se reintenta | commits previos de la rama | `tests/crm_copilot/test_web_turns.py` |
| POST pendiente responde 202; otro usuario no lee el turno | commits previos de la rama | `tests/crm_copilot/test_ask_http.py` |
| Repetir el turno deja una fila y el texto original; otro usuario es otra fila | `66c4aec` | `tests/crm_copilot/test_web_turns.py` contra PostgreSQL |
| Un 403 de alcance en HubSpot y en Pipedrive es `forbidden`, no una bandeja vacía | `cef950b` | `tests/crm_providers/test_context_contract.py` |
| Confirmar otro contacto no aplica; repetir la misma operación no la aplica dos veces | `f9e0352` | `tests/crm_copilot/test_ask_http.py` |
| Pasados 30 s la espera no reenvía; reabrir lee el mismo turno y no desplaza la lectura | `b91e725` | `src/lib/ask-turn.test.ts` |
| La voz se puede cancelar o editar; no se envía sola y no crea un memo | este commit | `src/lib/ask-voice.test.ts` |

## No verificado

- Sin pasar por el arranque, los tests HTTP siguen usando memoria.
- No hay `AskPanel` ni recorrido en el navegador.
