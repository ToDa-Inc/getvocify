# E9 · Prueba de armonía, salud y activación

Integración de Lista 2: una conversación de ejemplo recorre todas las salidas y comprueba que enseñan los mismos hechos.

## Addendum E9 (26 sep 2026)

| Caso | Entrada | Esperado | Test |
|---|---|---|---|
| Compromiso alineado | C04 `commitments[0]` con «llamar el jueves» y fecha jue 24 sep | Misma tarea y fecha en CRM (E2), tarjeta `commitment_due` en Hoy y «por qué llamas» del brief v2 | `test_harmony_all_surfaces_share_commitment_facts` |
| Reunión alineada | F14 aceptada con `starts_at` jue 24 sep 11:00 | Tarjeta `meeting_today` el día de la reunión con hora 11:00 | `test_harmony_all_surfaces_share_commitment_facts` |
| Objeción y playbook | Objeción `price` abierta + entrada de playbook | Misma categoría en Hoy, «qué decir» del brief y patrón en Equipo | `test_harmony_all_surfaces_share_commitment_facts` |
| Dolor y gancho | `pain_confirmed` con cita | Mismo gancho en brief v2 y `pain_quote` en follow-up | `test_harmony_all_surfaces_share_commitment_facts` |
| Confirmación tras autoaprobación | Autoaprobación con reunión pendiente y etapa distinta | Señal `confirm_pending` en Hoy (E7) | `test_harmony_all_surfaces_share_commitment_facts` |
| Nota F09 | Score publicado tras hooks | Nota coherente con objeción de precio | `test_harmony_all_surfaces_share_commitment_facts` |
| Canal llamada | `interaction_kind=call`, `source=vocify_call` | Mismas aserciones que WhatsApp | `test_harmony_all_surfaces_share_commitment_facts[call]` |
| Canal WhatsApp | Entrada `processor._extract_and_create_memo` | `interaction_kind=visit` y mismas aserciones | `test_harmony_all_surfaces_share_commitment_facts[whatsapp]` |
