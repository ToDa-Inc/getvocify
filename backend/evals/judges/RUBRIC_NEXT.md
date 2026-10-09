# Rúbrica 2 — qué tiene que salir de cada llamada para actuar después

Mismas llamadas de Álvaro (SDR de Motor de Ventas). Turnos numerados `[n] S1/S2:`; la etiqueta de
hablante NO es fiable: decide quién habla por el contenido. Cada archivo indica la fecha y hora de la
llamada (hora UTC; el comercial está en Europe/Madrid, UTC+2 en estas fechas).

Para cada llamada, lo que un buen asistente de ventas debería deducir para el comercial:

1. `followup_email`: ¿hay que mandar un email después de esta llamada?
   - `needed`: true / false.
   - `why`: una frase. true cuando el comercial prometió enviar algo (info, propuesta, invitación,
     caso, precio, resumen) o el prospecto lo pidió ("mándame un correo", "envíame la info").
     Una invitación de calendario para una reunión agendada cuenta como `needed: true` con
     `kind: "calendar_invite"`.
   - `kind`: "info" | "proposal" | "calendar_invite" | "recap" | "other" | null.
   - `content`: qué tiene que llevar, en tus palabras (máx 20 palabras), o null.
2. `callback`: ¿hay que volver a llamar a esta persona?
   - `needed`: true / false (false si se agendó reunión, si dijo que no le interesa de forma
     definitiva, si no es la persona y no hay motivo para volver a llamarla).
   - `when`: lo acordado o pedido: fecha ISO "YYYY-MM-DD" o con hora "YYYY-MM-DDTHH:MM" (hora de
     Madrid), resuelta desde la fecha de la llamada; null si no se dijo cuándo.
   - `when_text`: cómo se dijo ("a las 12:30", "a finales de septiembre", "en enero"), o null.
   - `who_asked`: "prospect" (él pidió que le llamaran) | "rep" (el comercial dijo que llamaría) | null.
   - `why`: una frase: el motivo / gancho para esa llamada (p.ej. "estaba recogiendo a los niños y
     pidió que le llamara a las 12:30"; "pidió volver a hablar en enero cuando tengan presupuesto").
3. `meeting`: ¿quedó agendada una reunión en esta llamada?
   - `booked`: true / false / null (null si se habló pero quedó abierto).
   - `starts_at`: "YYYY-MM-DDTHH:MM" Madrid, o "YYYY-MM-DD" si solo día, o null.
   - `with`: "ae" | "sdr" | "unknown".
4. `refer_to`: si derivaron a otra persona (el decisor real, el CEO...), su nombre/cargo; si no, null.
5. `brief_next_call`: lo que el comercial debería leer justo antes de la PRÓXIMA llamada con esta
   persona, en 1–3 viñetas cortas en español, solo hechos útiles (qué pasó, qué quedó pendiente, el
   gancho para abrir). Nada de relleno ("breve presentación", "se habló de..."). Ejemplo de estilo:
   ["Llamada el 24 sep", "No pudo atenderte: estaba recogiendo a los niños", "Te pidió que le llamaras a las 12:30"].
6. `crm_note_must_have`: hasta 5 hechos que la nota del CRM de esta llamada tiene que recoger sí o
   sí (datos de la empresa dichos por el prospecto, situación, objeciones, decisor, próximo paso).
   Cada uno máx 15 palabras, en tus palabras.
7. `crm_must_not`: hechos que NO deberían aparecer en la nota (cosas que dijo el comercial al
   vender, presentadas como si fueran del prospecto; suposiciones). Lista corta, puede ir vacía.
8. `doubts`: dudas concretas.

Salida: un JSON (lista, un objeto por llamada) con
{"memo_id", "followup_email": {...}, "callback": {...}, "meeting": {...}, "refer_to", "brief_next_call": [...],
 "crm_note_must_have": [...], "crm_must_not": [...], "doubts": [...]}.
Lee cada llamada entera. No inventes: si no se dijo, null. No copies más de 10 palabras seguidas de la transcripción.