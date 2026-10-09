# Juez A/B de la nota y los campos del CRM

Para cada llamada hay dos versiones (A y B) de lo que Vocify escribiría en el CRM: `summary` (nota),
`nextSteps` (tareas) y `fields` (campo → valor). También `must_have` y `must_not` (escritos por alguien
que leyó la llamada). La llamada está en calls/<memo_id>.txt: léela antes de juzgar.

Para A y para B por separado:
1. `fields`: para CADA campo rellenado → "ok" (lo dijo el prospecto o es un dato de contacto cierto,
   valor correcto) | "inferred" (no se dijo; deducido o mapeado de algo vago) | "wrong" (contradice la
   llamada o atribuye al prospecto lo que dijo el comercial) | "trivial" (vacío disfrazado: 0, "", unknown).
   Formato {"campo": "ok|inferred|wrong|trivial"}.
2. `missed_fields`: datos que el PROSPECTO dijo claramente y que deberían estar en un campo de los que
   la otra versión o la lista de campos muestra, pero esta versión dejó vacíos (lista de nombres de campo).
3. `note`: {"coverage": n de must_have recogidos, "invented": n de afirmaciones falsas o no dichas,
   "pitch_as_fact": n de cosas del discurso del comercial presentadas como del prospecto,
   "filler": n de frases vacías, "score": 1-5 (¿le sirve a otro comercial que abre el CRM mañana?)}.
4. `tasks`: {"ok": bool, "why": "≤12 palabras"}.

Salida: JSON lista [{"memo_id", "A": {fields, missed_fields, note, tasks}, "B": {...}}].
En tu respuesta final: por versión, totales de campos por veredicto, total de missed_fields, media de
note.score, media de coverage, total invented y pitch_as_fact, y tasks ok. Después, los 3 problemas
más frecuentes de A, redactados para arreglarlos de forma general.