# Design · F16 — Espacio del comercial

> Plan Lista 2 · E10. Contrato: [`spec.md`](./spec.md). Maqueta a 1440 px: [`mock.html`](./mock.html).
> Aprobado por el founder el 26 sep 2026 (D5, D7, D12 y §7 tal como están).

## 0. Resumen (5 líneas)

1. `/dashboard` pasa a ser **la casa del comercial**: una sola columna con cinco secciones en orden fijo (Reuniones de hoy, Falta tu OK, A quién llamar, Próximas, Hecho hoy) y un **panel de contacto** a la derecha.
2. **Maestro-detalle:** la primera tarjeta ya viene seleccionada, así que la preparación de la siguiente llamada está siempre a la vista. La acción principal es una sola: «Llamar a {nombre}».
3. **La casa es la cola.** El reductor de F06 (`shared/ui/queue.js`) maneja la selección: `Enter` llama, `n` pasa a la siguiente y ↑/↓ se mueven. No hace falta un modo aparte de «Empezar a llamar».
4. **El dialer es el mismo.** La instancia montada en `DashboardLayout` se ancla al pie del panel; el brief sigue visible durante la llamada y al colgar el panel enseña CRM, confirmación y follow-up.
5. Casi todo es reutilizado. Lo nuevo: `RepHome`, `ContactPanel`, un compositor puro `shared/ui/home.js` y tres lecturas de backend. Todo detrás de `REP_WORKSPACE_ENABLED`.

---

## 1. Estado actual (qué hay y qué falla para quien vive aquí)

| Pieza | Dónde | Qué hace hoy | Qué le falta al comercial que pasa el día aquí |
|---|---|---|---|
| Rutas | `src/App.tsx` | `/dashboard` → `DashboardLayout` + `DashboardHome`; `memos/:id` → `MemoDetail`; `ask` redirige a `/dashboard` con `{ask:true}`; `insights` → `TeamInsightsPage`; `settings/*` → `SettingsLayout` | Nada: la casa vive en la misma ruta índice |
| Layout y menú | `src/components/dashboard/DashboardLayout.tsx` | Sidebar `w-60`: Inicio, Notas de voz, Copiloto (beta), Preguntar, Equipo (solo `managers`), Ajustes, Llamar. Campana (`ReportBell`) junto al logo. Tarjeta de planes con «Reservar una demo» al pie. Cabecera `h-14` con usuario y salir | Para un miembro sobran Copiloto (beta, directo en web), la tarjeta de planes y «Notas de voz» como nombre (ya no son solo notas de voz: E1 trae llamada, reunión y visita) |
| Home | `src/pages/dashboard/DashboardHome.tsx` | `max-w-3xl` centrado: `TodayPanel` + `ActivityPanel` («Recientes») | Dos listas de «a quién llamar» separadas (Hoy y `ContactPriorities`), sin reuniones, sin follow-ups, sin tareas futuras, sin «hecho hoy». El ancho de 1440 px no se aprovecha |
| Hoy | `src/features/today/components/TodayPanel.tsx`, `TodayItemList.tsx`, `TodayCardActions.tsx`, `ContactPriorities.tsx`, `src/lib/today.ts` | Tarjetas de papel con nombre, empresa, motivo y cita. Acciones solo con icono (llamar, CRM, descartar, deshacer). «Empezar a llamar» es un icono (`ListNumbers`). Máx. 7 (`backend/app/services/hoy/signals.py`, `DEFAULT_LIMIT`) | No hay una acción principal visible. La preparación no se ve antes de llamar: el brief (`ContactBrief`) solo aparece en `MemoDetail`, es decir, **después** |
| Cola F06 | `shared/ui/queue.js` (`queueReducer`, `QUEUE_KEYS`), `src/lib/today-queue.ts` | idle → queue → calling → review → siguiente. `Enter` llama, `s` salta, `Esc` sale; en revisión `n` sigue | Vive como un modo aparte que sustituye la lista por una sola tarjeta |
| Dialer | `src/components/dashboard/calling/FloatingDialer.tsx`, `DashboardDialer.tsx`, `src/features/calling/DialerFocusProvider.tsx` | Cristal flotante 340 px abajo a la derecha. En llamada: iniciales, nombre, tiempo, silenciar, «Colgar». En reposo: buscador y `TodayDialerCards` | Durante la llamada no hay brief. Al colgar no pasa nada en pantalla: el comercial tiene que ir a buscar la conversación |
| Revisión | `src/pages/dashboard/MemoDetail.tsx` | Transcripción + `ContactBrief`, objeciones, `MeetingProposalReview`, `PostInteractionBrief`, `CoachingScore`, `FollowupCard`, `HubSpotSyncPreview` | Correcta para la revisión completa. Se mantiene |
| Follow-up | `src/components/dashboard/FollowupCard.tsx` (`<v-followup>`, `shared/ui/compose.js`) | Borrador con destinatario, asunto, cuerpo, Enviar, WhatsApp, Copiar. Polling mientras se escribe | Solo se ve dentro de `MemoDetail`; los follow-ups sin enviar no aparecen en ningún sitio |
| Preguntar | `src/features/ask/components/AskPanel.tsx` en el `aside` derecho de `DashboardLayout` (`max-w-md`) | Panel lateral con composer abajo; respuestas con `TodayCardActions` (F07.06) | Encaja: ocupará la misma columna derecha que el panel de contacto |
| Campana | `src/components/dashboard/ReportBell.tsx` | Popover: «Informes» + «Vocify hizo» (F13) | Se queda donde está |
| Ajustes | `src/pages/dashboard/settings/SettingsLayout.tsx` | Subnav en pastillas: CRM, Llamadas, Oferta, Glosario, Resúmenes, Proceso, Equipo, Uso, Facturación | E6 añade «Tu forma de escribir» aquí. Nada más cambia |
| Equipo | `src/pages/dashboard/TeamInsightsPage.tsx`, `src/features/team-insights/components/*` | Solo owner/admin; adherencia por comercial en orden alfabético (F15) | Sin cambios. Nunca aparece en la casa |
| Primitivas | `src/components/ui/button.tsx` (pill; `default`, `outline`, `ghost`, `link`), `icon-action.tsx`, `sheet.tsx`, `skeleton.tsx`, `collapsible.tsx`, `tooltip.tsx`, `popover.tsx` | — | Bastan todas |
| Tokens | `src/styles/tokens.css` (de `shared/tokens/tokens.json`), `src/index.css`, `src/lib/theme/materials.css`, `src/lib/theme/tokens.ts` (`THEME_TOKENS`), `tailwind.config.ts`, `shared/ui/vocify-ui.css` | Crema `40 33% 96%`, tinta `30 10% 14%`, bronce `35 25% 35%`, papel blanco con filete, `rounded-xl` = 16 px, pastillas, Geist 400, 150 ms | Se usan tal cual. Cero tokens nuevos |

**Extensión** (`chrome-extension/popup/index.html`, `popup.js`): en la ficha de HubSpot pinta el brief (`#contact-brief`, `paintContactBrief` con `shared/ui/brief.js`) encima del botón de grabar. Revisión con propuesta de reunión (`shared/ui/meeting-proposal.js`). **No pinta la lista de Hoy** (existe `v-today-card` pero no se usa).
**Desktop** (`desktop/lib/home-brief.js`): usa `contactBriefDisplayLines`, las mismas 0–3 líneas.

---

## 2. Recorrido de un día y momentos críticos

| Hora | Momento | Qué ve | Qué hace | Crítico porque |
|---|---|---|---|---|
| 8:30 | Abre Vocify | Fecha, pulso, 1 reunión, 3 cosas en Falta tu OK, 5 llamadas; el panel ya enseña la primera | Lee en 10 s qué toca | **Primer vistazo.** Si hay que pensar, vuelve al CRM |
| 8:32 | Despeja lo pendiente | Confirmación de etapa (E7), 2 follow-ups listos | Confirmar (1 clic); Abrir → Enviar en el panel | Nada pendiente en silencio. Cada fila, un clic |
| 8:40 | Antes de marcar | 3 líneas + etiqueta «Pitch hecho · falta cualificar» | Lee 5 s y pulsa `Enter` | **El brief tiene que caber y leerse sin scroll** |
| 8:41 | En llamada | Brief arriba, barra de llamada abajo, tarjeta «En llamada · 03:12» | Habla | No mover nada en pantalla mientras habla |
| 8:47 | Cuelga | «Guardado en HubSpot» o «Revisar y guardar», confirmación E7 y follow-up escribiéndose | Enviar, o `n` | **Primer «wow»:** CRM hecho y follow-up listo sin tocar nada |
| 8:48 | Sin respuesta | La selección baja sola; nota «Sin respuesta · 8:48» en la tarjeta | Sigue | No dar por hecha una llamada fallida |
| 11:30 | Reunión | Fila de reunión con «Falta del playbook: decisor, presupuesto» | Prepara 1 min | Llegar sabiendo qué cualificar |
| 16:00 | Tarde | Hecho hoy · 9; Próximas con lo de mañana | Revisa Próximas | Cerrar el día sabiendo qué viene |
| Viernes | Semana | Informe en la campana (F13) | Lo lee si quiere | Sin comparativas |

---

## 3. Decisiones de diseño

| # | Decisión | Alternativas descartadas | Por qué |
|---|---|---|---|
| D1 | **Maestro-detalle con panel fijo a la derecha desde 1280 px**; el mismo `ContactPanel` en `Sheet` por debajo | Desplegar la tarjeta en línea; abrir una página por contacto | Llamar es lo más frecuente del día: la preparación de la siguiente llamada tiene que estar siempre a la vista sin clic. Desplegar en línea empuja la lista y la reordena visualmente; una página rompe «sin saltar de pantalla» |
| D2 | **La primera tarjeta de A quién llamar sale seleccionada** | Panel vacío hasta elegir | Un clic menos en la acción más repetida. El panel nunca está vacío en escritorio ancho |
| D3 | **Una sola acción principal: «Llamar a {nombre}»** (pastilla bronce del panel). Tras colgar, pasa a «Enviar» (follow-up) o a «Revisar y guardar» | Botón «Empezar a llamar» en la cabecera + botones en cada tarjeta | Dos pastillas llenas compiten. Con la selección automática, «Empezar a llamar» ya es «Llamar a la primera»; la cola sigue existiendo (ver D4) |
| D4 | **La casa es la cola.** El índice de `queueReducer` es la tarjeta seleccionada | Mantener el modo cola que sustituye la lista | Mismo bucle de F06 (llamar → revisar → siguiente) sin cambiar de vista ni aprender un modo. Se conservan `Enter`, `s`, `n`, `Esc` |
| D5 | **Orden fijo de secciones:** Reuniones de hoy → Falta tu OK → A quién llamar → Próximas → Hecho hoy | Mezclarlo todo en una lista por prioridad | Las reuniones marcan el día (tienen hora). Lo de un clic va antes para despejar en un minuto. Llamar es el grueso y el protagonista. Lo futuro y lo hecho, abajo y en voz baja |
| D6 | **Falta tu OK agrupa confirmaciones (E7), follow-ups listos (F02) y conversaciones por revisar** en un solo bloque de filas compactas | Tres secciones separadas | Es un solo concepto: «Vocify ya lo hizo, falta tu OK» (principio 4 de `EXPERIENCIA_PRODUCTO.md`). Tres títulos para una o dos filas es ruido |
| D7 | **Tope de 7 tarjetas de Hoy** entre reuniones, confirmaciones y llamadas (plan §1.2 y §6). Tres confirmaciones o más → una fila. Los follow-ups no cuentan (no son tarjetas de Hoy); se ven 3 + «N más» | Contar solo llamadas | El plan fija 7 «tarjetas» en total. Confirmado por el founder |
| D8 | **«N más cuando termines estos»** es texto, no enlace | Enlace «Ver todos» | Foco: al resolver, sube la siguiente. `/today` no devuelve las plegadas y abrirlas invita a reordenar |
| D9 | **Las tarjetas no llevan botones fijos.** Clic = seleccionar. Al pasar el ratón aparece un icono de teléfono (llamada en 1 clic). Descartar y posponer viven en el panel | Mantener los tres iconos por tarjeta | Las acciones del panel ya cubren a la seleccionada; repetirlas en 7 tarjetas es ruido. Llamar sigue a un clic desde cualquier tarjeta |
| D10 | **Preguntar ocupa la columna derecha en lugar del panel de contacto**; al cerrarlo vuelve el contacto | Dos paneles a la vez | Un solo panel lateral a la vez. Es el mismo `aside` que hoy |
| D11 | **Dialer anclado al pie del panel** con la misma instancia (`placement` como cambio de clase, sin portal) | Segundo dialer dentro del panel; mover el nodo con portal | Un portal o una segunda instancia remonta el SDK de voz y corta la llamada. Fuera de la casa, el dialer vuelve a flotar como hoy |
| D12 | **La home es la misma para owner/admin** (su propio día). Equipo, en el menú | Home de manager = Equipo (`PLAN_INTEGRACION.md`) | En equipos de 5 a 10, el head of sales también vende. Equipo sigue a un clic y sin ranking |
| D13 | **El coaching no sale en la casa ni en «Después de la llamada»**; sigue en `MemoDetail` (`CoachingScore`) y en el informe | Una nota de coaching al colgar | En reuniones recientes se acordó que el coaching no bloquee el trabajo y que el comercial elija cuándo verlo. Al colgar, lo único que importa es el CRM y el follow-up |

---

## 4. Wireframes

### 4.1 Home a 1440 px (panel abierto en la primera tarjeta)

```
┌─────────────┬──────────────────────────────────────────────────────────────────────────────────────────┐
│ ◖Vocify Beta│                                                     Lucía Ferrer        ⇥    (LF)        │ h-14
│         🔔  │                                                     Kinetic Software                     │
│             ├──────────────────────────────────────────────────┬───────────────────────────────────────┤
│ ◉ Hoy       │  Hoy  martes, 29 de septiembre              [🎙]  │ (MO) Marina Ortiz                  ↗  │
│ ○ Conversac.│  3 llamadas hoy, todas guardadas en HubSpot      │      Operaciones · Tenéis Solutions   │
│ ○ Preguntar │                                                  │                                       │
│ ○ Llamar    │                                                  │ Antes de llamar                       │
│ ○ Ajustes   │  Reuniones de hoy                                │ 11 sep: «se nos quedan leads sin      │
│             │  ┌────────────────────────────────────────────┐  │ llamar los viernes»                   │
│             │  │ 11:30  Demo con Pedro Sanz · Grupo Rovira   │  │ Pidió que la llamaras hoy para ver    │
│             │  │        Falta del playbook: decisor, presup. │  │ números.                              │
│             │  └────────────────────────────────────────────┘  │ ▎Precio: compáralo con lo que cuesta  │
│             │                                                  │ ▎un comercial más.                    │
│             │  Falta tu OK                                     │ (Pitch hecho · falta cualificar)      │
│             │  ┌────────────────────────────────────────────┐  │                                       │
│             │  │ Confirma: reunión jue 1 oct, 11:00 con      │  │ ( Llamar a Marina      ↵ )           │
│             │  │ Andrea Vidal          (Confirmar)  Revisar  │  │ +34 612 48 90 21                      │
│             │  │ Etapa → Meeting booked · de tu llamada…     │  │ Posponer a mañana · Descartar         │
│             │  ├────────────────────────────────────────────┤  │ ───────────────────────────────────── │
│             │  │ Follow-up para Nuria Gil · «Resumen…»  Abrir│  │ Conversaciones                        │
│             │  │ Follow-up para Iván Rey · «El caso…»   Abrir│  │ 22 sep · Llamada · 14 min             │
│             │  └────────────────────────────────────────────┘  │ Dudó por el precio; quedó en llamarla │
│             │                                                  │ el martes con números.                │
│             │  A quién llamar                                  │ 11 sep · Visita                       │
│             │  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  │ Primera visita. Le interesa para el   │
│             │  ┃ Marina Ortiz  Tenéis Solutions   Compromiso┃  │ equipo de Valencia.                   │
│             │  ┃ Pidió que le llamaras.                     ┃  │                                       │
│             │  ┃ «Llámame el martes y lo vemos con números» ┃  │                                       │
│             │  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛  │                                       │
│             │  ┌ Jordi Puig  Loop Energía      Sin respuesta ┐  │                                       │
│             │  │ Le escribiste el 16 sep («Propuesta piloto  │  │                                       │
│             │  │ Q4») y no ha respondido.                    │  │                                       │
│             │  └─────────────────────────────────────────────┘  │                                       │
│             │  ┌ Carmen Ruiz  Hostelia      Dolor confirmado ┐  │                                       │
│             │  ┌ Álvaro Méndez  Frutas L.   Objeción abierta ┐  │                                       │
│             │  ┌ Sofía Navarro  Dentalia          Sin llamar ┐  │                                       │
│             │  2 más cuando termines estos                     │                                       │
│             │                                                  │                                       │
│             │  Próximas                                        │                                       │
│             │  Mañana     Enviar la propuesta a A.… En el CRM  │                                       │
│             │  Jue 1 oct  Llamar a Raúl Soler…      En el CRM  │                                       │
│             │  Lun 5 oct  Mandar el caso de éxito…             │                                       │
│             │                                                  │                                       │
│             │  Hecho hoy · 4                               ⌄   │                                       │
└─────────────┴──────────────────────────────────────────────────┴───────────────────────────────────────┘
   240 px           columna de la lista (contenido máx. 680 px)          panel 400 px, papel blanco
```

### 4.2 Home a 1024 px (sin panel fijo)

```
┌──────────────┬───────────────────────────────────────────────────────────┐
│ menú 240 px  │ Hoy  martes, 29 de septiembre                        [🎙]  │
│ (el actual,  │ 3 llamadas hoy, todas guardadas en HubSpot                 │
│  plegable    │                                                            │
│  < lg)       │ Reuniones de hoy · Falta tu OK  (igual que a 1440)         │
│              │ A quién llamar                                             │
│              │ ┌ Marina Ortiz  Tenéis Solutions        Compromiso  (📞) ┐  │
│              │ │ Pidió que le llamaras.                                  │  │
│              │ └─────────────────────────────────────────────────────────┘  │
│              │ … (el icono de teléfono se ve siempre: no hay panel)        │
└──────────────┴───────────────────────────────────────────────────────────┘
Clic en la tarjeta → Sheet derecha (400 px) con el mismo ContactPanel. Esc cierra.
```

### 4.3 Panel de contacto (detalle)

```
┌───────────────────────────────────────┐
│ (MO) Marina Ortiz                  ↗  │  ↗ = Abrir en el CRM (IconAction)
│      Dir. de Operaciones · Tenéis     │  ✕ solo en Sheet
│                                       │
│ Antes de llamar                       │  capsLabel 13 px
│ 11 sep: «se nos quedan leads sin      │  gancho (E3)        · 15 px tinta
│ llamar los viernes»                   │
│ Pidió que la llamaras hoy para ver    │  por qué llamas (E3)
│ números.                              │
│ ▎Precio: compáralo con lo que cuesta  │  qué decir (E3); filete bronce = viene
│ ▎un comercial más.                    │  del playbook del equipo
│ (Pitch hecho · falta cualificar)      │  v-chip
│                                       │
│ ( Llamar a Marina                 ↵ ) │  pastilla bronce, la única llena
│ +34 612 48 90 21                      │  12 px, apagado
│ Posponer a mañana · Descartar         │  acciones de texto 13 px
│ ───────────────────────────────────── │
│ Follow-up pendiente                   │  solo si existe (F02)
│ «Números que vimos» · listo · Abrir   │
│ ───────────────────────────────────── │
│ Conversaciones                        │  máx. 3; clic → MemoDetail
│ 22 sep · Llamada · 14 min             │
│ Dudó por el precio; quedó en…         │
└───────────────────────────────────────┘
En frío (E4): «Quién es» · «Por qué llamas» · «Cómo abrir», mismas 3 líneas y mismo sitio.
Reunión seleccionada: una línea «Reunión hoy 11:30» encima de «Antes de llamar» y «Falta del playbook: …».
```

### 4.4 Dialer en llamada (panel)

```
┌───────────────────────────────────────┐
│ (MO) Marina Ortiz                  ↗  │
│ Antes de llamar                       │  el brief NO se mueve ni se oculta
│ 11 sep: «se nos quedan leads…»        │
│ Pidió que la llamaras hoy…            │
│ ▎Precio: compáralo con…               │
│ (Pitch hecho · falta cualificar)      │
│                                       │
│ Conversaciones …                      │
│                                       │
│ ╭───────────────────────────────────╮ │  barra de cristal (en vivo) =
│ │ (MO) Marina Ortiz  03:12  🎙  Colgar│ │  DashboardDialer con placement="panel"
│ ╰───────────────────────────────────╯ │
└───────────────────────────────────────┘
Lista: la tarjeta de Marina muestra «● En llamada · 03:12» en bronce. Selección bloqueada.
```

### 4.5 Después de la llamada

```
┌───────────────────────────────────────┐
│ (MO) Marina Ortiz                  ↗  │
│ Llamada de 6 min · ✓ Guardado en HubSpot │  o «Procesando la llamada…» (una línea)
│                                       │  o «( Revisar y guardar )» si no hay autoaprobación
│ Confirma: reunión jue 1 oct, 11:00 ·  │  E7, solo si aplica
│ etapa → Meeting booked                │
│               (Confirmar)  Revisar    │
│ ───────────────────────────────────── │
│ Follow-up                             │  <v-followup> (FollowupCard)
│ [marina.ortiz@tenees.es]              │  chip destinatario
│ Números que vimos hoy                 │  asunto 450
│ Hola Marina: como quedamos, te paso…  │
│ ( Enviar )  (WhatsApp)  Copiar        │  Enviar = la acción principal ahora
│ ───────────────────────────────────── │
│ Siguiente: Jordi Puig             n   │  acción de texto
└───────────────────────────────────────┘
Mientras se escribe: «Escribiendo el seguimiento…» con silueta (patrón F02).
Sin respuesta: no hay este estado; la selección baja y la tarjeta anota «Sin respuesta · 8:48».
```

### 4.6 Estados

```
Primera vez, sin CRM (miembro)           Sin CRM (owner/admin)
┌──────────────────────────────────┐     ┌──────────────────────────────────┐
│ Hoy                              │     │ Hoy                              │
│ Conecta tu CRM para preparar     │     │ Conecta tu CRM para preparar     │
│ tu día                           │     │ tu día                           │
│ Tu administrador tiene que       │     │ ( Conectar CRM )  Grabar una     │
│ conectar el CRM.                 │     │                   interacción    │
│ ( Grabar una interacción )       │     └──────────────────────────────────┘
└──────────────────────────────────┘     Sin panel en ambos casos.

CRM conectado, sin conversaciones        Sin contactos asignados
┌──────────────────────────────────┐     ┌──────────────────────────────────┐
│ A quién llamar                   │     │ Todavía no hay contactos         │
│ ┌ Sofía Navarro  Dentalia  Sin llamar┐ │ asignados para priorizar         │
│ ┌ Hugo Pardo  Kinesis     Sin llamar┐  │ Revisa tu asignación con el      │
│ …(contactos de /contact-priorities)  │ │ administrador · Mapear resp.     │
│ Panel: preparación en frío (E4) o    │ │ ( Grabar una interacción )       │
│ «Sin conversación todavía.»          │ └──────────────────────────────────┘
└──────────────────────────────────┘

Todo hecho                               Parcial (CRM caído / sin permiso)
┌──────────────────────────────────┐     ┌──────────────────────────────────┐
│ Hoy                              │     │ 3 llamadas hoy…                  │
│ Nada urgente hoy. Buen momento   │     │ Información incompleta · 10:05   │
│ para prospectar                  │     │ (tarjetas verificadas, sin más)  │
│ Próximas …                       │     │ Panel: «No se pudo cargar todo.» │
│ Hecho hoy · 9  ⌄                 │     │ + líneas verificadas             │
└──────────────────────────────────┘     └──────────────────────────────────┘

Carga                                    Error
┌──────────────────────────────────┐     ┌──────────────────────────────────┐
│ Hoy                              │     │ Hoy                              │
│ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │     │ No se pudo preparar el día       │
│ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │     │ ( Reintentar )                   │
│ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │     │ Próximas y Hecho hoy siguen si   │
│ Panel: «Leyendo…» (una línea)    │     │ sus lecturas responden           │
└──────────────────────────────────┘     └──────────────────────────────────┘
Tres siluetas de papel con el respiro `v-breathe` de `shared/ui/vocify-ui.css`; sin spinners.
```

---

## 5. Proporcionalidad: cada elemento nuevo

| Elemento | Dónde | Peso visual | Por qué ese peso |
|---|---|---|---|
| Cabecera (fecha + «Hoy» + pulso) | Arriba de la columna | `pageTitle`, pulso en `body` apagado, una línea | Orienta en un vistazo. El pulso es la «tira discreta» de `EXPERIENCIA_PRODUCTO.md`, sin cifras comparativas |
| Reuniones de hoy | Primera sección, solo si hay | Fila de papel compacta; la hora en tinta y el resto en apagado | Tiene hora fija, pero es de lectura: sin botón propio |
| Falta tu OK | Segunda sección, solo si hay | Un papel con filas de una línea; `Confirmar` en `outline` pequeño, lo demás texto | Un clic por fila, sin robar la pastilla llena a Llamar |
| Tarjetas de A quién llamar | Tercera sección | Papel `p-4`, nombre 15 px, motivo 15 px tinta. La seleccionada con borde bronce/45 (el hover actual, más fuerte) | Es el grueso del día. La selección reutiliza el lenguaje del hover, no el filete bronce (ese significa «de tu equipo») |
| «N más cuando termines estos» | Bajo la última tarjeta | Texto 13 px apagado | Dice que hay más sin invitar a abrirlo |
| Próximas | Cuarta sección | Filas sin papel, 14 px; fecha y marcador «En el CRM» apagados | Es futuro: se consulta, no se actúa |
| Hecho hoy | Última, plegada | Una fila con contador y chevron (`Collapsible`) | Da cierre sin ser un panel de logros |
| Panel de contacto | Derecha, 400 px, papel con filete a la izquierda | Nombre 17 px; brief 15 px; **única pastilla llena** | Es donde se prepara y se actúa. Contenido = papel |
| Barra de llamada | Pie del panel | Cristal `glass-panel` (en vivo) | Cristal = flotante / en vivo (`PLAN_INTEGRACION.md`) |
| Icono de teléfono al pasar sobre una tarjeta | Derecha de la tarjeta | `IconAction` 36 px, solo al pasar el ratón y en foco de teclado | Llamada en un clic sin llenar la lista de botones |
| Pista de tecla (↵, n) | Dentro de la pastilla o la acción | 12 px al 60 % de opacidad | Enseña el atajo sin una pantalla de ayuda |

Qué se quita para miembros: Copiloto (beta) del menú, la tarjeta de planes y el bloque «Recientes» de la home (vive en Conversaciones).

---

## 6. Interacción

**Teclado** (solo con `REP_WORKSPACE_ENABLED`; se ignora con ⌘/Ctrl y dentro de inputs, textareas o contenteditable, como el cuerpo del follow-up):

| Tecla | Acción | Origen |
|---|---|---|
| `Enter` | Acción principal de la tarjeta seleccionada (llamar; en una confirmación, Confirmar) | F06 `QUEUE_KEYS.queue.Enter` |
| `s` | Saltar: selecciona la siguiente sin actuar | F06 |
| `n` | Tras colgar: siguiente tarjeta | F06 `QUEUE_KEYS.review.n` |
| `Esc` | Cierra `Sheet` o Preguntar; si no hay nada abierto, quita la selección | F06 |
| `↓` / `j`, `↑` / `k` | Mover la selección por todas las filas en orden visual (reunión, Falta tu OK, llamadas). Cada fila abre su contacto en el panel; en un follow-up, el panel enseña el borrador | Nuevo (navegación, sin efectos) |

**Transiciones.** 150 ms `cubic-bezier(0.16,1,0.3,1)` (`materials.css`). La selección cambia sin mover la lista. Al resolverse, la tarjeta sale con colapso de altura medida (`shared/ui/today-card.js`, `exitMotion`); con movimiento reducido, solo opacidad. El panel hace un fundido cruzado de 150 ms entre contactos, sin deslizar. Lo nuevo entra al final de su sección. **Nunca se reordena** durante una llamada ni con el panel en «Después de la llamada».

**Deshacer.** Descartar, posponer y confirmar dejan en el sitio una fila «Descartada · Deshacer» durante 5 s (`undo_deadline`, `PATCH /today/{id}`). Confirmar de E7 usa la misma ventana. Tras un 409, se refresca y se enseña el estado real.

**Llamada.** Selección bloqueada (clic en otra tarjeta → tooltip «En llamada»). Preguntar puede abrirse y sustituye al contenido del panel, pero la barra sigue en el pie. Si se sale de `/dashboard`, el dialer vuelve a su posición flotante y la llamada sigue.

---

## 7. Navegación: comercial y manager

| Entrada | Comercial (miembro) | Owner/admin | Nota |
|---|---|---|---|
| Hoy (antes «Inicio») | ✓ | ✓ | Es la casa. Mismo icono |
| Conversaciones (antes «Notas de voz») | ✓ | ✓ | Llamadas, reuniones y visitas (E1). Misma ruta `/dashboard/memos` |
| Preguntar | ✓ | ✓ | Columna derecha (D10) |
| Llamar | ✓ | ✓ | Dialer para un número o contacto fuera de Hoy. Mismo botón |
| Equipo | — | ✓ | `managers: true` como hoy. Orden alfabético, sin ranking (F15) |
| Ajustes | ✓ | ✓ | E6 añade «Tu forma de escribir» |
| Copiloto (beta) | **oculto** | ✓ | El directo vive en desktop (decisiones Lista 2); la ruta sigue existiendo |
| Tarjeta de planes | **oculta** | ✓ | «Reservar una demo» no tiene sentido para un comercial de pago |
| Campana | junto al logo | junto al logo | Sin cambios (F13) |

---

## 8. Coherencia entre superficies

| Superficie | Qué hace | Cómo conecta con la casa |
|---|---|---|
| Dashboard (casa) | Organizar el día: preparar, llamar, confirmar, enviar, preguntar | — |
| Extensión | Preparar desde la ficha del CRM (brief sobre el botón de grabar) y revisar tras grabar | Mismo texto de brief (`shared/ui/brief.js` → `/briefs`). Lo que se confirma o envía allí desaparece de la casa al volver el foco (`useToday` ya usa `refetchOnWindowFocus: true`). El popup no gana una lista de Hoy |
| Desktop | Capturar reuniones y llamadas; brief en la home de la app | Mismas 0–3 líneas (`desktop/lib/home-brief.js`). La reunión capturada entra en Falta tu OK o en Hecho hoy |
| Todas | Tokens de `shared/tokens/tokens.json`, `vocify-ui.css` (papel, chip, pastilla) | Misma etiqueta «Pitch hecho · falta cualificar» (`.v-chip`) en panel, extensión y desktop cuando E3 la entregue |

---

## 9. Componentes

**Reutilizados**

| Componente | Ruta | Uso en la casa |
|---|---|---|
| `DashboardLayout` | `src/components/dashboard/DashboardLayout.tsx` | Marco, menú, `aside` de Preguntar, dialer |
| `CallCard` / `TodayItemList` | `src/features/today/components/TodayItemList.tsx` | Tarjetas de llamada (+ prop `selected`, icono al pasar el ratón) |
| `useTodayCardActions`, `useTodayUndoClock` | `src/features/today/hooks/useTodayCardActions.ts` | Descartar, posponer, deshacer |
| `useToday` / `todayApi` | `src/features/today/hooks/useToday.ts`, `api.ts` | Tarjetas, reuniones (E5), confirmaciones (E7) |
| `ContactPriorities` (datos) | `src/features/today/components/ContactPriorities.tsx`, `src/lib/contact-priorities.ts` | Contactos sin llamar y dolor confirmado, fundidos en A quién llamar |
| `queueReducer`, `QUEUE_KEYS`, `queueKeyAction` | `shared/ui/queue.js`, `src/lib/today-queue.ts` | Selección, llamada, revisión, siguiente |
| `reduceTodayList`, `exitMotion` | `shared/ui/today-card.js` | Salida medida, foco al siguiente |
| `ContactBrief` + `brief.js` | `src/components/dashboard/memos/ContactBrief.tsx`, `shared/ui/brief.js` | Bloque «Antes de llamar» (+ etiqueta y filete cuando E3 los entregue) |
| `FollowupCard` (`<v-followup>`) | `src/components/dashboard/FollowupCard.tsx` | Follow-up en el panel y tras colgar |
| `MeetingProposalReview` / `renderMeetingProposal` | `src/components/dashboard/memos/MeetingProposalReview.tsx`, `shared/ui/meeting-proposal.js` | «Revisar» de una confirmación de reunión |
| `FloatingDialer`, `DashboardDialer`, `DialerFocusProvider` | `src/components/dashboard/calling/*`, `src/features/calling/DialerFocusProvider.tsx` | Llamada anclada al panel |
| `AskPanel` | `src/features/ask/components/AskPanel.tsx` | Columna derecha |
| `Button`, `IconAction`, `Sheet`, `Skeleton`, `Collapsible`, `Tooltip` | `src/components/ui/*` | Pastillas, iconos, panel estrecho, carga, Hecho hoy |
| `THEME_TOKENS` | `src/lib/theme/tokens.ts` | Tipografía, radios, papel |

**Nuevos (justificados)**

| Componente | Ruta propuesta | Por qué no basta lo existente |
|---|---|---|
| `composeHome()` (puro) | `shared/ui/home.js` + `home.test.js` | La regla de secciones, tope de 7, agrupado de confirmaciones y deduplicado por contacto tiene que ser una sola, testeable con `node --test` y reutilizable por desktop o extensión si algún día pintan Hoy |
| `RepHome` | `src/features/today/components/RepHome.tsx` | `TodayPanel` es una lista con modo cola; la casa es un maestro-detalle con cinco secciones. `TodayPanel` se queda intacto para el flag apagado |
| `HomeSection` | `src/features/today/components/HomeSection.tsx` | Título pequeño + contenido + «no pintar si está vacío». Diez líneas; evita repetir el patrón cinco veces |
| `ContactPanel` | `src/features/today/components/ContactPanel.tsx` | No hay vista de contacto fuera de `MemoDetail`. Compone piezas existentes (brief, follow-up, acciones, historial); se monta fijo o dentro de `Sheet` |
| `useHomeSelection` | `src/features/today/hooks/useHomeSelection.ts` | Une `queueReducer` + teclado + bloqueo en llamada |

---

## 10. Archivos a tocar

| Archivo | Cambio | Por qué |
|---|---|---|
| `backend/app/config.py` | `REP_WORKSPACE_ENABLED = False` | Flag global |
| `backend/app/services/company.py`, `backend/app/api/auth.py`, `backend/app/api/company.py` | `rep_workspace_enabled` en el resumen de empresa | Mismo patrón que `can_use_dialer` |
| `src/features/company/types.ts`, `src/features/company/api.ts` | `repWorkspace?: boolean` | Leer el flag |
| `src/pages/dashboard/DashboardHome.tsx` | Con flag → `RepHome`; sin flag → lo actual | Rollback limpio |
| `src/components/dashboard/DashboardLayout.tsx` | Menú del comercial; ocultar planes y Copiloto a miembros; la columna derecha alterna entre contacto y Preguntar; `placement` del dialer | Navegación y panel único |
| `src/components/dashboard/calling/FloatingDialer.tsx`, `DashboardDialer.tsx` | `placement: "floating" \| "panel"` como clase; exponer `onCallEnded({callSid, outcome})` y el tiempo transcurrido | Anclar sin remontar; después de la llamada |
| `src/features/calling/DialerFocusProvider.tsx` | Exponer el estado de llamada (contacto, tiempo, `callSid`) | «En llamada · 03:12» en la tarjeta y bloqueo de la selección |
| `src/features/today/components/TodayItemList.tsx` | Prop `selected`, icono al pasar el ratón, nota «Sin respuesta · hh:mm» | Reutilizar la tarjeta |
| `src/components/dashboard/memos/ContactBrief.tsx` | Etiqueta (`.v-chip`) y filete de playbook si el payload los trae | Hueco para E3/E4 |
| `shared/ui/queue.js` | `HOME_KEYS` (↑/↓/j/k) y `queueKeyAction` que ignore destinos editables | Teclado sin romper F06 |
| `src/features/today/api.ts` | Consultas `followups`, `upcoming`, `done`, `memos?status` | Datos de las secciones nuevas |
| `backend/app/api/today.py` + `backend/app/services/hoy/upcoming.py`, `done.py` | `GET /today/upcoming`, `GET /today/done` | Próximas y Hecho hoy |
| `backend/app/api/followup.py` | `GET /api/v1/followups?status=ready` | Follow-ups por enviar |
| `backend/app/api/memos.py` | Filtro `status` en `list_memos` | Conversaciones por revisar |
| `src/lib/product-catalog.ts` | Claves ES/EN (§12) | Copy |
| `docs/EXPERIENCIA_PRODUCTO.md` | Texto de §13, **tras la aprobación** | Documento de producto |
| `docs/features/MASTER_PLAN.md` | Flag en «Hoy por empresa» (T1) y estado de F16 al cerrar (T6) | Restricciones globales y regla del proceso |

---

## 11. Cómo se enchufan E3–E7

| Entrega | Dónde aparece en la casa | Qué hace F16 por ella | Sin la entrega |
|---|---|---|---|
| E2 · compromisos → tareas | Próximas: marcador «En el CRM» | `/today/upcoming` devuelve `crm_task_id` si existe | Filas sin marcador |
| E3 · brief v2 | Panel «Antes de llamar»: gancho, por qué, qué decir + etiqueta | `ContactBrief` pinta `label` como `.v-chip` y el filete si `source: "playbook"`. E3 cumple así su «tarjeta de Hoy desplegada»: es el panel | Líneas actuales de F03 |
| E4 · llamada en frío | Mismo bloque para contactos sin llamar: quién es, por qué, cómo abrir | Mismo hueco; `/contact-priorities` aporta el contacto | «Sin conversación todavía.» + motivo |
| E5 · reuniones en Hoy | Sección Reuniones de hoy; línea «Reunión hoy 11:30» en el panel | `composeHome` saca `meeting_today` a su sección; cuentan en el tope de 7 | La sección no existe |
| E6 · follow-ups | Mejores borradores en Falta tu OK y tras colgar | Nada: `<v-followup>` ya los pinta | — |
| E7 · confirmaciones | Falta tu OK y «Después de la llamada» | `composeHome` saca `confirm_pending`; `Enter` = Confirmar con 5 s de deshacer; `Revisar` abre `MeetingProposalReview` en el panel | Falta tu OK sin confirmaciones |

---

## 12. Copy nuevo (`src/lib/product-catalog.ts`)

Se reutilizan tal cual: `todayTitle`, `today_call`, `today_open`, `dismiss`, `undo`, `today_clear`, `today_no_activity`, `today_connect_title`, `today_connect_admin_detail`, `today_prepare_failed`, `today_incomplete`, `today_record`, `today_capture`, `retry`, `connect_crm`, `map_owners`, `review_assignment`, `today_signal_*`, `navAsk`, `navCall`, `navSettings`, `navInsights`, `confirmAction`.

| Clave | ES | EN |
|---|---|---|
| `navToday` | Hoy | Today |
| `navConversations` | Conversaciones | Conversations |
| `home_meetings` | Reuniones de hoy | Today's meetings |
| `home_needs_ok` | Falta tu OK | Needs your OK |
| `home_calls` | A quién llamar | Who to call |
| `home_upcoming` | Próximas | Coming up |
| `home_done` | Hecho hoy | Done today |
| `home_folded` | {count} más cuando termines estos | {count} more once these are done |
| `home_in_crm` | En el CRM | In the CRM |
| `home_pulse_calls` | {count} llamadas hoy | {count} calls today |
| `home_pulse_saved` | todas guardadas en {crm} | all saved to {crm} |
| `home_followup_row` | Follow-up para {name} | Follow-up for {name} |
| `home_review_row` | Conversación con {name} sin guardar en el CRM | Conversation with {name} not saved to the CRM |
| `home_open` | Abrir | Open |
| `home_review` | Revisar | Review |
| `home_meeting_no_time` | Hoy · sin hora | Today · no time set |
| `today_signal_pain` | Dolor confirmado | Confirmed pain |
| `today_signal_uncalled` | Sin llamar | Not called yet |
| `panel_before_call` | Antes de llamar | Before you call |
| `panel_history` | Conversaciones | Conversations |
| `panel_followup_pending` | Follow-up pendiente | Follow-up pending |
| `panel_call` | Llamar a {name} | Call {name} |
| `panel_snooze` | Posponer a mañana | Snooze until tomorrow |
| `panel_in_call` | En llamada | On a call |
| `panel_hang_up` | Colgar | Hang up |
| `panel_processing` | Procesando la llamada… | Processing the call… |
| `panel_saved` | Guardado en {crm} | Saved to {crm} |
| `panel_review_save` | Revisar y guardar | Review and save |
| `panel_no_answer` | Sin respuesta · {time} | No answer · {time} |
| `panel_next` | Siguiente: {name} | Next: {name} |
| `panel_call_failed` | Llamada fallida | Call failed |
| `done_call` | Llamada con {name} | Call with {name} |
| `done_followup` | Follow-up enviado a {name} | Follow-up sent to {name} |
| `done_confirmed` | Confirmado: {what} | Confirmed: {what} |

Las frases de motivo, reunión y confirmación («Pidió que le llamaras.», «Confirma: reunión…») las escribe el backend con plantillas (`backend/app/services/hoy/reasons.py`, E5, E7). La UI no genera texto.

---

## 13. Propuesta para `docs/EXPERIENCIA_PRODUCTO.md` (no aplicado)

Sustituye la sección «1. El Dashboard — no es un CRM, es Hoy» y la frase final de «La regla de forma»:

> ### 1. El Dashboard — la casa del comercial
>
> El comercial pasa aquí su día. Abre Vocify y ya está preparado: primero las reuniones de hoy, luego lo que solo espera su OK (una confirmación, un follow-up listo), y después a quién llamar y por qué, con un máximo de siete cosas. A la derecha, la preparación de la siguiente llamada: tres líneas que se leen en cinco segundos y un botón para llamar.
>
> Todo se hace desde aquí, sin cambiar de pantalla: preparar, llamar, confirmar, enviar el follow-up, preguntar. Al colgar, el CRM ya está guardado y el follow-up escrito.
>
> Lo que no hay: paneles de analítica, rankings, rachas ni comparativas. Una tira discreta con el pulso del día («3 llamadas hoy, todas guardadas en HubSpot») y una lista corta de lo hecho, plegada. El comercial trabaja aquí; no se mide aquí.
>
> La extensión sigue siendo la forma de preparar desde la ficha del CRM, y la app de escritorio, la de capturar reuniones. Las tres dicen lo mismo con las mismas palabras.

Y en «La regla de forma», la última frase pasa a: «El comercial trabaja en Vocify cada día, pero nunca abre un panel de analítica.»

---

## 14. Desglose de construcción (ola 2)

Orden: **T1 → (T2 ∥ T3) → T4 → T5 → T6**. Cada tarea deja la app funcionando con el flag apagado y encendido.

Comunes a todas (`.superpowers/sdd/global-constraints.md`): test en rojo antes de implementar; backend con `pytest` del archivo concreto y la suite completa antes de commitear; frontend con `make test-js` (1 fallo previo conocido en `team-insights.test.ts`) y `npx tsc --noEmit -p tsconfig.app.json` sin superar la base de 39 errores. Ninguna tarea toca la app desktop, ni crea tablas, ni añade prompts.

### T1 · Flag, capacidad y menú
- **Archivos:** `backend/app/config.py`, `backend/app/services/company.py`, `backend/app/api/auth.py`, `backend/app/api/company.py`, `src/features/company/types.ts`, `src/features/company/api.ts`, `src/pages/dashboard/DashboardHome.tsx` (switch a un `RepHome` mínimo que de momento pinta `TodayPanel`), `src/components/dashboard/DashboardLayout.tsx` (menú del comercial, sin planes ni Copiloto para miembros), `src/lib/product-catalog.ts` (`navToday`, `navConversations`), `docs/features/MASTER_PLAN.md` (flag en la línea «Hoy por empresa»). La lista de entradas sale de una función pura `navItemsFor({role, repWorkspace})` en `src/lib/nav.ts`.
- **Tests primero:** pytest del resumen de empresa con el flag encendido y apagado; `node --test src/lib/nav.test.ts` (miembro/admin × flag).
- **Verificación:** Reticle con el flag apagado (la home y el menú no cambian) y encendido (menú del comercial).

### T2 · Lecturas nuevas en backend
- **Archivos:** `backend/app/services/hoy/upcoming.py` y `done.py` (puros), `backend/app/api/today.py` (`/today/upcoming`, `/today/done`), `backend/app/api/followup.py` (`GET /api/v1/followups?status=ready`), `backend/app/api/memos.py` (filtro `status`). Todas detrás de `REP_WORKSPACE_ENABLED`.
- **Tests primero:** ventana de 7 días y zona horaria; `crm_task_id` → marcador; Hecho hoy se vacía a medianoche; solo el autor ve sus follow-ups; `status=pending_review` filtra; con el flag apagado, 404.
- **Verificación:** pytest verde; sin UI (Reticle no aplica hasta T3).

### T3 · Casa: composición y secciones
- **Archivos:** `shared/ui/home.js` + `home.test.js` (`composeHome`), `src/features/today/components/RepHome.tsx`, `HomeSection.tsx`, `src/features/today/api.ts`, `TodayItemList.tsx` (`selected`, icono al pasar el ratón), `src/lib/product-catalog.ts`.
- **Tests primero** (`node --test shared/ui/home.test.js`): orden de secciones; sección vacía = ausente; tope de 7 con reuniones y confirmaciones; ≥3 confirmaciones → 1 fila; deduplicado por contacto (`/today` gana a `/contact-priorities`); texto «N más»; un 409 conserva el estado real.
- **Verificación:** Reticle, flow «el comercial abre Hoy y ve reuniones, Falta tu OK y a quién llamar con su motivo»; estados de carga, error, vacío y parcial forzados por red.

### T4 · Panel de contacto, selección y teclado
- **Archivos:** `src/features/today/components/ContactPanel.tsx`, `src/features/today/hooks/useHomeSelection.ts`, `shared/ui/queue.js` (`HOME_KEYS`, ignorar editables) + `queue.test.js`, `src/components/dashboard/memos/ContactBrief.tsx` (etiqueta y filete), `DashboardLayout.tsx` (columna derecha contacto ↔ Preguntar), `Sheet` por debajo de 1280 px.
- **Tests primero:** ↑/↓/j/k mueven y no se disparan en editables ni con ⌘/Ctrl; `Enter`/`s`/`n`/`Esc` sin cambios; primera tarjeta seleccionada; al resolver la seleccionada, pasa a la siguiente; nunca el brief de otro contacto (`brief.test.js`).
- **Verificación:** Reticle, flow «seleccionar una tarjeta enseña su preparación y un solo botón de llamar», a 1440 y a 1024.

### T5 · Dialer anclado y después de la llamada
- **Archivos:** `FloatingDialer.tsx` (`placement`), `DashboardDialer.tsx` (`onCallEnded`, tiempo), `DialerFocusProvider.tsx` (estado de llamada), `ContactPanel.tsx` (vista «Después de la llamada» con `GET /calls/{call_sid}`, `FollowupCard`, confirmación de E7 si llega), `src/lib/today-queue.ts` + test.
- **Tests primero:** `call_ended` con conversación → revisión; buzón / sin respuesta → avanza y la tarjeta se queda; llamada fallida → se queda; selección bloqueada en llamada; cambiar de ruta no desmonta el dialer.
- **Verificación:** Reticle con el estado del dialer registrado en `src/reticle-dev.ts` (no se puede llamar de verdad): tras `call_ended` simulado, el panel enseña el follow-up y `n` selecciona la siguiente.

### T6 · Cierre: coherencia, docs y gate
- **Archivos:** `docs/EXPERIENCIA_PRODUCTO.md` (texto de §13), `docs/features/MASTER_PLAN.md` (estado de F16), copy EN revisado en `product-catalog.ts`, y el informe web (`src/lib/report-snapshot.ts`, `ReportPage`) con la misma línea por canal que ya lleva el email (`metrics.channels` de E1: «3 llamadas · 1 reunión · 2 visitas»), sin bloque nuevo.
- **Tests:** `npx @reticlehq/server gate` sobre los flows de T1, T3, T4 y T5; repaso de la tabla de edge cases de la spec (cada fila con su test).
- **Verificación:** veredicto `pass` en todos los flows; con el flag apagado, la home actual intacta.

---

## 15. Riesgos

| Riesgo | Mitigación |
|---|---|
| Mover el dialer de sitio corta la llamada | Una sola instancia; `placement` solo cambia clases; sin portal. Test en T5 |
| El tope de 7 deja fuera llamadas importantes cuando hay muchas reuniones o confirmaciones | Confirmaciones agrupadas a partir de 3; el founder confirmó que reuniones y confirmaciones cuentan en el tope |
| Dos fuentes para A quién llamar (`/today` + `/contact-priorities`) | `composeHome` puro y testeado; `/today` gana en duplicados. A medio plazo, que lo devuelva el backend en una lectura |
| Atajos que se disparan escribiendo el follow-up | `queueKeyAction` ignora editables. Test en T4 |
| Historial por contacto solo para HubSpot | Se oculta el bloque si no hay filtro (Pipedrive/Salesforce), nunca vacío |
| Tres lecturas nuevas en cada apertura | Deterministas, sobre tablas ya indexadas por usuario; se piden en paralelo con `/today` |

## Checklist UX (skill §5)

- [x] Reutiliza patrones y estilos: papel, chip, pastilla, `CallCard`, `ContactBrief`, `v-followup`, dialer, `Sheet`. Cero tokens nuevos.
- [x] Encaja con extensión y desktop: mismo brief, misma etiqueta, mismas plantillas.
- [x] Menos clics: la preparación sale sin clic; llamar = `Enter`; confirmar = 1 clic; tras colgar, todo en el panel.
- [x] Edge cases y vacíos diseñados (§4.6 y la tabla de la spec).
- [x] Textos cortos: plantillas de backend; la UI no genera texto.
- [x] Archivos y motivos en §10.

## Firma
- [x] Revisado por: Toni (founder) · fecha: 26 sep 2026
