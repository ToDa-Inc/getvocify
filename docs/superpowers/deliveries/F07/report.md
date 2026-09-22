# Informe F07

Estado: C07 y C08 en `feat/vocify-v1`. El esquema ya está aplicado. Un turno puede guardar si la lectura del CRM fue completa, parcial o prohibida, y la pantalla usa una frase distinta en cada caso. Falta cerrar el panel contra el loop real del copiloto.

## Entregado

| Pieza | Commit | Prueba |
|---|---|---|
| Mismo `client_turn_id` devuelve el mismo turno; un contacto distinto no recibe la escritura; un resultado incierto no se reintenta | commits previos de la rama | `tests/crm_copilot/test_web_turns.py` |
| POST pendiente responde 202; otro usuario no lee el turno | commits previos de la rama | `tests/crm_copilot/test_ask_http.py` |
| Repetir el turno deja una fila y el texto original; otro usuario es otra fila | `66c4aec` | `tests/crm_copilot/test_web_turns.py` contra PostgreSQL |
| Un 403 de alcance en HubSpot y en Pipedrive es `forbidden`, no una bandeja vacía | `cef950b` | `tests/crm_providers/test_context_contract.py` |
| Confirmar otro contacto no aplica; repetir la misma operación no la aplica dos veces | `f9e0352` | `tests/crm_copilot/test_ask_http.py` |
| Pasados 30 s la espera no reenvía; reabrir lee el mismo turno y no desplaza la lectura | `b91e725` | `src/lib/ask-turn.test.ts` |
| La voz se puede cancelar o editar; no se envía sola y no crea un memo | `8f4d3c0` | `src/lib/ask-voice.test.ts` |
| Transcribir la pregunta devuelve texto y `memo_id` null; el silencio queda vacío | `a0ac152` | `tests/crm_copilot/test_ask_http.py` |
| Conversación vacía, sin resultados y lectura parcial del CRM no comparten la misma frase | `40835da` | `src/lib/ask-situation.test.ts` |
| Un turno con lectura prohibida no se guarda como consulta sin resultados | `53f4821` | `tests/crm_copilot/test_ask_http.py` |
| La pregunta web pasa por el loop una vez; el reintento no lo vuelve a llamar | `d72ed0c` | `tests/crm_copilot/test_ask_http.py` |
| Al arrancar, Ask usa el mismo loop que WhatsApp; si falla, el turno sigue pendiente | `d1e6699` | `tests/crm_copilot/test_ask_http.py` |
| Pipedrive no se rechaza como «solo HubSpot»; queda no disponible | `8d11e42` | `tests/crm_providers/test_context_contract.py` |
| Esa no disponibilidad no se guarda como una respuesta vacía | `d1c464b` | `tests/crm_copilot/test_web_turns.py` |
| Confirmar exige operación, revisión y contacto; sin contacto no hay botón | `98bc0fd` | `tests/crm_copilot/test_web_turns.py`, `src/lib/ask-situation.test.ts` |
| La propuesta queda guardada y solo se confirma para ese contacto | este commit | `tests/crm_copilot/test_ask_http.py` |

## No verificado

- Sin pasar por el arranque, los tests HTTP siguen usando memoria.
- Si el turno trae cobertura, la pantalla usa la frase de permiso, de lectura parcial o de sin resultados.
