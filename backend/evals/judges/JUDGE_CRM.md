# Juez de la nota y los campos del CRM

Después de cada llamada, Vocify escribe en el CRM una nota (`summary`, markdown), unas tareas
(`nextSteps`) y rellena campos (`fields`: nombre del campo → valor). Para cada llamada tienes eso,
más `must_have` (hechos que la nota debería recoger, según alguien que leyó la llamada entera) y
`must_not` (cosas que no deberían aparecer). La llamada está en calls/<memo_id>.txt.

Para cada llamada:
1. `fields`: para CADA campo rellenado, un veredicto:
   - "ok": lo dijo el prospecto (o es un dato de contacto/empresa cierto) y el valor es correcto;
   - "inferred": no se dijo, el modelo lo dedujo o lo mapeó desde algo vago;
   - "wrong": contradice la llamada, o atribuye al prospecto lo que dijo el comercial;
   - "trivial": un valor vacío disfrazado (0, "none", "unknown") o irrelevante.
   Formato {"campo": {"v": "ok|inferred|wrong|trivial", "why": "≤12 palabras"}}.
2. `note`: {"coverage": cuántos must_have recoge (n de N), "invented": lista de afirmaciones de la
   nota que no son ciertas o no se dijeron, "pitch_as_fact": lista de cosas que son el discurso del
   comercial presentadas como situación del prospecto, "filler": lista de frases vacías,
   "missing_key": lo más importante que falta (≤15 palabras), "score": 1-5 (¿le sirve a otro
   comercial que abre el CRM mañana?)}.
3. `tasks`: {"ok": bool, "why": "≤15 palabras"} — ¿las tareas son las correctas (ni sobran ni faltan)?

Salida: JSON lista [{"memo_id", "fields": {...}, "note": {...}, "tasks": {...}}].
En tu respuesta final: totales de campos por veredicto, media de note.score, y los 3 patrones de
fallo más frecuentes (nota y campos) con ejemplos, redactados para arreglarlos de forma general.