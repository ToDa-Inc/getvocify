# E9 · Prueba de armonía, salud y activación

Integración de Lista 2: una conversación de ejemplo recorre todas las salidas y comprueba que enseñan los mismos hechos.

### Addendum E9 · armonía de extremo a extremo (26 sep 2026)

Una llamada del marcador y una nota de voz de WhatsApp entran por su entrada real y recorren el código de producción. Solo se simula el IO externo (modelos, STT, API de HubSpot, envío de WhatsApp) y la base de datos (`backend/tests/e2e/fake_db.py`). Todos los tests están en `backend/tests/e2e/test_harmony_conversation.py` y corren para `call` y `whatsapp`.

| Caso | Entrada | Esperado | Test |
|---|---|---|---|
| Una sola C04 vigente | Conversación guardada | Una llamada al modelo C04; `is_current` con compromiso, objeción `price` y reunión | `test_one_c04_run_is_current_for_the_stored_conversation` |
| Fecha del compromiso | «llámame el jueves» (jue 24 sep) | Misma fecha en C04, tarea CRM (E2), fila `commitment_due` de Hoy (una sola tarjeta, con la tarea enlazada), «por qué» del brief y follow-up | `test_commitment_date_is_the_same_in_c04_crm_task_hoy_brief_and_followup` |
| Reunión | «quedamos el jueves a las 11» | Misma hora en C04, propuesta F14 aceptada, reunión escrita en CRM, `meeting_today` y follow-up | `test_meeting_is_the_same_in_c04_proposal_crm_hoy_and_followup` |
| Confirmación en Hoy | Llamada autoaprobada | `confirm_pending` con la propuesta vigente; al confirmar se escriben reunión y etapa. WhatsApp no tiene confirmación | `test_only_the_auto_approved_call_confirms_meeting_and_stage_from_hoy` |
| Reunión en informes | Reunión acordada | 1 en informe semanal, informe de equipo y panel Equipo (WhatsApp: xfail, sin `screening_outcome`) | `test_meeting_counted_in_report_and_team` |
| Dolor | Cita de dolor | Mismo gancho del brief y `pain_quote` del follow-up | `test_pain_quote_is_the_same_in_c04_brief_hook_and_followup` |
| Objeción en Hoy | «Está caro» | `objection_open` con categoría `price` y la cita | `test_price_objection_is_the_same_in_c04_and_hoy` |
| Objeción en Equipo e informe | «Está caro» | `price` en informe y Equipo (xfail: los patrones salen como `other`) | `test_price_objection_reaches_team_and_report` |
| Objeción en brief posterior | «Está caro» | Brief posterior listo con sección `price` (xfail: sin playbook fijado ni patrones `price`) | `test_price_objection_reaches_the_post_call_brief` |
| «Qué decir» del brief | Playbook publicado con entrada de precio | Línea «Precio: …» (xfail: estos canales no fijan playbook ni motion) | `test_brief_says_the_playbook_line_for_the_price_objection` |
| Adherencia F09 | Score publicado | Mismo valor en `memo_scores`, informe, informe de equipo y panel Equipo | `test_adherence_is_the_same_in_score_report_and_team` |
