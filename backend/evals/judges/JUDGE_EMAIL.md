# Juez de emails de follow-up

Para cada llamada tienes el transcript (léelo entero) y el borrador de email que Vocify propone
al comercial para enviar al prospecto después de la llamada (`draft.subject`, `draft.body`).
`label_email` dice si alguien que leyó la llamada cree que hacía falta un email y qué debía llevar.

Puntúa cada borrador:
- `fits_call` (true/false): el email tiene sentido para lo que pasó (si no hacía falta email —no
  contestó, era una prueba, dijo que no rotundo— un email igualmente puede valer si es breve y
  correcto; marca false si es raro enviarlo).
- `promised_covered` (true/false/null): si se prometió enviar algo (info, propuesta, invitación,
  caso), el email lo trae o lo anuncia. null si no se prometió nada.
- `invented` (n): afirmaciones falsas o no dichas (un acuerdo que no hubo, una fecha distinta, un
  dato del prospecto inventado, una reunión "confirmada" que no se confirmó).
- `wrong_date_or_name` (true/false): nombre, empresa, día u hora mal.
- `tone` 1-5: natural, de comercial real, breve; 1 = robótico o lleno de relleno.
- `send_as_is` 1-5: ¿lo enviaría un buen comercial tal cual? (5 = sí; 3 = con retoques; 1 = no).
- `issue` (≤20 palabras): el problema principal, o null.

Salida: JSON lista [{"memo_id", "fits_call", "promised_covered", "invented", "wrong_date_or_name",
"tone", "send_as_is", "issue"}]. Respuesta final: medias y totales, y los 3 problemas más frecuentes
redactados para arreglarlos de forma general.