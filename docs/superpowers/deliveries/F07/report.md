# Informe F07

Estado: **cerrada** contra el Definition of Done (11/11 criterios de aceptación). Sin sesión live HubSpot/Pipedrive ni llamadas a OpenRouter en las pruebas de cierre.

## Criterio → prueba

| Criterio | Prueba |
|---|---|
| Mismo loop web y WhatsApp | `test_live_ask_loop_uses_the_same_run_copilot_turn_as_whatsapp` |
| HubSpot y Pipedrive, capacidades equivalentes (fixtures) | `tests/crm_providers/test_context_contract.py` |
| Sin escritura sin confirmación válida | `test_writes_require_confirmation`, `test_a_proposed_confirmation_can_be_confirmed_for_that_contact_only`, `test_confirm_with_empty_memory_loads_the_stored_proposal_once` |
| Doble envío / reintento no duplica operación | `test_repeating_a_client_turn_returns_the_same_turn`, `test_confirming_another_contact_writes_nothing_and_a_repeat_does_not_apply_twice`, `test_a_repeated_ask_turn_is_one_row_and_another_user_is_separate` |
| Cambio de contacto invalida propuesta | `test_changing_contact_before_confirm_writes_nothing`, confirm HTTP 409 |
| Miembro no lee otro usuario / ID ajeno | `test_another_user_cannot_read_the_turn`, `test_a_foreign_object_is_denied_before_its_items_are_returned`, PG `save_ask_turn` |
| Audio y texto, mismas herramientas (mismo POST de turno) | `test_a_transcribed_question_uses_the_same_turn_loop_as_typed_text`, `src/lib/ask-voice.test.ts` |
| Respuesta sin tool_call ni JSON crudo | `test_a_tool_call_line_is_not_part_of_the_answer`, `test_a_completed_row_body_is_not_shown_as_raw_json` |
| 202, polling, reabrir, error tardío | `test_pending_turn_is_accepted_and_replay_keeps_the_same_id`, `src/lib/ask-turn.test.ts` |
| Voz: grabar / transcribir / enviar manual | `src/lib/ask-voice.test.ts` |
| Vacío / sin resultados / parcial / foco y scroll | `src/lib/ask-situation.test.ts`, `closeAskPanel` en `src/lib/ask-turn.test.ts` |

## Regresiones al cerrar

- `cd backend && .venv/bin/python -m pytest tests/crm_copilot tests/crm_providers -q` → 51 passed
- `make test-js` → 42 passed
- `npm run build` → ok

## Bloqueos (fuera del DoD de aceptación)

- **CRM live:** no se ejecutaron lecturas reales contra cuentas HubSpot/Pipedrive; los criterios de contrato usan fixtures y adapters mock.
- **Loop live OpenRouter:** `live_ask_loop` está cableado en `main.py` pero no se invocó contra un modelo en este cierre.
- **Reticle:** no se pidió veredicto Reticle en el DoD de las 11 casillas; flujo web no verificado con `reticle_act_and_wait` en este commit.

## Entregado (histórico)

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
| La propuesta queda guardada y solo se confirma para ese contacto | `0a36037` | `tests/crm_copilot/test_ask_http.py` |
| Confirmar de verdad llama al loop una vez; otro contacto y un repetido no | `ac766e4` | `tests/crm_copilot/test_ask_http.py` |
| Una línea de tool_call no entra en la respuesta | commits previos | `tests/crm_copilot/test_web_turns.py` |
| Un turno con opciones del copiloto devuelve id y etiqueta; sin opciones no hay clave `choices` | commits previos | `tests/crm_copilot/test_web_turns.py`, `src/lib/ask-choices.test.ts` |
| Tras confirmar, cancelar, reopen sin botones | commits previos | `src/lib/ask-confirm.test.ts`, `tests/crm_copilot/test_ask_http.py` |
