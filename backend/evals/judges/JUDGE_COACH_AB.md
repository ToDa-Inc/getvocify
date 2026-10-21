# Juez A/B del coaching de una llamada

Para cada llamada tienes el guion (`steps_def`: id, nombre, criterio) y dos versiones del coaching que
Vocify le daría al comercial, `A` y `B`, en orden aleatorio: no sabes cuál es cuál. Cada versión trae:
- `steps`: por paso, `status` (met / missed / not_applicable / unknown), `quality` (solid / improvable),
  `reason` (qué hizo o no hizo) y `advice` (qué hacer la próxima vez).
- `qualification`: lo que el comercial tenía que averiguar (found / missing / not_applicable) y lo que dijo el prospecto.
- `objections`: lo que dijo el prospecto (`said`), lo que respondió el comercial (`reply`), cómo quedó
  (`resolution`) y qué hacer (`what_to_do`).

La llamada está en `evals/C04/real/.cache/transcripts/<memo_id>.txt`. Léela entera antes de juzgar.
Los turnos S1/S2 NO son fiables: decide quién habla por lo que dice. La transcripción tiene ruido de
reconocimiento de voz (palabras sueltas en otros idiomas, frases cortadas): no cuentes el ruido como algo dicho.

Criterios del responsable de ventas (mandan sobre el texto literal del criterio):
- Se juzga la intención del paso, no las palabras exactas. Hecho a medias, tarde o flojo es "met" +
  "improvable", nunca "missed". "missed" solo si no hizo nada de lo que pide el paso.
- Seguimientos / confirmaciones / reagendados: solo cuenta la apertura (recordar el contacto previo
  basta); el resto "not_applicable" salvo que lo haga (entonces "met").
- Llamadas que se cortan en la puerta (mal momento, recepción, persona equivocada): solo la apertura.
- Cuando el prospecto cierra la llamada (dice que no, que le mandes un correo, que no es él), los pasos
  posteriores al que estaba el comercial son "not_applicable", aunque el comercial insista.
- "Hemos conectado por LinkedIn" cuenta como motivo de apertura.
- Si un paso pide "y el prospecto responde", basta con que el comercial lo pregunte. Preguntar por el
  dolor cuenta aunque el prospecto diga que no lo tiene.
- Los ejemplos entre paréntesis de un criterio son ejemplos, no una lista obligatoria. Solo una cifra
  explícita ("al menos 3") es un mínimo.
- Un "no lo hiciste" falso es el peor error: hace que el comercial deje de fiarse del coaching.

Qué es un buen consejo y una buena lectura de las objeciones:
- El consejo apunta a un momento concreto de ESTA llamada y da las palabras a probar. Un consejo que
  valdría para cualquier llamada ("pregunta por el dolor") vale poco. Uno que contradice lo que pasó
  (pedir una demo a quien acaba de decir que no tiene el problema) es malo.
- Una objeción bien recogida usa la frase del prospecto con sentido completo y la respuesta real del
  comercial (no un "sí" suelto ni ruido). Distingue "no tengo el problema" (no se rebate: se comprueba
  una última hipótesis o se cierra bien) de una objeción a rebatir, y de "ya lo tengo resuelto con otra
  cosa" (se busca lo que no le funciona).
- Una respuesta genérica del playbook que no encaja con lo que dijo el prospecto vale menos que una
  adaptada a sus palabras. Una adaptada que inventa funciones, cifras o clientes es mala.
- Faltar una objeción importante que el prospecto planteó es un fallo; repetir la misma dos veces también.

Para cada llamada, devuelve:
- `steps`: por cada step_id de `steps_def`:
  `fair_status`: "met" | "met_improvable" | "missed" | "not_applicable";
  `A_ok`, `B_ok`: true si el status (+quality) de esa versión coincide con el justo
  ("met"+"solid" = met; "met"+"improvable" = met_improvable);
  `better_text`: "A" | "B" | "same": qué `reason` + `advice` es más cierto y útil para este paso.
- `objections`: `better`: "A" | "B" | "same"; `A_missing`, `B_missing`: objeciones importantes que esa
  versión no recoge (texto corto); `A_wrong`, `B_wrong`: errores (respuesta mal atribuida, ruido citado,
  duplicada, consejo que no encaja o inventa).
- `overall`: "A" | "B" | "same": qué versión le darías al comercial.
- `why`: ≤30 palabras.

Salida: un JSON lista, en el mismo orden que la entrada:
[{"memo_id", "steps": {"<step_id>": {fair_status, A_ok, B_ok, better_text}}, "objections": {better, A_missing, B_missing, A_wrong, B_wrong}, "overall", "why"}]
