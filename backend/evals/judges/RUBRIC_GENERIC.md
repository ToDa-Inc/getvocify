# Rúbrica genérica — cualquier empresa, cualquier comercial

Cada archivo es una conversación grabada por un comercial (B2B). La cabecera dice: la empresa para
la que vende, el nombre del comercial (puede venir con "(test)"), el origen (voice_memo = llamada o
nota de voz; meeting_transcript = reunión), y los pasos del guion de ventas si la empresa tiene uno.
Turnos numerados `[n] ETIQUETA: texto`. La ETIQUETA (S1/S2, un nombre, "?") viene de la
diarización automática y NO es fiable: puede no decir quién es el comercial, cruzarse a mitad de
llamada, o haber un único bloque sin etiquetas. Decide quién habla POR EL CONTENIDO.
Si todo es un único turno sin etiquetas, puede ser una nota dictada por el comercial: dilo.

Etiqueta por conversación (JSON, un objeto por conversación):

1. `call_type`: cold_first_contact (primera conversación de ESTE comercial con ESTA persona; que
   hablara antes con un compañero no la convierte en seguimiento) | follow_up | meeting_confirmation |
   meeting_reschedule | discovery_meeting (reunión/demo agendada, larga) | bad_moment (no puede hablar y
   se corta, sin conversación de venta) | gatekeeper | wrong_person (no es la persona: ya no está, no es
   su área, número equivocado) | no_conversation (buzón, no contesta, solo saludos, audio roto) |
   not_a_sales_call (personal, interna, prueba) | dictated_note (el comercial dicta una nota, una sola voz) | other.
2. `phase_reached`: none | opening | discovery | pitch | closing (la fase más avanzada a la que llegó).
3. `rep_turns_sample`: hasta 3 números de turno que dijo seguro el comercial; `prospect_turns_sample`:
   hasta 3 del prospecto. Prioriza turnos donde la ETIQUETA engaña. Vacíos si es un único turno.
4. `speaker_swap`: true si la etiqueta del comercial cambia o se comparte.
5. `steps` (SOLO si la cabecera trae pasos del guion): por paso {status, doubt, why}. Juzga por la
   INTENCIÓN del paso, no por las palabras exactas.
   met = lo hizo; missed = tocaba y no lo hizo; not_applicable = no tocaba (la llamada se cortó antes,
   el tipo de llamada no lo pide, o ya se hizo en una conversación anterior).
   Reglas: en follow_up / meeting_confirmation / meeting_reschedule solo se juzga la apertura (recordar
   el contacto previo basta como motivo); el resto: met si lo hizo, si no not_applicable.
   En bad_moment / gatekeeper / wrong_person solo la apertura. Si un paso pide "y el prospecto responde",
   basta con que el comercial lo pregunte. Un paso sobre cerrar/agendar la reunión NO se etiqueta
   (lo declara el comercial): ponlo como "rep_outcome".
6. `followup_email`: {needed, kind: info|proposal|calendar_invite|recap|other|null, content (≤20 palabras), to (nombre/rol si no es el interlocutor)}.
   needed si el comercial prometió enviar algo o el prospecto lo pidió (incluida una invitación de calendario).
7. `callback`: {needed, who_asked: prospect|rep|null, when ("YYYY-MM-DD" o "YYYY-MM-DDTHH:MM" hora de
   Madrid, resuelta desde la fecha de la cabecera, que está en UTC; null si nadie dijo cuándo),
   when_text, why (≤15 palabras: el gancho)}. false si se agendó reunión, si dijo un no definitivo, o si
   derivó a otra persona sin motivo para volver a llamarle.
8. `meeting`: {booked: true|false|null, starts_at (como callback.when) , with: ae|sdr|unknown}.
9. `refer_to`: nombre/rol si derivó a otra persona, si no null.
10. `brief_next_call`: 1–3 viñetas cortas en español para leer justo antes de la próxima llamada con
    esta persona: qué pasó, qué quedó pendiente, el gancho. Solo hechos útiles, nada de relleno.
11. `crm_note_must_have`: hasta 5 hechos (≤15 palabras) que la nota del CRM debe recoger;
    `crm_must_not`: cosas que no deben aparecer (lo que dijo el comercial al vender atribuido al
    prospecto, suposiciones).
12. `summary_es`: una frase con qué pasó. `doubts`: dudas concretas.

Forma: {"memo_id","call_type","phase_reached","speaker_swap","rep_turns_sample","prospect_turns_sample",
"steps": {...} o {}, "followup_email","callback","meeting","refer_to","brief_next_call",
"crm_note_must_have","crm_must_not","summary_es","doubts"}.
Lee cada conversación entera. No inventes. No copies más de 10 palabras seguidas.