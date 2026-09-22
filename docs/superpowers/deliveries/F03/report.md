# Informe F03

Estado: formato mínimo en `feat/vocify-v1`. `prepare_brief` distingue «sin conversación», «no quedó nada» y una lectura a medias. El `GET /api/v1/briefs` usa esa lectura. La extensión todavía no abre `screen-contact`.

El brief de antes de llamar muestra como mucho tres hechos. Sin conversación: «Sin conversación todavía.» Si se habló y no quedó nada: «Última vez: {fecha}. No quedó nada pendiente.» Las cuatro filas fijas quedan retiradas. Detalle en `docs/superpowers/plans/2026-09-22-vocify-v1/00-decisiones.md`.

No afecta a F10: las notas y los patrones no leen este brief.
