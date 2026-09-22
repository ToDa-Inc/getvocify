# Informe F03

Estado: la extensión pinta el brief al abrir un contacto y lo esconde si hay captura. Otro contacto no reutiliza el texto. `GET /api/v1/briefs` ya distingue sin conversación, nada pendiente y lectura a medias.

El brief de antes de llamar muestra como mucho tres hechos. Sin conversación: «Sin conversación todavía.» Si se habló y no quedó nada: «Última vez: {fecha}. No quedó nada pendiente.» Las cuatro filas fijas quedan retiradas. Detalle en `docs/superpowers/plans/2026-09-22-vocify-v1/00-decisiones.md`.

No afecta a F10: las notas y los patrones no leen este brief.
