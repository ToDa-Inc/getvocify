# Instrucciones para actualizar `proposed_plan.md` — UX/UI + proceso de ejecución

> **Para quien va a tocar `proposed_plan.md`:** esto no es feedback para leer y ponderar — es una lista de ediciones concretas que hay que meter dentro del plan, feature por feature. Cada punto dice en qué sección de `proposed_plan.md` entra y qué hay que cambiar o añadir ahí. Ya leí el plan completo (1935 líneas) antes de escribir esto, así que cada instrucción dice explícitamente si ya está resuelta (no tocar), si falta (añadir), o si contradice algo que ya está escrito (resolver el conflicto antes de tocar código).

---

## A. UX/UI — instrucciones por feature

Verificado contra código real: `electron-main.mjs` completo, `DashboardHome.tsx` completo, `ObjectionCopilotPage.tsx`.

### A0 — Auditoría real de las 3 superficies (esto faltaba en el plan y en mi propia versión anterior de este documento)

**`proposed_plan.md` audita bien el backend (archivo y línea por feature), pero no deja constancia de lo que hay hoy en cada pantalla real.** Esto es lo que confirmé leyendo el código, no asumiendo:

- **Dashboard (`src/pages/dashboard/DashboardHome.tsx`, 31 líneas completas):** hoy es solo un saludo ("Welcome back, {nombre}") + `<VoiceRecorderWidget>` + `<ActivityPanel>`. No hay contactos, no hay "Hoy", no hay nada más — confirma que F05 ("Hoy" como parte principal de `/dashboard`) tiene sitio libre real donde construirse, no hay que desplazar nada complejo.
- **`src/pages/dashboard/ObjectionCopilotPage.tsx` (255 líneas) no es un endpoint con una tarjeta simple — es un feature module completo**, con sus propios hooks (`useObjectionSuggestions`, `useTurnDetector`, `useRealtimeTranscription`) y componentes (`CopilotControls`, `SuggestionCard`, `VoiceEnrollmentPanel`) importados de `@/features/copilot`. **Esto sube el costo real de "embeber" esto en el flujo de meeting (F12)** — no es mover un componente, es decidir si esos hooks se reutilizan desde el nuevo sitio o si esa página queda como una segunda implementación en paralelo. `proposed_plan.md` no lo dice así de explícito; hay que añadirlo al Backend/Frontend de F12 como coste real, no dar por hecho que es un simple traslado de componente.
- **Extensión (`chrome-extension/popup/index.html`):** confirmado otra vez, las únicas pantallas son `screen-loading`, `screen-login`, `screen-processing`, `screen-record`, `screen-review`, `screen-success` — todas atadas al ciclo de una llamada. Esto respalda A3 de abajo: no hay hoy ningún sitio en la extensión para mostrar contexto de un contacto sin llamada activa, hay que crearlo.
- **Desktop (`getvocify-desktop/electron-main.mjs`):** tiene más infraestructura de la que yo había asumido — ver A6, es el hallazgo más importante de esta revisión.

**Qué meter en `proposed_plan.md`:** añadir esta auditoría de pantallas reales como parte de la sección 2 ("Discrepancias encontradas"), o al menos citarla dentro de F05 y F12 donde afecta directamente el alcance.

### A_principio — "Nada da saltos" y accesibilidad, como regla transversal, no solo de F06

El propio spec de spine (`docs/superpowers/specs/2026-09-21-copilot-spine-design.md`, §2.3 "Nothing jumps" y §7 "Accessibility and motion") ya define esto: los estados de carga reservan el espacio del componente final (no hay saltos de layout), las transiciones usan `prefers-reduced-motion`, el contraste de texto es ≥4.5:1, cada control tiene foco visible. **`proposed_plan.md` solo aplica el foco de teclado explícitamente a F06 (la cola)** — el resto de features con UI nueva (F02, F05, F09, F12) no repiten esta regla, aunque deberían heredarla igual, porque usan el mismo kernel de componentes compartidos.

**Qué meter:** una línea en "Restricciones globales" (junto a la que ya vamos a pedir de TDD+SOLID en B6): *"Todo componente del kernel de UI compartido (`shared/ui/`) hereda las reglas de motion y accesibilidad de `copilot-spine-design.md` §2.3 y §7 — no se repiten por feature, se cumplen por construcción."* Esto evita que cada feature tenga que redeclararlo, y evita que se pierda en las que no lo mencionan hoy.

### A1 — F01 (Captura desktop): el problema de la transcripción en vivo, con su ubicación exacta

**Estado en el plan:** F01 solo dice, en la columna de auditoría, "intentar imitar la UX de Granola lo máximo posible" — es una intención, no un requisito técnico. La sección Backend/Frontend de F01 no lo desarrolla.

**Qué meter:** añadir a la sección Backend o Frontend de F01 este requisito concreto, con su causa ya localizada — no hace falta que el desarrollador la vuelva a buscar:
- `getvocify-desktop/renderer/app.js:220` (`renderTranscript()`) hoy hace `` `${finalTranscript} ${interimTranscript}`.trim() `` — concatenación directa, sin ningún tratamiento. Por eso se ve como texto a trozos de 1-2 palabras en vez de fluido.
- El requisito es: reconciliar visualmente el momento en que `interimTranscript` (provisional) se confirma y pasa a `finalTranscript` (definitivo), sin salto ni parpadeo — aparición gradual, no en bloques.
- Candidato correcto para construirlo: un componente `<v-transcript>` dentro del kernel de UI compartido (`shared/ui/`, el mismo que ya usa `<v-followup>` en F02) — porque el mismo problema de suavizado aplicaría a cualquier otra superficie que en el futuro muestre transcripción en vivo.

### A2 — F01: falta el entregable de distribución (instalador)

**Estado en el plan:** cero menciones a DMG, firma de código, notarización o instalador en todo el documento (verificado por búsqueda). F01 solo cubre importar el repo y arreglar el pipeline de captura.

**Qué meter:** añadir a F01 (o crear F01b si se prefiere separarlo como entrega propia) esto, ya verificado contra `getvocify-desktop/package.json`:
- Ya existe infraestructura base: `electron-builder`, target `dmg`+`zip`, `productName: "Vocify Companion"`, ícono, script `npm run dist:mac`.
- **Gap real, no de infraestructura sino de "puesta a punto":** `"identity": null` y `"hardenedRuntime": false` — el DMG no está firmado ni preparado para notarización de Apple. Cualquiera que lo descargue hoy va a ver el aviso de Gatekeeper de "app dañada". Firmar/notarizar requiere una cuenta Apple Developer ID — **esto es una decisión de negocio que hay que confirmar con Dani antes de convertirla en tarea de ingeniería**, no asumir que ya existe la cuenta.
- El bloque `"dmg"` de ese `package.json` solo tiene `title` y `artifactName` — no hay `background` ni posicionamiento de iconos, así que hoy es el instalador genérico de electron-builder, no uno con marca/logo.
- Falta decidir dónde vive el link de descarga del `.dmg` (dashboard, landing, ambos) — no until confirmar si ya existe algún flujo de descarga real (no lo pude confirmar del todo, solo encontré el texto "Vocify Companion" en `src/pages/dashboard/RecordPage.tsx:33`, sin verificar si es o no un link).

### A3 — F03 (Preparación de llamada/meeting): falta la extensión como superficie

**Estado en el plan:** F03 sigue correctamente "pendiente de aprobación" (tu propia decisión), pero cuando propone dónde vive dice: *"`<v-brief>` dentro de la tarjeta ampliada, el marcador y la home desktop"* — **cero menciones a la extensión** en toda la sección F03 (verificado).

**Qué meter:** cuando se apruebe el formato de F03, la propuesta a validar tiene que incluir explícitamente la extensión en la página de contacto de HubSpot como superficie **primaria**, no secundaria — es el momento real en que un comercial necesita ese contexto (a punto de llamar, en HubSpot), no cuando está en el dashboard de Vocify. El dashboard y el desktop pueden tener la misma vista como secundaria.

**Edge case a añadir explícitamente en F03:** qué se muestra cuando el comercial abre un contacto sin ninguna interacción previa capturada por Vocify — no dejarlo vacío sin más, definir un estado explícito ("sin interacciones registradas todavía", con alguna acción útil como ver lo que sí trae HubSpot).

### A4 — F09 (Scoring): confirmar si el resultado real pesa en el número, no solo en el texto

**Estado en el plan:** ya está bien resuelto — dos ejes (adherencia al playbook + no premiar la llamada fácil), elegibilidad explícita (`null` en vez de 0%). Es de los mejor resueltos de todo el plan.

**Qué meter:** una sola aclaración, no un cambio de diseño — confirmar explícitamente en la sección Backend de F09 si el resultado real (deal avanzado, meeting agendado, cerrado) influye en el `value: 0-10` numérico, o solo en el texto cualitativo de fortalezas/mejoras. Hoy el documento no lo deja 100% cerrado.

### A5 — F10 (Objeciones): falta el desglose explícito de qué se ve dónde

**Estado en el plan:** el backend está bien resuelto. El frontend dice "campo discreto Añadir nota en la captura desktop y en las superficies de llamada" sin desglosar las tres vistas distintas.

**Qué meter:** añadir a la sección Frontend de F10 una tabla corta con las tres vistas y su propósito distinto — no es trabajo de backend nuevo, es dejar explícito lo que ya está repartido entre F10 y F15:

| Superficie | Cuándo es relevante | Qué se muestra |
|---|---|---|
| Desktop/extensión, durante el meeting | En el momento, para responder ya | La objeción actual, con sugerencia si se pide (esto ya es F12) |
| Dashboard, revisión de una interacción pasada | Después, para aprender | Objeciones de esa llamada, categorizadas, con cómo se manejaron (parte del brief, F11) |
| Dashboard, panel de equipo | Ver patrones, no una llamada suelta | Agregación de qué se repite y quién las supera (ya cubierto en F15) |

### A6 — F12: la ventana flotante que pedías **ya existe en el código** — F12 está factualmente equivocado, no es una decisión pendiente

**Estado en el plan:** F12 dice literalmente *"Una sola pastilla; no una segunda ventana."*

**Lo que pediste tú, textual:** *"las tarjetas del meeting pueden aparecer en el ordenador flotando, no siempre con la app completa abierta."*

Verificado en `getvocify-desktop/electron-main.mjs`: **ya existe exactamente esa ventana**:

- `createOverlay()` (línea 129) crea una `BrowserWindow` con `frame: false, transparent: true, resizable: false, skipTaskbar: true, alwaysOnTop: true`, y además `setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })` — es decir, **ya está pensada para quedar por encima de Zoom/Meet en pantalla completa**, que es justo el caso de uso real de una tarjeta de meeting.
- `showOverlay()` / `hideOverlay()` (líneas 156/163) ya están expuestas por IPC (`overlay:show`, `overlay:hide`) y ya se disparan hoy al empezar/parar de escuchar (líneas 324/329).
- Ya tiene su propio renderer: `renderer/overlay.html` + `renderer/overlay.js` — hoy muestra una pastilla mínima ("Live"/"Idle" + la última línea de transcripción + botón Stop, con doble clic para volver a abrir la ventana principal).

**Conclusión, no hay conflicto que decidir:** la frase de F12 *"no una segunda ventana"* es incorrecta respecto al código real — la segunda ventana ya existe y ya se usa en producción para el estado de "escuchando". Lo que hay que meter en F12 no es una decisión de arquitectura nueva, es: **extender ese overlay ya existente** para que, además del estado "Live/Idle" que ya muestra, pueda mostrar el contenido de la tarjeta de objection handling/checklist cuando `grounded: true` — reutilizando `showOverlay()`/`hideOverlay()` y el canal IPC `overlay:state` que ya existe, en vez de construir mecanismo de ventana nuevo.

**Qué meter en F12:** reemplazar la frase *"Una sola pastilla; no una segunda ventana"* por algo como: *"La sugerencia se muestra en el overlay ya existente (`renderer/overlay.html`, `showOverlay`/`hideOverlay`), extendiendo su estado más allá de Live/Idle — no se construye una ventana nueva porque ya existe una, y no se duplica dentro de la ventana principal."*

### A7 — F04 (Priorización): falta estado vacío

Definition of Done no incluye qué se muestra cuando no hay candidatos. Añadir copy explícito, mismo patrón que ya usa F05 (*"Nada urgente hoy. Buen momento para prospectar"*).

### A8 — F06 (Tareas inteligentes): falta la animación al resolver/descartar una tarjeta

`docs/superpowers/specs/2026-09-21-copilot-spine-design.md` §2.3 exige que los cambios de altura (una tarjeta que sale de "Hoy") se animen sobre altura medida, no con salto brusco, y que bajo `prefers-reduced-motion` se use solo opacidad. F06 no lo menciona ni en Backend/Frontend ni en su Definition of Done. Añadir como criterio de aceptación explícito.

### A9 — F07 (Ask Vocify): falta especificación visual del panel de chat

- No hay patrón de burbujas de conversación definido. `CopilotNote.tsx` es solo un renderizador de notas (discrepancia 5 del propio plan), así que el chat es UI nueva sin diseño visual especificado en ningún sitio.
- El backend responde con `202` + polling del turno persistido, no streaming. Falta especificar el estado de carga durante la espera — no asumir un patrón de streaming token a token si el backend no lo entrega.
- No se especifica el indicador visual de grabación de voz (forma de onda, temporizador, estado de "transcribiendo").

Añadir estas tres piezas a la sección Frontend de F07.

### A10 — F08 (Playbooks): falta el estado de onboarding sin playbook cargado

F09 resuelve el caso downstream (*"Falta configurar el proceso"*), pero F08 no especifica si Settings muestra algún aviso proactivo (banner, checklist de configuración) cuando la empresa todavía no cargó ningún playbook. Añadir a la sección Frontend de F08.

### A11 — F11 (Brief post-interacción): falta enumerar los estados visuales

F02 define explícitamente `generating / ready / sent / unavailable`. F11 no enumera el equivalente (pendiente / listo / omitido por inelegibilidad) como estados de UI. Igualar el mismo patrón.

### A12 — F13 (Reporting): falta el layout de la página de informe

Solo se define el contenido (números agregados). No se especifica si la página del informe es texto/tabla o incluye visualización. Definir antes de construir, no dejarlo a criterio del ejecutor.

### A13 — F14 (Meeting booked): falta conectar la detección con el overlay en vivo

Con el hallazgo de A6 (el overlay flotante ya existe), falta decidir si "reunión detectada" se muestra ahí en tiempo real durante el meeting, o solo después de forma asíncrona en la revisión. `proposed_plan.md` solo especifica lo segundo. Añadir la decisión explícita a F14.

### A14 — F15 (Dashboard de equipo): falta el tratamiento visual de las agregaciones

No se especifica si las métricas de equipo (objeciones, adherencia, win-loss) se muestran como tabla, gráfico o ambos. Definir antes de construir.

---

## B. Proceso de ejecución — instrucciones para la sección 5 del plan (y para las "Restricciones globales")

### B1 — Ejecución por subagentes

**Estado en el plan:** referencia el skill `executing-plans` en la primera línea, pero no especifica si cada entrega corre como sesión propia con contexto limpio.

**Qué meter en la sección 5 ("Ejecución, pruebas y salida a producción"):** cada una de las 16 entregas (F01...F15 + los cimientos F0/F0.1) se lanza como su propio subagente/sesión aislada, con el spec de esa única feature como contexto de entrada — no el documento completo de 1935 líneas. El subagente reporta de vuelta (qué se hizo, qué pruebas pasaron, qué quedó pendiente) antes de autorizar la siguiente entrega. Esto no es una preferencia de herramienta — es la forma concreta de cumplir la restricción global que el propio plan ya tiene: "una feature a la vez, hasta el final, antes de pasar a la siguiente."

### B2 — Que no se quede atascado (lo más importante de este bloque, y lo único que no tiene ninguna cobertura hoy)

**Estado en el plan:** cero cobertura — verificado, no hay ninguna mención a qué hacer cuando el ejecutor se topa con algo que no puede resolver solo.

**Qué meter como subsección nueva dentro de la sección 5:**
- Nunca esperar indefinidamente una respuesta humana en medio de una entrega. Ante un bloqueo de producto (como el conflicto de F12 en A6), el agente: (a) deja constancia clara del bloqueo y las opciones, (b) sigue con cualquier parte de la misma entrega que no dependa de esa decisión, (c) si no queda nada más que avanzar ahí, pasa a preparar la siguiente entrega que sí pueda ejecutarse.
- Un test que falla no es un bloqueo — el ciclo TDD que ya tiene el plan resuelve eso. Lo que falta es la misma regla para bloqueos de *producto* (dato faltante, permiso no confirmado, decisión pendiente tipo F03).
- Todo bloqueo se documenta en el propio commit/PR de esa entrega, no se pierde en el chat de la sesión.

### B3 — Edge cases: mismo rigor en todas las features, no solo en las mejor resueltas

**Estado en el plan:** ya hay edge cases reales y concretos en las 15 features, pero desiguales en profundidad — F01, F06 y F14 están muy bien, otras son más cortas.

**Qué meter:** pedir explícitamente, para cada feature, estos dos casos si no los tiene ya:
1. El caso "no hay datos todavía" (contacto nuevo, empresa recién onboarded, playbook sin cargar) — F03 ya lo insinúa, falta igualarlo en F04, F05, F09.
2. El caso de dato parcial/ambiguo — ya bien cubierto en F14 (fechas) y F01/F11 (audio), falta confirmar el mismo estándar en F09 (playbook ambiguo) y F15 (deals con múltiples responsables).

No es pedir edge cases inventados — es pedir que se aplique parejo el mismo nivel que ya se usó en las mejores features.

**Falta además una regla de proceso, no de contenido:** `proposed_plan.md` no dice qué hace el ejecutor cuando, ya construyendo una entrega, encuentra un edge case que no estaba listado en el spec. Añadir a la sección 5 ("Ciclo de trabajo por entrega"), como paso explícito entre "implementar el mínimo necesario" y "ejecutar regresiones":

- Detectar edge cases no listados en el spec de la entrega es parte del trabajo, no un extra opcional.
- Cada edge case nuevo que se detecte se resuelve dentro de esa misma entrega (diseño de la solución + test que lo cubre) antes de cerrarla — no se deja anotado sin resolver ni se pasa a la siguiente entrega.
- Si el edge case implica una decisión de producto que el ejecutor no puede tomar solo, se documenta como bloqueo siguiendo el protocolo de B2, no se ignora ni se resuelve por suposición.
- El edge case y su resolución se registran en el mismo commit/PR de la entrega, junto con su test.

### B4 — Testing: ya está bien, solo confirmar que no se pierde

**Estado en el plan:** ya resuelto y bien — ciclo TDD explícito por entrega, tabla de pruebas obligatorias por área, evaluación de IA con casos críticos que deben pasar antes de habilitar cada funcionalidad. **No hace falta añadir nada aquí.**

### B5 — Migraciones: ya está bien, solo confirmar que no se pierde

**Estado en el plan:** ya resuelto — 13 migraciones numeradas (037 a 049) con su contenido, todas aditivas, con la regla explícita de que "la desactivación de una funcionalidad no elimina sus datos". **No hace falta añadir nada aquí.**

### B6 — TDD y SOLID: subirlos de mención por feature a regla de entrada no negociable

**Estado en el plan:** SOLID aparece en cada feature (sección propia), TDD es el ciclo de trabajo de la sección 5 — el contenido está, pero vive repartido en vez de declarado una vez arriba.

**Qué meter:** una línea nueva en "Restricciones globales" (donde ya está "una feature a la vez", "ICP: empresas con CRM estructurado", etc.): *"Cada entrega sigue TDD y se valida contra SOLID antes de darse por cerrada — no son sugerencias de estilo, son parte del Definition of Done de cada una."*

---

## C. Checklist final — ir tachando al editar `proposed_plan.md`

- [ ] A0 — sección 2 (o F05/F12 directamente): añadir la auditoría real de pantallas (DashboardHome mínimo, ObjectionCopilotPage como feature module completo, pantallas reales de la extensión).
- [ ] A_principio — Restricciones globales: añadir la herencia de motion/accesibilidad del spec de spine para todo el kernel compartido.
- [ ] A1 — F01: añadir el requisito técnico de suavizado de transcripción, citando `app.js:220`.
- [ ] A2 — F01: añadir el entregable de distribución (DMG firmado/notarizado/con marca), marcando la firma de código como decisión de negocio pendiente de confirmar.
- [ ] A3 — F03: cuando se apruebe, incluir la extensión a nivel de contacto como superficie primaria + edge case de "sin interacciones todavía".
- [ ] A4 — F09: aclarar si el resultado real pesa en el `value` numérico o solo en el texto cualitativo.
- [ ] A5 — F10: añadir la tabla de "qué se ve dónde" en la sección Frontend.
- [ ] A6 — F12: reemplazar "no una segunda ventana" por la instrucción de reutilizar el overlay ya existente (`createOverlay`/`showOverlay`/`hideOverlay`, `renderer/overlay.html`).
- [ ] A7 — F04: añadir estado vacío.
- [ ] A8 — F06: añadir animación de salida de tarjeta como criterio de aceptación.
- [ ] A9 — F07: añadir patrón de burbujas de chat, estado de carga sin streaming, indicador de grabación de voz.
- [ ] A10 — F08: añadir aviso de onboarding cuando no hay playbook cargado.
- [ ] A11 — F11: enumerar estados visuales del brief (pendiente/listo/omitido).
- [ ] A12 — F13: definir layout de la página de informe (tabla vs. gráfico).
- [ ] A13 — F14: decidir si la detección de meeting se refleja en el overlay en vivo.
- [ ] A14 — F15: definir tratamiento visual de las agregaciones de equipo.
- [ ] B1 — sección 5: añadir ejecución por subagentes, uno por entrega.
- [ ] B2 — sección 5: añadir el protocolo de "no quedarse atascado" como subsección propia.
- [ ] B3 — F04, F05, F09, F15: igualar profundidad de edge cases con el estándar ya usado en F01/F06/F14.
- [ ] B3 — sección 5: añadir la regla de detectar y resolver edge cases nuevos durante la ejecución de cada entrega, no solo los ya listados en el spec.
- [ ] B6 — Restricciones globales: añadir la línea de TDD+SOLID no negociables.
- [ ] B4 y B5 ya están bien — no tocar, solo confirmar que sigue así después de las demás ediciones.
