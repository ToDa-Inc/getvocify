# Cierre de Vocify V1

Una entrega no está cerrada porque sus tests pasen. Está cerrada solo cuando las cuatro columnas de su fila son sí.

Este archivo es la referencia de cierre. Sustituye el hábito de marcar Definition of Done con un test de contrato y dejar fuera la spec de producto.

## Qué manda cada documento

| Documento | Manda | No manda |
|---|---|---|
| `proposed_plan.md` | Alcance, orden, bloqueos | Cómo se ve una pantalla |
| `00-contracts.md` | Campos, estados, `null`, rutas, permisos | UX |
| Plan de la entrega (`01`–`16`) | Spec funcional, estados de UI, edge cases, Definition of Done | Interfaces de otras features |
| `docs/features/PLAN_INTEGRACION.md` | Cómo se concatenan web, extensión y desktop | Un JSON nuevo |
| `00-decisiones.md` | Decisiones ya tomadas. No se reabren | El resto de la spec |
| Skill `vocify-ux-coherence` | Menos información, menos clics, un solo producto, texto de IA corto, peso visual proporcional | Contratos |

Si dos fuentes chocan, gana `00-decisiones.md` en lo que cubre. Si no hay decisión, gana la spec de la entrega para esa feature y `PLAN_INTEGRACION.md` para cómo se sientan juntas.

## Regla de cierre

Cada fila necesita las cuatro:

1. **Contrato.** La interfaz producida coincide con el Cxx de `00-contracts.md`.
2. **DoD.** Cada casilla del Definition of Done tiene prueba ejecutada, o una línea en `00-decisiones.md` que la aparta.
3. **Spec de producto.** La persona ve lo que describe la sección Frontend de esa entrega: foco, acción principal, vacío, carga, error, texto corto. Verlo en la superficie, no inferirlo de un test de librería.
4. **Superficie.** Web, extensión, desktop u overlay, según esa feature. Un hueco en la superficie que la spec nombra deja la fila abierta.

Hueco en 3 o 4: la fila sigue abierta aunque el informe diga DONE.

Checklist de la skill, dentro de la columna Spec:

- Reutiliza tokens y componentes que ya existen (`THEME_TOKENS`, papel, pills).
- Una acción principal. Lo ocasional es compacto.
- Vacío, carga y error diseñados.
- Texto de IA corto y concreto. Emails incluidos.
- Transcripción en vivo ya unida por hablante.
- Idioma, login alternativo y preferencias no ocupan el espacio principal.

## Tabla

Estado al 24 sep 2026. `sí` solo si la columna está cumplida en el producto, no en el informe.

| Entrega | Contrato | DoD | Spec de producto | Superficie | Sigue abierto |
|---|---|---|---|---|---|
| F01 captura | sí | sí, firma apartada en decisiones | no: falta DMG usable con logo | desktop | Instalador interno |
| F02 follow-up | sí | sí | no: el correo no está forzado a ser específico | web, extensión, desktop | Prompt del seguimiento |
| F0 inteligencia | sí | sí, worker apagado en código; local puede encenderlo | n/a, no es pantalla | backend | Flag de producción sigue apagado |
| F08 playbooks | sí | no: falta el recorrido publicar visto | no: la lista compite con formularios de importación | web settings | Aviso, un editor, publicar |
| F07 Ask | sí | casillas marcadas; la de historial no se recorrió en UI | parcial: panel, fase «Leyendo el CRM», scroll si estás al final, confirmación en tarjeta. Falta ver un `202` real | web | Recorrido con una pregunta real |
| F04 prioridad | sí | sí | parcial: debe vivir dentro de Hoy, sin segundo vacío | web | Un solo vacío cuando no hay nada |
| F05 Hoy | sí | sí en tests; el informe admite que no hubo UI real | parcial: Hoy es la home, sin saludo (manda `PLAN_INTEGRACION` §1.3) | web | Estados de primera visita vistos en pantalla |
| F06 cola | sí | sí | parcial: la cola existe; no es el bucle de la extensión | web | Cola en extensión |
| F03 brief | sí, formato mínimo | walk de extensión apartado en decisiones | parcial: líneas existen; el vacío y el estilo en ficha eran invisibles | extensión, y la misma lista en web/desktop | `screen-contact` como entrada |
| F10 notas | sí | offset exacto apartado | parcial | memo | Dónde se ve la nota según superficie |
| F09 scoring | sí | sí | parcial: sin playbook no hay nota; la UI no lo explica en el momento | memo, equipo | Omitir puntuación de forma visible |
| F14 meeting | sí | sí | no: la tarjeta flotante no está comprobada fuera de la ventana | desktop overlay | Pastilla, no ventana nueva |
| F11 brief posterior | sí | sí | parcial | memo | Cuándo se destaca |
| F12 live | sí en API | no: cuatro casillas nativas abiertas | no | overlay desktop | Minimizada, fullscreen, una sola pastilla |
| F13 informe | sí | sí | parcial: la página existe; el email no se juzgó contra slop | web, email | Mismo snapshot, texto corto |
| F15 equipo | sí | no: falta el walk contra API local | parcial: tarjetas sí; no es la home del manager | web | Coaching primero, gráficos después |

## Orden para completar

No se abre una feature nueva. Cada hueco se cierra en la fila que ya existe.

1. Home web: Hoy, contactos y grabar en un solo flujo. Actividad como recientes.
2. Preguntar: panel lateral, historial, espera real, confirmación en el turno.
3. Playbook: lista primero, un editor, publicar visto.
4. Extensión: brief en la ficha, vacío honesto, oculto al grabar.
5. Desktop: turnos unidos, pastilla con la ventana minimizada.
6. Follow-up e informe: texto de modelo corto y específico.
7. DMG interno con logo. Firma Apple sigue fuera.

Cuando las cuatro columnas de una fila son sí, esa fila se cierra aquí. Cuando las dieciséis lo son, V1 está cerrado.
