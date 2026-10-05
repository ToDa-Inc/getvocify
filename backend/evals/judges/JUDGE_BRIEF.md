# Juez de briefs antes de llamar

Un SDR va a volver a llamar a un prospecto. Antes de marcar lee un brief de 1–3 líneas. Para cada
llamada tienes: `ideal` (lo que un buen jefe de ventas querría que leyera, escrito por alguien que
leyó la llamada entera) y dos briefs generados, `A` y `B`. Puedes leer la llamada en
calls/<memo_id>.txt si necesitas comprobar un dato.

Puntúa A y B por separado, de 1 a 5 en cada criterio:
- `util`: ¿le dice al SDR lo que necesita para abrir y llevar la llamada? (qué pasó, qué quedó, el gancho)
- `exacto`: ¿todo lo que dice es cierto según la llamada? (1 = algo falso o atribuido a quien no es)
- `sin_relleno`: ¿evita frases vacías tipo "breve presentación", "se habló de…", "el cliente indica…"?
- `gancho`: ¿le da un motivo concreto para la llamada / una forma de abrir?
Y `peor_fallo`: una frase con el problema más grave de cada uno (o null).

Salida: JSON lista [{"memo_id", "A": {util, exacto, sin_relleno, gancho, peor_fallo}, "B": {...}}].
Al final, en tu respuesta: medias por criterio de A y de B, y los 3 patrones de fallo más
frecuentes de A con ejemplos (memo_id), para poder arreglarlos de forma general.