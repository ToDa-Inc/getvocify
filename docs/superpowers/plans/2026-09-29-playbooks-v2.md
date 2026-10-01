# Vocify · Playbooks v2: de formulario a documento vivo (29 sep 2026)

> **Para agentes:** plan por fases. Cada tarea: TDD, suite en verde, un commit, revisión antes de la siguiente. Aplica la skill `vocify-ux-coherence` (`.cursor/skills/vocify-ux-coherence/SKILL.md`) y la regla de cierre de `docs/superpowers/plans/2026-09-22-vocify-v1/00-cierre.md`.

**Objetivo:** que un Head of Sales tenga un playbook útil en **menos de 2 minutos**, dictándolo, pegándolo o subiendo lo que ya tiene; que ese playbook se aplique **solo** a la llamada correcta; y que después vea, en el mismo documento, qué partes se cumplen y cuáles no.

**Base:** `origin/staging` @ `61d234a`. Se trabaja en `staging`.

**Principio rector del plan:** en Vocify un playbook no es un documento que el comercial lee. Es dos cosas: **la rúbrica** con la que se evalúa cada llamada (C04 marca cada paso como cumplido, fallado o no aplica) y **la respuesta en el momento** (brief antes de llamar, sugerencia en directo, debrief). Todo lo que no sirve a una de esas dos cosas sobra en la pantalla.

---

## 1. Diagnóstico honesto del estado actual

Archivos: `src/features/playbooks/components/PlaybooksSection.tsx`, `PlaybookEditor.tsx`, `PlaybookSetupNotice.tsx`, `src/lib/playbook-editor.ts`, `src/lib/playbook-setup.ts`, `src/pages/dashboard/SalesProcessPage.tsx`, `src/pages/dashboard/PlaybookPage.tsx`, `backend/app/api/playbooks.py`, `backend/app/services/playbooks/*`, `backend/app/services/captures.py::playbook_fields_for_capture`.

| # | Problema | Por qué importa |
|---|---|---|
| P1 | **Las tipologías propias no se aplican nunca.** `motion_for()` solo conoce `discovery` y `closing` (por rol o por canal). Un tipo creado con «Añadir tipología» (el `sales` de la captura) solo se fija a una llamada si es el único playbook publicado de la empresa. | El Head of Sales dedica tiempo a un playbook que el coaching ignora sin avisar. Es el fallo que más confianza cuesta, y es la razón por la que «muchos playbooks» hoy no sirve de nada. |
| P2 | **Es un formulario, no un playbook.** Primera vista: 4 botones de importación, una caja de pegar, un paso vacío con 3 campos, 7 cajas de objeciones y 2 botones de guardar. Unos 15 campos vacíos antes de aportar nada. | Contradice «con menos información, más valor». Parece trabajo, no una herramienta. |
| P3 | **Audio y PDF no entienden nada.** El texto importado pasa por `parsePlaybookText`, que corta por viñetas y números. Un audio dictado no tiene viñetas: sale un solo paso gigante o un paso por párrafo sin sentido. Las objeciones de un guion nunca se detectan: acaban como pasos. | «Subir audio» promete lo que más encaja con Vocify (explicarlo hablando) y no lo cumple. |
| P4 | **El campo que decide la nota es el que menos se ve.** C04 juzga cada paso **solo** contra su `criterion` (`prompts/intelligence_v4.md`). Si el Head of Sales escribe «Apertura» y deja vacío «Cuenta como hecho cuando…», el criterio pasa a ser «Apertura», el juicio es vago y la adherencia se vuelve ruido. | Un coaching con ruido deja de creerse en dos semanas. Aquí es donde la IA aporta más: convertir sus palabras en un criterio observable. |
| P5 | **Borrador y publicación como dos conceptos.** «Guardar borrador» + «Publicar», con «Cambios sin guardar» visible. Al Head of Sales no le importa el borrador: quiere no perder lo escrito y decidir cuándo aplica. | Un clic y una decisión de más en cada cambio. |
| P6 | **Validación antes de escribir.** Un paso recién añadido muestra ya «Cada paso necesita un nombre» en rojo. | Error sin haber hecho nada. Sensación de formulario roto. |
| P7 | **Objeciones a ciegas.** Siete cajas iguales, aunque en la misma página (`ObjectionBreakdown`) Vocify ya sabe qué objeciones salen y cuántas veces. | La información para priorizar existe y está a 300 px, sin conectar. |
| P8 | **El comercial no puede leer su playbook.** `/dashboard/process` es solo para managers y `/dashboard/playbook` solo enseña las mejores llamadas de la semana. | La rúbrica con la que se le evalúa es invisible para quien es evaluado. |
| P9 | **Detalles:** clave de tipo = texto libre sin etiqueta («sales»), dos indicadores de estado a la vez, flechas subir/bajar siempre visibles, `PlaybookSetupNotice` con una lista de 4 pasos que describe la UI en vez de simplificarla. | Ruido visual. |

**Lo que está bien y se conserva:** el modelo de datos (pasos `{step_id, label, criterion, example}` + respuestas por las 7 categorías de C04), las versiones fijadas por llamada, las plantillas por flujo, la validación compartida front/back (`structured.py` ↔ `playbook-editor.ts`), la vista de solo lectura, los permisos (owner/admin editan).

---

## 2. La visión, como Head of Sales

### 2.1 Qué tiene un buen playbook (y qué peso tiene cada parte)

| Bloque | Qué es | Peso | Dónde se usa después |
|---|---|---|---|
| **Objetivo** | Una línea: qué tiene que pasar para que la llamada haya ido bien («Reunión con día y hora»). Viene del tipo de llamada, no se escribe. | Una línea bajo el título | ProcessHealth, debrief |
| **Pasos** | 3 a 6 cosas que el comercial **tiene que hacer**, cada una comprobable en la transcripción. Nombre corto (2–4 palabras) + «cuenta como hecho cuando…». | Protagonista | C04 met/missed, checklist en directo (desktop), debrief, adherencia |
| **Respuestas a objeciones** | Qué dice un buen comercial ante precio, timing, «no decido yo»… 1–2 frases que se puedan decir en voz alta. | Segundo | Brief antes de llamar (extensión y dashboard), sugerencia en directo, Ask, panel de objeciones |
| **Frases** | La frase de ejemplo de un paso. Es «el guion», pero a nivel de línea. Opcional. | Bajo demanda | Debrief: «Prueba con: «…»» |
| **Fuente** | El PDF, audio o texto original, guardado tal cual. | Un enlace | Nadie la usa en el día a día; evita perder nada |

Sobre el **guion**: los comerciales no leen guiones durante una llamada. El guion completo no se muestra como bloque: Vocify lo parte en pasos y frases, y el documento original queda enlazado como fuente. Así el valor del guion llega en el momento en que sirve.

Sobre **muchos pasos**: más de 6 pasos convierte el coaching en una lista de fallos. A partir del 7º paso aparece una línea discreta: «Con más de 6 pasos el coaching pierde foco». El límite duro sigue en 15.

### 2.2 Pocos playbooks, bien enrutados

Lo que cambia una llamada de otra es **el objetivo y la apertura**, no el nombre del tipo. Por eso propongo un catálogo corto, con valores por defecto, y no un generador de tipos libres:

| Rol | Tipo | Clave | Objetivo | Se aplica cuando (por defecto) | Pasos de plantilla |
|---|---|---|---|---|---|
| SDR | **Llamada en frío** | `discovery` (existe) | Reunión agendada | SDR · llamada · contacto sin reunión | Apertura con permiso · Motivo concreto · Descubrir el dolor · Cualificar · Reunión con día y hora |
| SDR | **Lead inbound** | `inbound` (nuevo) | Reunión agendada | SDR · llamada · el lead vino de un formulario o inbound (si el CRM lo dice) | Referencia a su solicitud · Qué le hizo pedir info · Cualificar · Reunión con día y hora |
| AE | **Discovery** | `ae_discovery` (nuevo) | Dolor confirmado y demo agendada | AE · reunión · primera reunión del deal, o etapas de CRM elegidas | Agenda · Situación actual · Dolor e impacto · Quién decide y cómo · Siguiente reunión |
| AE | **Demo** | `closing` (existe) | Siguiente paso con fecha | AE · reunión (por defecto de AE) | Agenda y objetivo · Repasar el dolor · Demo enfocada · Resolver dudas · Siguiente paso |
| AE | **Propuesta y negociación** | `negotiation` (nuevo) | Fecha de decisión o firma | AE · reunión · etapas de CRM elegidas (propuesta, contrato) | Repasar la propuesta · Validar decisores · Objeciones de precio y términos · Fecha de firma |

- **Prospección vs. cualificación vs. cold call completa:** en la mayoría de equipos son la misma llamada. La cualificación son pasos dentro de la llamada en frío, y C04 marca «no aplica» lo que no ocurrió. Un equipo que sí hace dos llamadas separadas crea un **tipo propio** con la condición «contacto ya contactado». No hace falta un tipo por defecto.
- **Contrato:** no suele ser una conversación que haya que evaluar (es email y legal). Queda dentro de «Propuesta y negociación».
- **`qualification`** (existe, oculto si no tiene versión publicada) se mantiene por compatibilidad y no se ofrece.
- **Tipo propio:** se puede crear, pero **siempre con rol y condición**. Sin condición no se guarda: así un playbook nunca se queda sin aplicarse (P1).

### 2.3 Estricto o personalizable

Propuesta: **estricto en la forma, libre en el contenido**. Las categorías de objeción son fijas (son las de C04; una categoría libre nunca haría match), el objetivo lo da el tipo y el número de pasos está acotado. Lo que se escribe es 100 % suyo. «Paso clave» (un paso que cuenta doble) queda fuera de esta entrega: cambia el scoring y el orden de los pasos ya expresa prioridad (el debrief nombra primero el primer paso fallado).

---

## 3. Recorrido

**Head of Sales (primera vez)** · llega desde el paso 4 del onboarding (`OnboardingWizard.tsx`) o desde Proceso de venta. Viene concentrado pero con poca paciencia: quiere que Vocify evalúe «como vendemos nosotros», no rellenar un formulario.

1. Ve la lista de tipos: los de los roles que tiene su equipo, cada uno en una fila. ★ **Momento crítico:** el estado vacío tiene que invitar a empezar, no explicar pasos.
2. Abre «Llamada en frío» → una sola caja: dictar, escribir, pegar o soltar un archivo. ★ **Momento crítico:** llegar al primer playbook en menos de 2 minutos.
3. Vocify lo estructura (≤ 20 s, una línea de progreso) → documento con pasos y respuestas, **con sus palabras**. ★ **Momento crítico (confianza):** nada inventado, nada genérico.
4. Retoca una línea y pulsa **Publicar**. Mensaje: «Activo en las llamadas nuevas».
5. **Una semana después** vuelve: al lado de cada paso ve el % de llamadas en que se cumple, y en objeciones ve «Timing · sale en 18 % · sin respuesta». Escribe esa respuesta o usa la mejor del equipo con un clic. ★ **Aquí está el valor que hace volver.**

**Comercial** · abre «Playbook» en la navegación → lee su proceso (solo sus tipos, solo lectura) y, debajo, las mejores llamadas de la semana. No edita nada.

---

## 4. Diseño de UI

### 4.1 Lista de playbooks (Proceso de venta → «Vuestro proceso»)

Sustituye a las pestañas y a las tarjetas `bg-secondary/40` actuales. Una fila por tipo, con `THEME_TOKENS.cards.base` como contenedor y filas separadas por `border-border/40`, igual que `PlaybookPage`.

```
Vuestro proceso
─────────────────────────────────────────────────────────────────────
Llamada en frío · SDR     Activo · 5 pasos · 4 respuestas        62 %  ›
Demo · AE                 Borrador sin publicar                         ›
Discovery · AE            Sin crear                               Crear ›
─────────────────────────────────────────────────────────────────────
+ Tipo de llamada                                      (enlace, ghost)
```

| Elemento | Peso | Por qué |
|---|---|---|
| Nombre + rol | `text-[15px] text-foreground` | Es lo que se busca |
| Estado + recuento | `capsLabel` | Contexto, no acción |
| % de cumplimiento (fase 3) | `text-sm text-muted-foreground`, solo si hay ≥ 10 llamadas | Resume la salud sin abrir |
| «Crear» | Único botón visible, solo en filas vacías | Acción principal de esa fila |
| «+ Tipo de llamada» | Enlace ghost al final | Ocasional |

- Se muestran los tipos por defecto de los roles que existen en el equipo (con `SALES_ROLES_ENABLED`: SDR → Llamada en frío; AE → Demo), más los que ya tienen versión. El resto está en «+ Tipo de llamada».
- **Fase 1** (antes del enrutado): «+ Tipo de llamada» se oculta. Un tipo propio que ya existe se muestra con la línea «No se aplica a ninguna llamada todavía» en `text-muted-foreground`. Es verdad, y evita que se creen más.
- `PlaybookSetupNotice` (la lista de 4 pasos) desaparece: el estado vacío de cada fila ya lo explica.

### 4.2 Crear (playbook vacío)

Al abrir una fila vacía, la fila se expande (transición de altura, sin salto) y enseña una sola caja, al estilo Granola:

```
Llamada en frío · SDR
Objetivo: reunión con día y hora

┌──────────────────────────────────────────────────────────────────┐
│ Cuéntalo como se lo contarías a un comercial nuevo, o pega      │
│ vuestro guion. También puedes soltar aquí un PDF o un audio.    │
│                                                                  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
 🎙  📎                                          [ Crear playbook ]
 o empezar con la plantilla →
```

- **Una caja para todo:** escribir, pegar, soltar un archivo (PDF, audio, .txt) o dictar con el micro (🎙 reutiliza `VoiceComposer` de Ask, con sus mismos estados y permisos). 📎 abre el selector de archivos. Todo va al mismo endpoint.
- **Acción principal:** «Crear playbook», que solo se activa con contenido.
- **Plantilla:** enlace secundario. Se aplica directamente, sin LLM.
- **Mientras procesa:** la caja se queda con el texto en `opacity-60` y una línea `VocifySpinner` + «Ordenando vuestro proceso…». Sin modal.
- **Al terminar:** la caja se sustituye por el documento (4.3). El texto original se guarda como fuente.

### 4.3 El documento (revisar, editar y leer son la misma vista)

```
Llamada en frío · SDR                        Borrador · Guardado   [ Publicar ]
Objetivo: reunión con día y hora

PASOS
1  Apertura con permiso       Se presenta y pide 30 segundos antes de contar nada.
2  Motivo concreto            Conecta la llamada con algo del prospecto: sector, rol o algo que hizo.
3  Descubrir el dolor         El prospecto nombra un problema concreto con sus palabras.
   «¿Cómo lo estáis haciendo hoy con…?»
4  Cualificar                 Confirma quién decide y cuándo quieren resolverlo.
5  Reunión con día y hora     Propone día y hora y el prospecto acepta.
+ Paso

OBJECIONES
Precio      «Entiendo. ¿Comparado con qué lo estás mirando?…»
Timing      Sale en el 18 % de las llamadas · sin respuesta          Escribir
+ Objeción

Fuente: guion-sdr.pdf
```

- **Edición en línea:** cada paso es texto hasta que recibe el foco; los inputs no tienen borde hasta entonces (`border-transparent` → `focus:border-border`). Nada de tarjetas por paso.
- **Nombre** en `text-[15px]`, **criterio** en `text-sm text-muted-foreground` en la misma fila (debajo en móvil). **Frase** en cursiva debajo, solo si existe; «+ frase» aparece al hacer hover o foco en el paso.
- **Reordenar y borrar:** asa de arrastre y papelera `IconAction` visibles solo en hover o foco (hoy son flechas siempre visibles). Las flechas se mantienen accesibles por teclado.
- **Objeciones:** se ven las respondidas y las que el equipo recibe sin respuesta, ordenadas por frecuencia (datos de `useTeamAdherence` → `objection_categories`, ya cargados en la misma página). El resto de categorías está en «+ Objeción». Contador de caracteres solo cerca del límite (hoy ya pasa así en los criterios).
- **Guardado automático:** tras 800 ms sin escribir se guarda el borrador. Estado en `capsLabel`: «Guardando…» / «Guardado». No hay botón «Guardar borrador».
- **Una acción principal: «Publicar»** (o «Publicar cambios» si ya hay una versión activa). Si no se puede, el botón está desactivado y hay **una** línea con el motivo («El paso 3 necesita un nombre»). Al lado, el enlace «Descartar cambios» vuelve a la versión activa (solo si hay versión activa y borrador).
- **Validación:** solo en blur o al intentar publicar. Un paso recién añadido y vacío nunca muestra error (P6).
- **Publicado y sin cambios:** misma vista, en modo lectura. Arriba a la derecha, «Editar» en ghost. En la fase 3 se ve el % por paso a la derecha de cada fila.
- **Borrador sobre una versión activa:** etiqueta «Borrador sin publicar». Las llamadas siguen usando la activa.

### 4.4 Vista del comercial (`/dashboard/playbook`)

El mismo componente en modo lectura, arriba, para sus tipos (pestañas solo si hay más de uno). Debajo, las «Mejores llamadas de la semana» que ya existen. Sin % por paso del equipo (para no crear un ranking); en su lugar, su propio % en «Coach», que ya existe.

---

## 5. Estructurar con IA (el corazón de la fase 1)

**Una llamada al LLM, con reglas deterministas antes y después.**

- **Entrada:** texto (escrito, pegado, sacado de un PDF o transcrito de un audio) + el tipo de llamada (clave, rol, objetivo) + idioma de la empresa.
- **Salida (JSON):** `steps[{label, criterion, example?}]` (3–7), `objections[{category, guidance}]` (solo las categorías de C04 y solo si la fuente trae la respuesta), `dropped` (líneas de la fuente que no eran ni paso ni objeción, para depurar).
- **Reglas del prompt (`backend/app/prompts/playbook_structure_v1.md`):**
  - Usa las palabras del Head of Sales. No inventes pasos que la fuente no nombra.
  - `label` de 2 a 4 palabras. `criterion` observable en una transcripción: lo que dice o consigue alguien, no una actitud («El prospecto acepta día y hora», nunca «Genera confianza»).
  - `example`: solo si la fuente trae una frase literal.
  - `guidance`: 1–2 frases que se puedan decir en voz alta, en el tono de la fuente.
  - Fuente sin proceso (un folleto de producto): devuelve 0 pasos y `reason: "no_process"`.
- **Guardas deterministas después del LLM:** `normalize_steps` / `normalize_objections` (recortan en vez de rechazar), un máximo de 7 pasos y una lista de criterios genéricos en `text_guard.py` (`genera confianza`, `construye rapport`, `aporta valor`, `escucha activa`…). Si falla la guarda, se reintenta una vez; si vuelve a fallar, el paso se queda con su nombre y un criterio vacío marcado para revisar.
- **Si el LLM falla o hay timeout (25 s):** se usa `parsePlaybookText` (el parser determinista de hoy) y la línea «Lo hemos separado por líneas; revisa los pasos». Nunca bloquea.
- **Evals:** `backend/evals/P01/cases.json`, con 12 casos: audio dictado desordenado (es), guion numerado, PDF con apartado de objeciones, fuente en inglés, notas sueltas estilo Granola, documento de 20 pasos (→ ≤ 7), folleto sin proceso (→ `no_process`), guion con frases literales (→ `example`), fuente que contradice la plantilla, texto muy corto («llamamos y agendamos»), mezcla de SDR y AE en un mismo documento (→ solo lo del tipo pedido), fuente con jerga del sector. Se corre 3 veces antes de encender el flag.
- **Coste:** una llamada por creación o reimportación, nunca por pulsación de tecla.

---

## 6. Integración entre superficies

No hay superficie nueva. Todas leen la versión publicada que ya leen hoy; lo que cambia es la calidad de lo que reciben.

| Superficie | Qué lee | Qué cambia con este plan |
|---|---|---|
| Dashboard · Head of Sales (`/dashboard/process`) | Todo | Lista + documento (sección 4) |
| Dashboard · comercial (`/dashboard/playbook`) | Versión activa de sus tipos | Nueva vista de lectura (4.4) |
| Desktop · checklist en directo (`copilot/checklist.py`, `live-assist-overlay.js`) | `label` de los pasos | Nombres de 2–4 palabras caben en el overlay. Sin código nuevo |
| Desktop / overlay · sugerencias (`copilot/prompts.py`) | `entries.guidance` | Respuestas cortas y decibles. Sin código nuevo |
| Extensión · brief del contacto (`contact-brief-box.js` ← `briefs/v2.py::say_line`) | `guidance` de la objeción abierta | Igual. Sin código nuevo |
| Debrief tras la llamada (`coaching/briefs.py`) | Pasos fallados + `example` | «Prueba con: «…»» sale más a menudo porque habrá frases |
| Ask Vocify (`crm_copilot/brain_tools.py`, `intel_tools.py`) | `entries`, `steps` | Nada |
| Fase 2 · detalle de una grabación (`MemoDetail.tsx`) | `sales_motion_key` del memo | Línea «Evaluada como: Demo · cambiar» |

---

## 7. Plan técnico

### Fase 1 · Un playbook en 2 minutos (tipos que ya se enrutan: `discovery`, `closing`)

Flag: `PLAYBOOK_V2_ENABLED` (por empresa, apagado). Con el flag apagado, `PlaybooksSection` y `PlaybookEditor` de hoy siguen iguales.

**T1 · Estructurar con IA (backend)**
- Nuevo `backend/app/services/playbooks/structure.py`: `async structure_source(text, motion_key, lang) -> {steps, objections, reason, fallback}`. Usa `LLMClient.chat_json` (mismo patrón que `glossary_ai.py`) y valida con `structured.normalize_*`.
- Nuevo `backend/app/prompts/playbook_structure_v1.md`.
- Criterios genéricos añadidos a `backend/app/services/text_guard.py` (función nueva `generic_criterion(text)`).
- Endpoint `POST /api/v1/playbooks/{key}/structure` `{kind: text|pdf|audio, payload}` → reutiliza `start_import` para sacar el texto (PDF/audio), guarda la fuente en `playbook_imports` (`kind`, `draft.text`) y devuelve la forma de `/editor` + `source_id`. No crea versión. Solo owner/admin (`_guard`).
- Evals `backend/evals/P01/` + `scripts/eval_playbook_structure.py`.
- Tests: la salida siempre pasa `normalize_steps`; fallback con el LLM caído; `no_process`; permisos.

**T2 · Borrador con guardado automático (backend)**
- `SupabasePlaybookStore.save_structured_draft`: si ya existe un borrador más nuevo que la versión activa, **se actualiza esa fila** en vez de insertar otra (hoy cada guardado inserta una `playbook_versions` y una `playbook_imports`; con autosave serían cientos). La fila de import `kind=editor` se crea una vez por borrador y se actualiza después.
- Mismo comportamiento en `MemoryPlaybookStore`.
- `DELETE /api/v1/playbooks/{key}/draft` para «Descartar cambios» (marca el borrador como `discarded`; no borra historial).
- `GET /{key}/editor` añade `source: {id, kind, name}` si el borrador o la versión vienen de una fuente.
- Tests: 10 guardados = 1 fila de borrador; publicar y después editar crea un borrador nuevo; descartar vuelve a `published`.

**T3 · Documento (frontend)**
- `PlaybookEditor.tsx` (523 líneas) se sustituye por:
  - `PlaybookDocument.tsx`: lectura/edición en línea, autosave, publicar, descartar;
  - `PlaybookStart.tsx`: la caja única (texto, archivo, micro con `VoiceComposer`, plantilla);
  - `PlaybookStepRow.tsx`, `PlaybookObjections.tsx`.
- La lógica pura sigue en `src/lib/playbook-editor.ts`, con tests en `playbook-editor.test.ts`: `visibleObjections(answers, frequencies)`, `validationToShow(step, touched)`, `publishBlocker(steps, objections) -> {code, stepIndex}`, `autosaveState` (idle/saving/saved/error).
- Solo tokens existentes (`THEME_TOKENS`, `Button` outline/ghost, `IconAction`, `VocifySpinner`, `ConfirmAction`).

**T4 · Lista de playbooks (frontend)**
- `PlaybooksSection.tsx`: filas (4.1) en vez de pestañas y tarjetas; una sola fila abierta a la vez; desaparece `PlaybookSetupNotice` con el flag encendido; se oculta el formulario «Añadir tipología»; los tipos propios ya existentes llevan la línea «No se aplica a ninguna llamada todavía».
- `SalesProcessPage.tsx`: pasa `objection_categories` (ya cargado) a la sección para ordenar las objeciones.
- `src/lib/playbook-setup.ts`: `playbookRows(motions, roles, flags)` con tests.

**T5 · Vista del comercial**
- `PlaybookPage.tsx`: `PlaybookDocument` en modo lectura arriba (tipos visibles para su `sales_role`, vía `GET /playbooks` que ya filtra por rol) y mejores llamadas debajo. Estado vacío: «Tu Head of Sales aún no ha publicado el proceso».

**T6 · Textos**
- `src/lib/product-catalog.ts` (es/en). Cortos, sin tono de asistente. Se eliminan las claves que dejan de usarse.

### Fase 2 · Catálogo de tipos y enrutado

Flag: `PLAYBOOK_ROUTING_ENABLED`.

**T7 · Datos**
- Migración `066_playbook_rules.sql` (+ `.down.sql`): `playbooks.label TEXT NULL`, `playbooks.applies_to JSONB NULL` = `{role: sdr|ae|any, channels: [call|meeting|visit], contact: new|contacted|inbound|any, deal_stages: [id…]}`.
- Catálogo (sección 2.2) en `backend/app/services/playbooks/catalog.py`: clave, rol, objetivo, `applies_to` por defecto, plantilla (se mueven aquí las plantillas de `playbook-editor.ts`, y el front las pide a `GET /playbooks/catalog`).
- `GOAL_FOR_MOTION` gana `inbound`, `ae_discovery` y `negotiation`. `process_health.MEASURABLE_GOALS` no cambia: solo `meeting_booked` se mide en una llamada.

**T8 · Enrutado**
- `motion.py::motion_for(sales_role, interaction_kind, context)`, puro. Orden:
  1. `sales_motion_key` explícito (igual que hoy);
  2. la regla más específica que encaje **y** tenga versión publicada (más condiciones gana; si empatan, el orden de la lista);
  3. la de su rol por defecto (D5 de hoy);
  4. el único publicado (hoy).
- `context` sale de lo que ya hay al fijar: contacto nuevo o ya contactado (misma señal que `never_contacted` de Hoy), inbound (propiedad de origen del contacto en el CRM, si la hay) y etapa del deal (`deal_lookup.py`).
- **Re-fijado antes de C04:** si al reservar la captura no se conocía el deal (reuniones de AE por Recall o desktop), `memo_extraction_hooks` vuelve a calcular el tipo justo antes de extraer. El checklist en directo usa el tipo del rol mientras tanto.
- Tests: tabla completa de `motion_for`; dos playbooks de AE con etapas; sin CRM → rol por defecto; re-fijado.

**T9 · UI de «Cuándo se aplica»**
- Una línea bajo el objetivo: «Se aplica a: llamadas de SDR a contactos nuevos · cambiar». «Cambiar» abre un popover con 3 selectores (rol, canal, contacto) y etapas del CRM solo si hay CRM conectado.
- «+ Tipo de llamada» vuelve y abre el catálogo (los 5 tipos + «Otro»). «Otro» pide nombre y regla; sin regla no se crea (P1).
- `closing` se llama «Demo y cierre» si la empresa no tiene `negotiation`, y «Demo» si la tiene (`flowLabel`).

**T10 · Corregir el tipo de una llamada**
- `MemoDetail.tsx`: «Evaluada como: Demo · cambiar» (autor y managers). Cambiar vuelve a fijar la versión, vuelve a correr C04 (observaciones) y el scoring. Rara vez se usará, pero es la salida cuando el enrutado se equivoca.

### Fase 3 · El playbook aprende de las llamadas

**T11 · % por paso en el documento**
- Nuevo agregado en `team_insights`: por `step_id` de la versión activa, cumplido / (cumplido + fallado) en el periodo, desde `extraction.intelligence.playbook_observations`. Con menos de 10 llamadas no se muestra número. Requiere `PLAYBOOK_OBSERVATIONS_ENABLED` encendido.
- El paso con el % más bajo se resalta (solo el color del número, nada más).

**T12 · Objeciones con datos**
- Cada categoría muestra su frecuencia y, si no tiene respuesta y hay `best_example` (Lista 3 T11), «Usar la respuesta de una llamada del equipo» rellena `guidance` con esa cita, **sin nombre** del comercial (lo mismo que se decidió para «sin ranking»).

---

## 8. Edge cases

| Caso | Qué ve el Head of Sales | Cómo sigue |
|---|---|---|
| Primera vez, nada creado | Filas con «Crear» y la caja única al abrir | Escribe, dicta o pulsa plantilla |
| Pega 3 palabras («llamamos y agendamos») | 1–2 pasos + línea «Muy poco para un proceso; añade lo que falta» | Edita o añade pasos |
| Sube un folleto sin proceso | «No hemos encontrado un proceso en este documento» + la plantilla ofrecida | Plantilla o dictar |
| PDF escaneado o cifrado | Mensajes de hoy (`playbookPdfNoText`, `playbookPdfEncrypted`) | Pegar el texto |
| Audio sin voz o STT caído | «No se ha entendido el audio» | Escribir o reintentar |
| LLM caído o lento | Pasos separados por líneas + «revisa los pasos» | Edita a mano |
| Documento de 40 pasos | 7 pasos + «Hemos agrupado el proceso en 7 pasos» | Revisa |
| Mezcla de SDR y AE en un documento | Solo lo del tipo abierto; al abrir el otro tipo se ofrece «Usar el mismo documento» | Un clic |
| Importar sobre un playbook con contenido | `ConfirmAction` de hoy («Reemplazar pasos») | Confirmar o cancelar |
| Cierra la pestaña a mitad | Borrador guardado (autosave) | Al volver sigue donde lo dejó |
| Autosave falla (red) | «Sin guardar · reintentar» en `capsLabel` y el texto sigue en pantalla | Reintento automático a los 5 s y manual |
| Dos managers editando a la vez | Gana el último guardado; el otro ve «Actualizado por otra persona · recargar» (comparar `updated_at`) | Recargar |
| Publicar con cambios a mitad de semana | «Activo en las llamadas nuevas. Las anteriores mantienen su versión» | Nada |
| Tipo propio existente sin regla (fase 1) | «No se aplica a ninguna llamada todavía» | En fase 2, «Añadir regla» |
| Dos reglas encajan (fase 2) | Ve en la grabación cuál se usó | «cambiar» en la grabación |
| Comercial sin playbook publicado | «Tu Head of Sales aún no ha publicado el proceso» | Nada que hacer |
| Idioma de la fuente ≠ idioma de la app | El documento sale en el idioma de la fuente | Correcto: es su guion |

---

## 9. Fuera de alcance (a propósito)

- **Guion palabra por palabra como bloque visible:** se parte en pasos y frases; el original queda como fuente.
- **Battlecards por competidor:** la categoría `competitor` cubre la respuesta general. Una respuesta por competidor con nombre vendría después, usando `competitor_mentions` de C04 v4.
- **Playbooks por comercial, historial de versiones visible y playbooks multidioma.**
- **«Paso clave» con peso en el scoring** (2.3).
- **Tipos ilimitados sin regla** (P1).

---

## 10. Definition of Done (por fase)

- [ ] Reutiliza patrones y tokens existentes; ningún color, espaciado ni botón nuevo.
- [ ] Primera vista de un playbook vacío: 1 caja + 1 botón + 1 enlace. Nada más.
- [ ] De fuente a playbook publicado en ≤ 3 clics.
- [ ] Ningún error visible antes de que el usuario toque el campo.
- [ ] Vacío, cargando, error y fallback del LLM diseñados.
- [ ] Texto de IA: criterios observables, respuestas decibles, sin frases de `text_guard`. Evals P01 en verde 3 veces.
- [ ] Un tipo de llamada visible siempre se aplica a alguna llamada (fase 2) o dice que no lo hace (fase 1).
- [ ] Backend: `cd backend && /home/user/venv/bin/python -m pytest -q -p no:cacheprovider`. Frontend: `node --experimental-strip-types --test src/lib/*.test.ts src/features/**/*.test.ts`. Tipos: ningún error nuevo en `npx tsc -p tsconfig.app.json --noEmit`. `npm run build`.
- [ ] **Verificación en la app con Reticle** (`reticle_act_and_wait`, nunca solo lectura), guardando cada flujo con su `intent`:
  1. Head of Sales pega un guion → «Crear playbook» → aparecen pasos → Publicar → la fila pasa a «Activo». `intent`: «un Head of Sales tiene un playbook activo a partir de su guion sin rellenar un formulario».
  2. Recargar a mitad de la edición conserva el borrador. `intent`: «no se pierde lo escrito».
  3. Un comercial abre Playbook y ve los pasos publicados. `intent`: «el comercial ve la rúbrica con la que se le evalúa».

---

## 11. Decisiones que necesito del founder antes de empezar

| # | Pregunta | Propuesta |
|---|---|---|
| Q1 | ¿El catálogo de 5 tipos (2 SDR, 3 AE) es el correcto para vuestros clientes? | Sí; cualificación y rellamada como tipo propio con regla |
| Q2 | ¿Fase 1 oculta «Añadir tipología» hasta que exista el enrutado? | Sí; crear tipos que no se aplican es peor que no poder crearlos |
| Q3 | ¿Autosave + una sola acción «Publicar», o se mantiene «Guardar borrador»? | Autosave |
| Q4 | ¿El comercial ve el playbook en «Playbook» encima de las mejores llamadas? | Sí |
| Q5 | Aviso a partir de 7 pasos (límite duro en 15) | Sí |
| Q6 | ¿La respuesta del equipo (fase 3) se copia sin nombre del comercial? | Sí, por «sin ranking» |

**Orden de entrega:** Fase 1 (T1–T6) → encender en Vocify y en 1 cliente → Fase 2 (T7–T10) → Fase 3 (T11–T12) cuando `PLAYBOOK_OBSERVATIONS_ENABLED` lleve 2 semanas encendido con evals v4 corridas.

---

## 12. Contratos de API (fijados antes de implementar; front y back trabajan contra esto)

Decisiones Q1–Q6: se aplican las propuestas de la sección 11 (el founder pidió construirlo tal cual).

Todas las rutas bajo `/api/v1`. Errores de validación: `422 {detail: {code, index?}}`. Permisos: escribir = owner/admin (`_guard`); leer = cualquiera de la empresa, con el filtro por rol de hoy.

### Flags (config.py + `CLIENT_FLAGS` en `feature_flags.py`, apagados por defecto)
- `PLAYBOOK_V2_ENABLED` — UI nueva (lista en filas, documento, caja única, vista del comercial).
- `PLAYBOOK_ROUTING_ENABLED` — catálogo, reglas «cuándo se aplica», enrutado y «cambiar tipo» en una grabación.

### Fase 1
**`POST /playbooks/{key}/structure`** — body `{kind: "text"|"pdf"|"audio", payload: string, name?: string}` (pdf/audio en base64).
→ `200 {sales_motion_key, steps: [{step_id?, label, criterion, example?}], objections: [{category, guidance}], reason: null|"no_process"|"too_short"|"grouped", fallback: bool, source: {id, kind, name}|null}`
- `fallback: true` = el LLM falló o no pasó las guardas; los pasos vienen del parser determinista (port en Python de `parsePlaybookText`).
- Fallos de lectura: `422 {detail:{code: "pdf_encrypted"|"pdf_has_no_text"|"audio_has_no_speech"|"stt_unavailable"|"unsupported_source"|"empty_source"}}`.
- No crea versión. Guarda la fuente en `playbook_imports` (`kind`, `draft.text`, `draft.name`).

**`GET /playbooks/{key}/editor`** — añade: `updated_at: string|null` (del borrador/versión devuelta), `has_live: bool`, `source_doc: {id, kind, name}|null` (`source` ya es el estado `"draft"|"published"|"empty"`).

**`PUT /playbooks/{key}/draft`** — body añade `base_updated_at?: string|null` y `source_id?: string|null`.
- Si existe un borrador más nuevo que la versión activa → se **actualiza esa fila** (mismo `version_id`); si no, se inserta uno.
- Si `base_updated_at` llega y no coincide con el `updated_at` del borrador pendiente → `409 {detail:{code:"stale_draft"}}`.
- Respuesta = misma forma que `GET /editor`.

**`DELETE /playbooks/{key}/draft`** — borra el borrador pendiente (nunca una versión publicada) → forma de `GET /editor` (`source` "published" o "empty").

Migración `066_playbook_draft_autosave.sql`: `playbook_versions.updated_at TIMESTAMPTZ NOT NULL DEFAULT now()` + trigger que lo actualiza.

### Fase 2
`applies_to` = `{role: "sdr"|"ae"|"any", channels: ("call"|"meeting"|"visit")[], contact: "new"|"contacted"|"inbound"|"any", deal_stages: string[]}`.

**`GET /playbooks`** — añade `details: {[key]: {label: string|null, role: "sdr"|"ae"|"any"|null, applies_to: AppliesTo|null, goal: string|null, catalog: bool}}` (siempre; aditivo).

**`GET /playbooks/catalog`** → `{types: [{key, role, goal, applies_to, label: {es, en}, template: {es: Step[], en: Step[]}}]}` con `discovery`, `inbound`, `ae_discovery`, `closing`, `negotiation`.

**`POST /playbooks/types`** — body `{type_key, name, applies_to?}`. Con `PLAYBOOK_ROUTING_ENABLED` y un tipo que no es del catálogo, sin `applies_to` → `422 {code:"rule_required"}`. Para un tipo del catálogo, `applies_to` por defecto del catálogo. → `{motions, details}`.

**`PUT /playbooks/{key}/rule`** — body `{applies_to}` → `{sales_motion_key, applies_to}`.

**`GET /playbooks/deal-stages`** → `{stages: [{id, label}]}` de la CRM conectada; `[]` si no hay.

**`POST /memos/{memo_id}/playbook`** — body `{sales_motion_key}` (autor o manager). Vuelve a fijar la versión activa de ese tipo, vuelve a correr C04 y scoring → `{sales_motion_key, playbook_version_id, status: "requeued"}`. `409 {code:"not_published"}` si el tipo no tiene versión activa.

**`GET /memos/{memo_id}/playbook`** → `{sales_motion_key: string|null, playbook_version_id: string|null, can_change: bool, options: [{key, label: string|null}]}` (`options` = tipos con versión activa; `can_change` = flag de enrutado y autor u owner/admin).

Migración `067_playbook_rules.sql`: `playbooks.label TEXT NULL`, `playbooks.applies_to JSONB NULL`.

### Fase 3
**`GET /playbooks/{key}/insights?period=week|month`** (managers) →
`{period, calls: int, steps: [{step_id, met, missed, rate: number|null}], objections: [{category, count, share: number, answered: bool, best_example: string|null}]}`
- `rate` = met/(met+missed) con ≥ 10 aplicables; si no, `null`. Solo `step_id` de la versión activa.
- `objections` ordenadas por `count` desc; `best_example` sin nombre de comercial.

### Una sola entrada para toda la empresa
**`POST /playbooks/structure`** (owner/admin) — body igual que `POST /{key}/structure` (`{kind, payload, name?}`), mismos `422 detail.code` de lectura. Vocify detecta qué tipos de llamada cubre el documento (con `PLAYBOOK_ROUTING_ENABLED`: los 5 del catálogo y los tipos propios con regla; sin él: `discovery` = todo lo de SDR/prospección y `closing` = todo lo de AE), estructura cada uno con UNA llamada al modelo (`playbook_split_v1`, ≤ 2 con el reintento por criterios genéricos; 85 s por llamada y el reintento solo si cabe en 110 s, porque la pantalla espera 120 s y un playbook real de 4 tipos no cabía en 25 s) y guarda cada tipo como borrador (un borrador pendiente se sobrescribe; una versión activa sigue activa). Un tipo del catálogo que la empresa aún no tiene se crea como en `POST /types`.
→ `200 {source: {id, kind, name}|null, fallback: bool, reason: null|"no_process", candidates: [{key, label}], types: [{sales_motion_key, reason: null|"grouped"|"too_short", editor: <forma de GET /editor>}]}`
- `fallback: true` (fallo, timeout o JSON inválido del modelo) → `types: []`, no se adivina el tipo: la UI pregunta cuál es y usa `POST /{key}/structure`.
- `error: {kind: "timeout"|"invalid_answer"|"model_error", detail}` acompaña a `fallback: true` (`null` si no hay fallback); la UI lo enseña bajo la pregunta. Un documento cuyos títulos ya nombran dos o más tipos se parte por esos títulos: una llamada corta por tipo, en paralelo, más la de empresa.
- `reason: "no_process"` → `types: []`.

**`GET /playbooks`** — cada `details[key]` añade `step_count`, `answer_count` (de la versión que el editor enseñaría a un manager: borrador pendiente si hay, si no la activa, si no 0) y `has_draft` (hay un borrador pendiente más nuevo que la activa). Para un comercial cuentan solo la versión activa y `has_draft` es siempre `false`.

---

## 13. Estado (29 sep 2026)

| Pieza | Estado | Dónde |
|---|---|---|
| T1 Estructurar con IA (`POST /structure`, prompt v1, guardas, fallback) | Hecho | `services/playbooks/structure.py`, `prompts/playbook_structure_v1.md` |
| T2 Autosave en la misma fila, 409 `stale_draft`, `DELETE /draft` | Hecho | `store.py`, migración 066 |
| T3–T6 Documento, lista, caja única, vista del comercial, textos | Hecho | `src/features/playbooks/components/*`, `src/lib/playbook-doc.ts` |
| T7 Catálogo, reglas, `details`, `/catalog`, `/rule`, `/deal-stages` | Hecho | `catalog.py`, `routing.py`, `api/playbook_rules.py`, migración 067 |
| T8 Enrutado por regla al fijar y re-fijado antes de C04 | Hecho | `captures.py`, `memo_extraction_hooks.py` (`pipeline_meta.playbook_pin`) |
| T9 «Se aplica a» y «+ Tipo de llamada» | Hecho | `PlaybookList.tsx`, `RuleEditor.tsx` |
| T10 «Evaluada como · cambiar» en la grabación | Hecho | `GET/POST /memos/{id}/playbook`, `MemoPlaybookLine.tsx` |
| T11–T12 % por paso y objeciones con frecuencia y respuesta del equipo | Hecho | `GET /playbooks/{key}/insights`, `services/playbooks/insights.py` |

**Contrato:** `GET /editor` devuelve la fuente en `source_doc` (`source` sigue siendo el estado). `POST /structure` usa el cliente con `timeoutMs: 120_000`.

**Pruebas:** backend 3107 passed, 32 skipped (sin PostgreSQL aislado). Frontend 449 pass. Sin errores de tipos nuevos. `npm run build` OK. La UI se recorrió en navegador (Playwright contra la app real con la API simulada según este contrato): crear desde texto → documento → autoguardado → publicar; editar la versión activa con una respuesta del equipo; regla; tipo nuevo; vista del comercial; 390 px.

**Pendiente antes de encender:**
1. Aplicar a mano en Supabase `066_playbook_draft_autosave.sql` y `067_playbook_rules.sql` (la API lee `updated_at`; sin la 066 falla el editor).
2. Correr `python -u backend/scripts/eval_playbook_structure.py --runs 3` con clave de OpenRouter (P01 no se ha corrido: no había clave).
3. Encender `PLAYBOOK_V2_ENABLED` en Vocify y un cliente; `PLAYBOOK_ROUTING_ENABLED` después, cuando haya dos playbooks publicados de un mismo rol.
4. Confirmar la señal inbound: hoy es `hs_analytics_source` de HubSpot distinto de OFFLINE; Pipedrive no da señal y la regla `inbound` no encaja allí.
5. Reticle: no se pudo verificar con Reticle en esta sesión (sin daemon ni backend con credenciales). Guardar los tres flujos de §10 con su `intent` en staging.

---

## 14. Rediseño tras la revisión del founder (29 sep 2026)

**Qué no funcionaba (visto en staging):** la empresa seguía en el editor viejo (flag apagado), y aun con la v2 el recorrido obligaba a elegir el tipo de llamada antes de dar el documento, no explicaba para qué servía cada parte y ponía el análisis vacío por encima del proceso.

**Qué cambia (sin flag; sale al desplegar):**
- **Una entrada para toda la empresa.** Página vacía = una caja: «Dale a Vocify vuestro playbook» (pegar, PDF, audio o dictado). `POST /playbooks/structure` detecta los tipos de llamada del documento, estructura cada uno y lo guarda como borrador. Si no puede separarlo, pregunta «¿Para qué llamada es?» y usa el flujo por tipo.
- **Resultado legible:** «Hemos encontrado 2 procesos en vuestro documento» y una fila por tipo con «5 comprobaciones · 2 respuestas · Sin activar».
- **Una sola acción para toda la página: «Activar para el equipo».** Guarda lo que se esté escribiendo y activa todos los cambios pendientes. El documento ya no tiene «Publicar»; «Rehacer desde un documento» y «Descartar cambios» van en el menú «···».
- **Títulos que dicen para qué sirve:** «Vocify comprueba en cada llamada» y «Cuando el cliente dice… / El comercial ve».
- **Página:** primero el proceso; «Cómo está funcionando» (salud del proceso, objeciones y sus filtros) solo aparece cuando hay llamadas evaluadas.
- **Fuera del vocabulario:** tipología, borrador, publicar. «Se aplica a» solo cuando decide algo (tipo propio o dos playbooks del mismo rol).
- **Comercial:** la pestaña Playbook sale siempre con su proceso; «Mejores llamadas» solo con `PLAYBOOK_TAB_ENABLED`.
- Se borran `PlaybookEditor.tsx` y `PlaybookSetupNotice.tsx` (editor y aviso de 4 pasos antiguos).

**Activación:** `docs/superpowers/plans/2026-09-29-activacion-playbooks-v2.sql` (migraciones 066 y 067 obligatorias antes de desplegar; `PLAYBOOK_ROUTING_ENABLED` opcional). `PLAYBOOK_V2_ENABLED` queda sin uso en el frontend.

**Pruebas:** backend 3151 passed, 32 skipped. Frontend 453 pass. Build OK. Recorrido en navegador (app real, API simulada según §12): vacío → pegar documento mixto → 2 procesos → revisar → activar; editar uno activo con autoguardado; menú «···»; comercial; 390 px. Evals P01/P02 pendientes de clave.

---

## 15. El molde de tres capas (29 sep 2026)

El Head of Sales da su playbook tal como lo tenga; Vocify lo encaja en este molde. **Lo que el documento no trae se queda vacío: la IA nunca lo inventa.** Lo que no encaja en ningún bloque va a `notes` de «Vuestra empresa». Las plantillas (tipo de llamada, BANT/MEDDIC/MEDDPICC) solo entran si se piden.

| Capa | Qué | Dónde vive | Para qué |
|---|---|---|---|
| 1 · Se evalúa en cada llamada (por tipo) | Pasos · **Qué tiene que salir de la llamada** (cualificación) · Objeciones (fijas y **propias**, con significado, pregunta de diagnóstico, respuesta y prueba) | `playbook_versions` (steps, entries, **qualification**) con borrador y «Activar para el equipo» | Nota por bloques, coaching, brief, directo |
| 2 · Lo que Vocify sabe de la empresa (una vez) | ICP y personas, no encaja, señales de compra, relato de valor (30 s / 3 min), diferenciadores, casos de cliente, **competidores**, precio y negociación, notas | `company_sales_knowledge` (efecto inmediato, sin activar) | Contexto del copiloto, brief, follow-up y Ask. No puntúa |
| 3 · Sale de las llamadas | Ejemplos buenos/malos, mejor respuesta real por objeción, sugerencias | Ya existe (T11/T12, mejores llamadas) | Mantener el playbook vivo |

### Contratos

**Objeciones (entries de la versión).** `{entry_id, category, guidance, label?, trigger?, meaning?, question?, proof?, source_ref}`. `category` ∈ price, timing, authority, competitor, status_quo, trust, other, **custom**. Custom: `entry_id = "objection:custom:<slug>"`, `label` obligatorio (≤ 60), `trigger` = cómo lo dice el cliente (≤ 200). Máx. 12 custom. `meaning`, `question`, `proof` ≤ 200/200/300; `guidance` ≤ 600. Una custom sin `guidance` se guarda igual (se sabe detectar aunque aún no haya respuesta).

**Cualificación (nueva columna `playbook_versions.qualification JSONB NOT NULL DEFAULT '[]'`).** `[{criterion_id, label, why?, good?, bad?}]`, máx. 8, `label` ≤ 60, resto ≤ 200. `criterion_id` = slug estable como `step_id`.

**Editor (`GET /playbooks/{key}/editor`, `PUT /playbooks/{key}/draft`).** Añade:
- `objections: [{category, guidance, id?, label?, trigger?, meaning?, question?, proof?}]` (`id` solo en custom = slug);
- `qualification: [{criterion_id?, label, why?, good?, bad?}]`.
Códigos 422 nuevos: `too_many_criteria`, `criterion_label_empty`, `criterion_label_too_long`, `custom_objection_label_empty`, `too_many_custom_objections`, `field_too_long`.

**`GET /playbooks`** `details[key]` añade `criteria_count`.

**`GET /playbooks/qualification-templates`** → `{templates: [{key: "bant"|"meddic"|"meddpicc", label, criteria: {es: Criterion[], en: Criterion[]}}]}`.

**Vuestra empresa.** Tabla `company_sales_knowledge (company_id PK, data JSONB NOT NULL DEFAULT '{}', source_id TEXT NULL, updated_at TIMESTAMPTZ)`. `data`:
```
{icp, bad_fit, value_short, value_long, pricing, notes: string,
 personas: [{name, cares_about, language, measured_on}],
 triggers: [{signal, how_to_use}],
 differentiators: [string],
 proofs: [{customer, situation, change, number, tags: [string]}],
 competitors: [{name, win_when, lose_when, they_like, landmines, how_to_talk}]}
```
Límites: textos largos ≤ 1500, campos cortos ≤ 300, listas ≤ 12. `GET /playbooks/company` (cualquier miembro) → `{knowledge, updated_at, sections: [claves no vacías]}`. `PUT /playbooks/company` (owner/admin) `{knowledge, base_updated_at?}` → mismo shape; 409 `stale_knowledge`.

**Entrada única (`POST /playbooks/structure`)** además reparte en cualificación, objeciones ampliadas/propias y «Vuestra empresa». Respuesta añade `company: {knowledge, updated_at, sections, filled: [claves rellenadas ahora]} | null`. **Fusión con lo existente:** listas se añaden sin duplicar (por `name`/`customer`/`signal`), un texto solo se rellena si estaba vacío (nunca pisa lo que editó el Head of Sales). Si el documento dice «usamos MEDDIC» (o BANT…), la cualificación usa esos criterios.

**Lectura de cada llamada (C04 `intelligence_v7`, flag `PLAYBOOK_QUALIFICATION_ENABLED`, apagado).** v6 más:
- entrada `playbook_qualification: [{criterion_id, label, good?}]` y `playbook_objections: [{id, label, trigger}]` (solo custom);
- salida `qualification_observations: [{criterion_id, status: found|missing|not_applicable|unknown, value, quote}]` y en cada objeción `objection_id` (id custom o null).

**Nota por bloques (con el mismo flag).** El score añade `blocks: {steps: {met, applicable}, qualification: {met, applicable}, objections: {met, applicable}}`; `value` = media (0–10, redondeada) de los bloques con `applicable > 0`. Coaching: un criterio `missing` produce «No salió: {label}». Sin flag, todo como hoy.

**Consumidores.** Brief y copiloto: la respuesta de una objeción custom se engancha por `objection_id`; el copiloto recibe de «Vuestra empresa» relato corto, diferenciadores, casos y competidores (sin inventar pruebas).

### Estado del molde de tres capas (29 sep 2026)

Hecho: migración 068, cualificación por versión con plantillas BANT/MEDDIC/MEDDPICC, objeciones propias y detalle (significado, pregunta, prueba), «Vuestra empresa» (`GET/PUT /playbooks/company`), reparto del documento en los tres bloques (`playbook_split_v2`/`playbook_structure_v2`), C04 `intelligence_v7` con cualificación y `objection_id`, nota por bloques, brief con respuesta de objeción propia y copiloto con «Vuestra empresa». UI: bloque «Qué tiene que salir de la llamada», objeciones propias, fila «Vuestra empresa» (también en la pestaña del comercial), nota «7/10 · Pasos 4/5 · Cualificación 2/4 · Objeciones 1/1».

Pruebas: backend 3289 passed / 32 skipped; frontend 462; build OK; recorrido en navegador con la API simulada.

Pendiente antes de encender `PLAYBOOK_QUALIFICATION_ENABLED`: correr con clave `scripts/eval_intelligence.py --v7` y `scripts/eval_playbook_structure.py --suite P01|P02|P03 --runs 3`. Migraciones 066, 067 y 068 obligatorias antes de desplegar (`2026-09-29-activacion-playbooks-v2.sql`).

---

## 16. Pausar, reanudar y eliminar (30 sep 2026)

Un Head of Sales tiene que poder, en un gesto y viéndolo: **pausar** un playbook (las llamadas nuevas dejan de evaluarse con él; el contenido se queda), **reanudarlo**, y **eliminarlo** (desaparece de la lista; se puede deshacer). Las llamadas ya evaluadas no cambian nunca: siguen apuntando a su versión.

**UX:** interruptor en la fila (Activo / Pausado); «···» en la fila con «Eliminar playbook» (confirmación + toast «Deshacer»). Un tipo de llamada propio vacío (p. ej. los «sdr»/«sales» del editor viejo) también se elimina así.

**Datos (migración `069_playbook_pause_archive.sql`):** `playbooks.paused_version_id UUID NULL`, `playbooks.archived_at TIMESTAMPTZ NULL`, `playbooks.archived_state TEXT NULL` (estado previo, para deshacer). `list_playbook_motions` excluye los archivados y devuelve `paused` cuando `active_version_id IS NULL AND paused_version_id IS NOT NULL`. Pausar = mover `active_version_id` a `paused_version_id` (así todo lo que lee la versión activa —fijar a la llamada, copiloto, brief, insights, enrutado— la ignora sin cambios).

**API (owner/admin; 409 `{code}` cuando no aplica):**
- `POST /playbooks/{key}/pause` (solo si está publicado; `not_published`) · `POST /playbooks/{key}/resume` (`not_paused`) → `{motions, details}`.
- `DELETE /playbooks/{key}` → archiva, guarda `archived_state`, pasa la versión activa a `paused_version_id`, borra los borradores pendientes, desactiva `interaction_types` de ese tipo → `{motions, details}`. Tipos sin fila en `playbooks` (solo `interaction_types`) también.
- `POST /playbooks/{key}/restore` (deshacer) → vuelve a `archived_state` (publicado → activo de nuevo) → `{motions, details}`.
- Guardar un borrador o crear el tipo sobre uno archivado lo desarchiva sin traer el contenido viejo. Publicar limpia `paused_version_id`.
- `GET /playbooks` `details[key]` añade `paused: bool`. `GET /{key}/editor` de uno pausado devuelve esa versión como `source: "published"` con `paused: true`.

---

## 17. Refactor de arquitectura (30 sep 2026) — sin cambios de producto

**Por qué:** varias escrituras de varios pasos iban sueltas por PostgREST (sin transacción); la 069 sobrecargaba `active_version_id` (nulo = «nunca publicado», «pausado» o «eliminado»); `store.py` implementaba todo dos veces (memoria y Supabase) con un falso PostgREST en los tests; `api/playbooks.py` y `PlaybookList.tsx` tenían cinco responsabilidades cada uno.

**Decisiones (no se reabren):**
1. **Una migración** `066_playbooks_v2.sql` (+ `.down.sql`) sustituye a 066–069. Idempotente y **segura si ya se aplicaron 066–069**: añade lo que falte, rellena `state`/`archived_at` desde `paused_version_id`/`archived_state` si existen y borra esas columnas.
2. **Esquema final.** `playbooks`: `label`, `applies_to`, **`state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active','paused'))`** (interruptor) y **`archived_at`** (borrado suave, ortogonal al interruptor). `active_version_id` vuelve a significar solo «la versión publicada»: pausar o eliminar **no la toca**. `playbook_versions`: `updated_at`, `qualification`. Tabla `company_sales_knowledge`.
3. **Qué aplica a una llamada** = `active_version_id IS NOT NULL AND state = 'active' AND archived_at IS NULL`. Vista SQL `playbooks_live` y **un único acceso en Python** (`services/playbooks/live.py`). Ningún otro módulo lee `active_version_id` para decidir qué aplica.
4. **Escrituras atómicas en Postgres** (funciones, como ya era `publish_playbook_motion`): guardar borrador con control de conflicto dentro del mismo `UPDATE … WHERE updated_at = base`; cambiar estado (`pause`/`resume`/`archive`/`restore`); guardar «Vuestra empresa» con control de conflicto; entrada única (todos los borradores + empresa en una transacción). Publicar pone `state='active'` y `archived_at=NULL`.
5. **Repositorio con una interfaz** (`Protocol`): `SqlPlaybookRepository` (llamadas finas a esas funciones y lecturas) e `InMemoryPlaybookRepository` (solo para tests de API). **Una suite de contrato** se ejecuta contra los dos (el SQL contra Postgres real cuando lo hay); así no pueden divergir. Se elimina el falso PostgREST.
6. **API por responsabilidad:** `playbooks.py` (lista, editor, borrador, publicar, estado), `playbook_intake.py` (estructurar e importar), `playbook_company.py` («Vuestra empresa»), `playbook_rules.py` y `playbook_insights.py` como están. Rutas y respuestas idénticas.
7. **Frontend:** `PlaybookList` → hook de acciones + `IntakePanel`, `PlaybookRow`, `RuleLine`, `AddTypeMenu`; `PlaybookDocument` → hook de borrador (carga, autoguardado, conflicto, vaciado) + vista. Mismo comportamiento.

**Criterio de hecho:** mismos contratos de API; todos los tests de API existentes pasan sin cambiar sus expectativas (salvo los que probaban detalles internos del almacenamiento); suite de contrato en verde contra memoria y contra Postgres real; los recorridos del navegador (crear, activar, editar, pausar, eliminar, deshacer, empresa) iguales.

### Estado del refactor (30 sep 2026)

Hecho y en `staging`, un commit por paso:

| Paso | Qué | Verificación |
|---|---|---|
| 1 | `066_playbooks_v2.sql` (+ `.down.sql`) sustituye a 066–069; funciones SQL atómicas; `full_reset.sql` alineado | `test_migration_066.py`: aplica sobre una base vacía y **sobre una base que ya tenía 066–069** |
| 2 | Un solo camino de lectura de «qué aplica a una llamada»: vista `playbooks_live` + `services/playbooks/live.py`; los lectores (briefs, captures, coaching, copilot, CRM copilot, team insights, routing) dejan de leer `active_version_id` | `test_live.py` (el doble de la vista se comprueba contra la vista real) |
| 3 | `PlaybookRepository` (Protocol) + `SqlPlaybookRepository` + `InMemoryPlaybookRepository`; se borra `store.py` y el falso PostgREST | `test_repository_contract.py`: los mismos escenarios contra memoria y contra **PostgreSQL 16 real** |
| 4 | API por responsabilidad: `playbooks.py`, `playbook_intake.py`, `playbook_company.py`, `playbook_rules.py`, `playbook_insights.py`; lo compartido en `services/playbooks/api_support.py` | rutas y respuestas idénticas; humo sobre el router real (`/company`, `/catalog`, `/structure` no se confunden con `/{key}`) |
| 5 | Frontend: hooks + componentes de una sola responsabilidad (ya estaba) | 650 tests de front, build |

Suite de backend: 3433 pasan, 30 saltados (los que necesitan servicios externos), con `VOCIFY_TEST_PG_DSN` apuntando a un Postgres 16 real: los 76 tests de contrato SQL se ejecutan.

Pendiente fuera del código: aplicar `066_playbooks_v2.sql` en Supabase justo antes de desplegar (el código nuevo lee `playbooks_live`; el desplegado antes lee `paused_version_id`, que la migración borra), y pasar las evals con clave de OpenRouter antes de activar `PLAYBOOK_QUALIFICATION_ENABLED`.


### Rediseño de la pantalla (30 sep 2026)

**Por qué:** la pantalla era un acordeón. Abrir un tipo de llamada desplegaba el documento entero (pasos, cualificación y objeciones) y obligaba a hacer mucho scroll. Todo el texto pesaba lo mismo y había una línea en cada fila. «Vuestra empresa» enseñaba siete secciones vacías, con etiquetas repetidas como placeholder. Además, una importación larga caía en el parser de líneas (timeout de 25 s) y daba 15 «pasos» como «1» o «**Equipo y volumen», o nombres cortados a mitad de palabra.

**Decisiones:**
1. **Lista y detalle en lugar de acordeón.**
   - A la izquierda (`ProcessNav`) están «Vuestra empresa» y cada tipo de llamada, con su icono y un punto de estado. Al final, «+ Tipo de llamada» e «Importar documento».
   - A la derecha va el elemento abierto.
   - En el móvil, la lista pasa a una fila con scroll horizontal.
   - Elegir un tipo de llamada cuesta un clic y nunca alarga la página.
2. **Pestañas por capa.**
   - Un tipo de llamada tiene tres pestañas: Pasos, Cualificación y Objeciones. Cada una lleva icono y recuento, y un punto de aviso si falta algo (un paso sin «cuenta como hecho cuando» o una objeción sin respuesta).
   - «Vuestra empresa» tiene cinco pestañas: Cliente, Oferta, Casos, Competencia y Notas.
   - Las pestañas son `components/ui/tabs.tsx`, reestilizado con subrayado para que sean idénticas a `.v-tabs` de la revisión post-llamada.
3. **Sin modo Editar/Listo.**
   - Un manager escribe directamente y el cambio se guarda solo.
   - «Guardado» aparece con un check y se desvanece (`SaveStatus`). Solo se queda en pantalla si hay error o conflicto, con la acción que lo arregla.
4. **Jerarquía.**
   - Nombres en peso medio y descripción apagada debajo; los pasos llevan número en un círculo.
   - Sin líneas entre filas: separa el espacio, y al pasar el ratón aparece un tinte.
   - Tokens nuevos: `typography.groupTitle`, `typography.fieldLabel` y `radius.control`. `sectionTitle` pasa a peso medio en toda la app.
5. **Primer valor.**
   - Sin nada creado, la caja de entrada es toda la sección.
   - Con «Vuestra empresa» vacía, la primera acción es «Importar documento».
   - Cada campo tiene su etiqueta encima y un ejemplo como placeholder.
   - Hay un solo aviso arriba, «N tipos de llamada tienen cambios…», con el botón «Activar para el equipo».
6. **Importación.**
   - El parser determinista (`parse_playbook_text` y `parsePlaybookText`, iguales en back y front) entiende esquemas: cada título numerado es un paso y lo que va debajo, su descripción. Los títulos sin número se tratan como contexto.
   - Quita el markdown, nombra el paso por su primera cláusula sin cortar palabras y recorta la descripción por frases.
   - El modelo tiene 60 s con documentos de 2 500 caracteres o más (antes 25 s). El markdown que copie el modelo también se quita.

**Mapa de densidad:**

| Capa | Qué aparece |
|---|---|
| Superficie | Nombre, rol, estado e interruptor, objetivo, pestañas con recuento y el contenido de la pestaña activa |
| Al pasar el ratón | Mover, eliminar y añadir frase; el porcentaje de cumplimiento con tooltip; el estado del punto |
| Un clic | Otra pestaña, otro tipo de llamada, «···» (reconstruir, descartar, eliminar), detalles de una objeción o de un criterio |
| Nunca aquí | Ajustes del producto (enlace a Ajustes → Oferta) |

**Pendiente:** los playbooks importados antes siguen con los pasos rotos. Se rehacen desde «···» → «Reconstruir desde un documento».

### Editar sin formularios (30 sep 2026, segunda vuelta)

**Por qué:** después de la primera importación, cambiar algo seguía siendo rellenar casillas (una para «suele significar», otra para «pregunta», otra para «prueba»…), y lo que la importación no encontraba se quedaba vacío para siempre. Además no se veía qué estaba activo ni dónde se usaba cada tipo de llamada.

**Decisiones:**
1. **«Dile a Vocify» (`FillBox`).** Encima de cada playbook y de «Vuestra empresa» hay una línea para escribir, dictar o soltar un archivo. `POST /playbooks/{key}/fill` y `POST /playbooks/company/fill` (`services/playbooks/fill.py`, prompts `playbook_fill_v1` y `company_fill_v1`).
   - El modelo devuelve solo los cambios y el código los aplica: pasos y criterios por índice, objeciones por categoría o por etiqueta, elementos de la empresa por nombre.
   - Lo que no se nombra no se toca. Todo pasa por los mismos normalizadores que un guardado.
   - Se mantienen los guardas de la estructuración: sin markdown, sin actitudes como criterio, sin competidores ni cifras que nadie dio.
   - El playbook no se guarda en el servidor. El editor lo mete en su borrador (autoguardado, conflicto, nada llega al equipo hasta publicar). «Vuestra empresa» se guarda al momento con `base_updated_at`.
   - En los dos casos sale un toast con el resumen y «Deshacer».
2. **Todo se lee como frases.** Nombre en peso medio y el texto debajo, editable donde se lee (`InlineTextarea` sin bordes, solo un tinte). Los detalles salen solo si tienen texto (`FieldLine`, con la etiqueta como entrada: «Ganamos cuando …»).
   - Lo que falta es un «✦ Completar con Vocify», que escribe la petición por el manager (`CompleteButton`).
   - Cada elemento tiene un «···» en la línea del título: añadir un campo, mover, eliminar (`ItemMenu`). Adiós a la papelera flotante y a las cajas.
3. **Sugerencias desde las llamadas.**
   - Objeciones que el equipo oye sin respuesta: fila fantasma con la respuesta del mejor comercial («Usar») o «Escribir la respuesta».
   - Sin nada escrito ni oído: precio, momento y autoridad como punto de partida.
   - Competidores mencionados en llamadas que no están en la lista (`competitor_mentions` de `/team/adherence`, la misma caché que la página): «+ Nombre · 7».
   - «Descartar» se recuerda en este navegador (`useDismissed`).
4. **Estado y publicación por tipo de llamada.** Esto sustituye a la decisión 16 de «Activar para el equipo» para toda la página.
   - La cabecera dice en una frase dónde se usa y qué es éxito (`usedForLine`), el estado en una palabra (`publishState`: Activo, Cambios sin publicar, Sin publicar, Pausado, Sin crear) y la acción que toca: «Publicar», o el interruptor una vez publicado.
   - La lista muestra la misma palabra. Sin icono de objetivo.
5. **Iconos.** Se quedan los de Phosphor, que ya usan las tres superficies. itshover.com no encaja (React y una librería de animación; la extensión y el escritorio no son React). El movimiento, si hace falta, va por el `AnimIcon` compartido.

**Tercera vuelta (30 sep 2026):**
- **«Completar» toca solo su elemento.** `scope` en `/fill` y `/company/fill`: `restrict_to` y `restrict_company` descartan cualquier otro cambio del modelo (antes, «Escribir la respuesta» en una objeción reescribía las cuatro). El botón no desaparece mientras escribe: dice «Escribiendo…» y la línea de «Dile a Vocify» dice «Vocify está escribiendo…».
- **Las objeciones son lo que dice el cliente.** `trigger` («Ahora mismo no tenemos presupuesto») vale también para las categorías fijas (`normalize_objections`, `objection_view`; el prompt de fill lo rellena siempre). Sin él, se muestra cómo suele sonar esa objeción. La categoría pasa a ser una etiqueta pequeña al lado.
- **Nada escondido en un menú ni cajas al pasar el ratón.** «+ Suele significar», «+ Frase para decir», etc. aparecen solo mientras se edita ese elemento (`EditAdds`). El «···» queda para mover y eliminar. Los campos ya no se tiñen al pasar el ratón; solo el cursor de texto.
- **Pasos mal importados.** `messySteps` detecta nombres que son solo un número, descripciones que empiezan por su numeración o nombres cortados a mitad de palabra. «Ordenar con Vocify» los estructura otra vez desde su propio texto (`stepsAsText`); objeciones y cualificación se quedan como están, y hay «Deshacer».

### Simplificación aprobada (30 sep 2026)

Aprobada sobre `docs/superpowers/mockups/playbook-editing.html`. **Regla: cada elemento es un nombre en negrita y una línea.** Todos los ajustes usan la misma fila (`DocRow`): marca a la izquierda, nombre, etiqueta o menú a la derecha, una línea debajo y una línea fina entre elementos.

- **Objeción** = lo que dice el cliente (`trigger`), su tipo y la respuesta (`guidance`). Se quitan `meaning`, `question` y `proof` de la pantalla, del modelo de datos (`normalize_objections`, `objection_view`), de lo que escribe Vocify y de la validación. Las antiguas se borran al siguiente guardado (opción 2).
- **Criterio de cualificación** = qué averiguar y cómo suena una buena respuesta (`good`). Se quitan `why` y `bad`; la puntuación solo usa `label` y `good`.
- **Métodos por rol** (`catalog.py`: `roles` y `summary`).
  - SDR: BANT, CHAMP, ANUM, GPCT.
  - AE: MEDDIC, MEDDPICC, SPICED, BANT.
  - Más «Propio». La tarjeta marcada es la del método del que salen exactamente los criterios (`matchedMethod`).
- **«Vuestra empresa»**: cada elemento es su nombre y una línea, la que usan el copiloto y los briefs.
  - Persona: qué le importa (`cares_about`).
  - Señal: qué hacer (`how_to_use`).
  - Caso: qué consiguió (`change`).
  - Competidor: cómo ganarles (`how_to_talk`).

  `LIST_FIELDS` pierde el resto. El guarda contra cifras inventadas pasa de `number` a `change`. El copiloto ya no pinta «Do not say» ni situation/number.
- **Tipografía**:
  - `panelTitle`: 22px, 600.
  - `itemTitle`: 15px, 600.
  - `itemBody`: 14px, texto al 80 %.
  - `groupTitle` pasa a 600.
  - Pestañas: la activa en 600 con la línea marrón. Lo mismo en `.v-tabs` compartido (extensión y escritorio sincronizados).
- **Glass solo en lo que flota**: «Dile a Vocify» se queda abajo (sticky) y la lista pasa por debajo; la entrada seleccionada de la lista usa `glass-nav`. El contenido va sobre papel.

**Pendiente:** `playbook_structure_v2` y `playbook_split_v2` todavía piden los campos quitados. El código los descarta, así que no cambia nada visible. Recortar esos prompts necesita pasar las evals con la clave de OpenRouter.
