# Juez del coaching paso a paso

Para cada llamada tienes el guion (`steps`: id, nombre, criterio) y lo que Vocify le dice al comercial
en cada paso (`verdicts`: status, quality, reason, advice). La llamada está en calls/<memo_id>.txt
(los turnos S1/S2 NO son fiables: decide quién habla por el contenido).

Criterios del responsable de ventas (mandan sobre el texto literal del criterio):
- Se juzga la intención del paso, no las palabras exactas.
- Seguimientos / confirmaciones / reagendados: solo cuenta la apertura (recordar el contacto previo
  basta); el resto "no aplica" salvo que lo haga (entonces "hecho").
- Llamadas que se cortan en la puerta (mal momento, recepción, persona equivocada): solo la apertura.
- "Hemos conectado por LinkedIn" cuenta como motivo de apertura.
- Si un paso pide "y el prospecto responde", basta con que el comercial lo pregunte.
- "Datos de la empresa" pide al menos 3 datos.
- "Cerrar la meeting" no lo juzga la IA (lo declara el comercial): ignóralo.

Trata TODOS los pasos con el mismo cuidado. Para cada paso de cada llamada:
- `fair_status`: el status justo: "met" | "met_improvable" | "missed" | "not_applicable".
- `vocify_ok`: true si el veredicto de Vocify (status + quality) coincide con el justo
  ("met"+"solid" = met; "met"+"improvable" = met_improvable).
- `reason_true`: true si el `reason` de Vocify es cierto según la llamada.
- `advice_useful`: solo si hay `advice`: true si es concreto, accionable y propio de esta llamada.
- `note`: ≤15 palabras si algo falla.

Salida: JSON lista [{"memo_id", "steps": {"<step_id>": {fair_status, vocify_ok, reason_true, advice_useful, note}}}].
En tu respuesta final: por paso, n juzgados y % vocify_ok; total de "met_improvable" justos vs los que
Vocify marcó así; % reason_true; % advice_useful; y los 3 patrones de error más frecuentes (en
cualquier paso), redactados para arreglarlos de forma general.