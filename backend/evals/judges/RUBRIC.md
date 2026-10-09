# Rúbrica de etiquetado — llamadas SDR de Álvaro (Motor de Ventas)

Álvaro Granado es SDR de **Motor de Ventas**. Llama a prospectos para conseguir una reunión con un AE.
Cada archivo tiene la transcripción con turnos numerados `[n] S1:` / `[n] S2:`. La diarización NO es fiable:
S1/S2 no indican quién es el comercial, y pueden cruzarse a mitad de llamada (el mismo hablante cambia de etiqueta,
o dos personas comparten etiqueta). Decide quién habla POR EL CONTENIDO de cada turno.
Atención: el prospecto a veces también se llama Álvaro ("¿Álvaro?" "Sí, soy yo"); el comercial es quien llama y vende.

## Qué etiquetar por llamada

1. `call_type` (uno):
   - `cold_first_contact`: primer contacto real con este prospecto (aunque haya conectado por LinkedIn antes).
   - `follow_up`: seguimiento de un contacto previo (llamada anterior, correo enviado, "me dijiste que te llamara").
   - `meeting_confirmation`: confirmar o recordar una reunión ya agendada.
   - `meeting_reschedule`: reagendar una reunión perdida, aplazada o que no se hizo.
   - `bad_moment`: el prospecto no puede hablar y se corta casi enseguida (pide que le llamen luego). Úsalo solo si la llamada no llega a tener conversación de venta.
   - `gatekeeper`: habla con recepción/asistente, no con el prospecto.
   - `wrong_person`: no es la persona adecuada / no es el interlocutor.
   - `not_a_sales_call`: no es una llamada de venta (personal, interna, prueba...).
   - `other`.
   Si dudas entre dos, elige uno y añade la duda en `doubts`.
2. `phase_reached`: la última fase a la que llegó la conversación: `opening`, `discovery`, `pitch`, `closing` (proponer/cerrar reunión), o `none` si no hubo conversación.
3. `rep_turns_sample`: hasta 3 números de turno que dijo seguro el comercial, y `prospect_turns_sample`: hasta 3 que dijo seguro el prospecto. Prioriza turnos donde la etiqueta S1/S2 engaña (cruces).
4. `speaker_swap`: true si la etiqueta del comercial cambia en algún momento (p.ej. S1 al principio y S2 al final), o si ambos comparten etiqueta.
5. `steps`: para cada paso del guion, `status` + `turns` (números de turno que lo justifican, si hay) + `why` (una frase corta, en tus palabras, sin copiar más de 10 palabras de la transcripción).
   - `met`: el comercial hizo lo que pretende el paso. **Se juzga la intención, no las palabras exactas.**
   - `missed`: el paso tocaba en esta llamada (por su tipo y por hasta dónde llegó) y el comercial no lo hizo.
   - `not_applicable`: no tocaba: la llamada se cortó antes, el tipo de llamada no lo pide (p.ej. en una confirmación de reunión no se hace discovery), o ya se cubrió en un contacto anterior.
   - `doubt: true` cuando no estés seguro.
6. `doubts`: lista de dudas concretas para que el responsable de ventas decida.

## El guion (playbook "discovery" de Motor de Ventas)

- `apertura_con_motivo` — Apertura con motivo: el SDR se presenta, dice de Motor de Ventas y da un motivo concreto de la llamada ligado a la empresa del prospecto antes de empezar a preguntar.
- `confirmar_quien_decide` — El SDR pregunta si el interlocutor es quien decide sobre el área comercial o quién más participa, y el prospecto responde.
- `descubrir_el_pain` — El SDR pregunta cómo consiguen clientes hoy y el prospecto nombra un problema concreto de su proceso comercial.
- `datos_de_la_empresa` — El SDR pregunta al menos tres de: facturación anual, objetivo de facturación, n.º de clientes, ticket medio, margen, ciclo de venta, n.º de empleados; y el prospecto responde.
- `detectar_urgencia` — El SDR pregunta por qué ahora o qué pasa si no lo resuelven en 90 días, y el prospecto contesta.
- `cerrar_la_meeting` — El prospecto acepta día y hora para reunión con el AE, o el SDR cierra explícitamente que no hay encaje y pregunta el motivo.

## Criterio del responsable de ventas (manda sobre el texto literal)

Ejemplos que el responsable ha dado como **aperturas perfectas** (`met`):
- "soy Álvaro Granado, te llamo de Motor de Ventas, que he visto que habéis conectado con [X]…" y después "he visto que estás en [empresa], me queda curiosidad de cómo estáis captando clientes". → apertura con motivo de manual.
- "soy Álvaro, te llamo de Motor de Ventas, que estuvimos hablando a finales de junio… me dijiste llámame a finales de septiembre". → apertura perfecta para un seguimiento: el motivo es el contacto previo.
Regla: en un seguimiento / confirmación / reagendado, el "motivo concreto" es el contacto previo o la reunión; no se exige un motivo ligado a la empresa.
Cuando un paso pide "y el prospecto responde", el SDR hizo su parte si preguntó; si el prospecto no contesta, márcalo `met` con `doubt: true` y explícalo.

## Salida
Escribe un único archivo JSON (lista, un objeto por llamada) en la ruta que te indiquen, con esta forma:
{"memo_id": "...", "call_type": "...", "phase_reached": "...", "speaker_swap": bool,
 "rep_turns_sample": [..], "prospect_turns_sample": [..],
 "steps": {"apertura_con_motivo": {"status": "...", "turns": [..], "why": "...", "doubt": bool}, ...6 pasos},
 "summary_es": "una frase: qué pasó en la llamada", "doubts": ["..."]}
Lee cada llamada entera. No inventes. Sé coherente entre llamadas.