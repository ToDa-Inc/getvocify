# Vocify · Lista 2 y armonía del producto — plan (26 sep 2026)

**Estado:** propuesta, pendiente de confirmación del founder. No se ejecuta nada hasta entonces.

**Fuentes:**
- las reuniones del 21 sep (Coaching, reportes y features con Danilo; Estrategia de IA y automatización; Automatización de tareas y coaching) y del 25 sep (demo con Mario Rey);
- la Lista 2 de la revisión reunión-vs-código;
- lo construido hoy (11 commits en `staging`);
- el mapa del código actual;
- `MASTER_PLAN.md`, `PLAN_INTEGRACION.md` y el plan v1 del 22 sep.

**Decisiones tomadas en esta conversación:**
- brief v2 aprobado (gancho, por qué llamas, qué decir y etiqueta de punto del proceso);
- la etapa del deal la confirma el comercial;
- una reunión solo cuenta con invitación y los dos acuden.

**Fuera de alcance, ya decidido:**
- desktop Windows, overlay en vivo y tarjeta de objeción en directo (Dani);
- firma del DMG;
- pricing (pendiente con Dani);
- biblioteca de mejores llamadas (V2);
- brief desde el calendario (más adelante);
- conexión directa a Gmail;
- merge a `main`;
- subir el permiso `sales-email-read`.

**Ideas aparcadas para leer más adelante:** `2026-09-26-ideas-sinergias-para-mas-adelante.md`.

---

## 0. En cinco líneas

1. Vocify gira alrededor de una sola cosa: **cada conversación de venta produce unos pocos hechos** (dolor, objeción, compromiso, reunión, en qué punto está la venta, competidor), y todo lo demás (CRM, Hoy, preparación, follow-up, coaching, informes) reutiliza esos mismos hechos.
2. Con lo hecho hoy, la mayor parte de la Lista 2 está resuelta. Quedan tres huecos:
   - el follow-up (estilo desde el primer día y evals);
   - el brief previo (dolor, gancho, pitch, competidor);
   - el cierre de Equipo (F15).
3. Al estudiar si los cuatro objetivos se cumplen de verdad aparecen **cinco cortes más**:
   - las visitas por WhatsApp se saltan el pipeline;
   - los compromisos van al CRM por un camino y a Hoy por otro;
   - no hay preparación de cold call ni de reunión;
   - con la autoaprobación activada, la etapa y la reunión se quedan sin confirmar.
4. El plan tiene nueve entregas en cinco olas: primero los cimientos (un pipeline, un compromiso), después las salidas (preparación, follow-up, confirmaciones) y por último el cierre (Equipo y prueba de armonía).
5. Se cierra con una **prueba de armonía**: una conversación de ejemplo recorre todo el sistema, por llamada y por WhatsApp, y cada superficie tiene que enseñar los mismos hechos.

---

## 1. Qué tiene que hacer Vocify (el output que queremos)

**Promesa (reunión 21 sep):** «Capturamos todo en tracción comercial y te ayudamos a vender más.» El comercial solo vende. Vocify es proactivo, no reactivo: acabas la llamada y el follow-up ya está redactado.
**Dos audiencias:** el comercial adopta si le quitamos trabajo; el head of sales compra por consistencia y visibilidad. Primero productividad al comercial, después información al manager. El comercial nunca debe sentirse vigilado: las vistas de equipo no hacen ranking.

### 1.1 Los cuatro objetivos y su output concreto

| Objetivo | Output que ve la persona | Criterio de «funciona» |
|---|---|---|
| **1. Vocify está en cada interacción** | La llamada (dialer propio o HubSpot calling), la reunión (desktop o extensión) y la visita (nota de voz por WhatsApp) acaban en la misma ficha de conversación, con la misma calidad de extracción. | Las tres vías pasan por el mismo pipeline y producen los mismos hechos. |
| **2. El CRM se actualiza casi solo** | Con contacto y deal claros y la autoaprobación activada, el CRM se guarda solo. Lo que tiene consecuencias (etapa, reunión) le llega al comercial como una confirmación de un clic. Sin autoaprobación, una sola pantalla de revisión con todo ya relleno. | Lo que se escribe en el CRM es lo mismo que Vocify enseña en Hoy, en la preparación y en el follow-up. Nada se queda pendiente sin que el comercial se entere. |
| **3. El admin se hace solo** | **Follow-up** redactado al colgar, en su voz desde el primer día. **Preparación de cold call:** quién es, por qué llamas y qué decir, sin LinkedIn. **Preparación de llamada de seguimiento:** gancho con sus palabras, por qué llamas y qué decir ante su objeción. **Preparación de reunión:** la reunión sale en Hoy el día que toca, con su brief y lo que falta del playbook. **Tareas** con la fecha exacta que se dijo. **Aviso de no respuesta** a los 10 días. **Ask:** «¿a quién llamo hoy?» con botón de llamar. | Ninguna de estas salidas pide al comercial un dato que Vocify ya tenía. |
| **4. Feedback y coaching** | Tras cada conversación, también las visitas: nota contra el playbook de su empresa, qué hizo bien y qué mejorar, cuando él elige verlo (al momento, diferido o a fin de día). Cada viernes, su semana. Al manager: informe de equipo, adherencia semanal por comercial (orden alfabético), objeciones y competidores con nombre, y Ask con las mismas cifras que el panel. | La nota premia la objeción bien trabajada, no el prospecto fácil (F09). |

### 1.2 El recorrido real (y dónde no podemos fallar)

**Comercial, un martes:**
1. **8:30, abre Vocify** y ve Hoy, con un máximo de 7 tarjetas y cada una con su motivo:
   - «Marina: te pidió que la llamaras hoy tras dudar por el precio»;
   - «Reunión hoy 11:00 · Acme»;
   - «Confirma: reunión del jueves con Pedro → etapa Meeting booked».

   ⚠ Momento crítico: si una tarjeta es falsa o genérica, deja de mirar Hoy.
2. **Antes de marcar** (extensión, dialer o Hoy), ve tres líneas y una etiqueta:
   - si ya habló con él: el gancho con sus palabras, por qué llama y qué decir, más «Pitch hecho · falta cualificar»;
   - si es un cold call: quién es, por qué le llama y cómo abrir según su playbook.

   Se lee en cinco segundos.
3. **Al colgar:** con la autoaprobación activada, el CRM ya está guardado. Si no, revisa una pantalla ya rellena. El «te llamo el jueves» ya es una tarea el jueves. El follow-up está redactado en su estilo.
4. **A los 10 días sin respuesta** al email (si su CRM lo permite), el contacto vuelve a salir en Hoy.
5. **Visita presencial:** manda una nota de voz por WhatsApp al salir y obtiene lo mismo que con una llamada: nota del playbook, compromisos en Hoy y reunión detectada.
6. **Viernes 18:00:** su semana (actividad, adherencia, qué mejorar), sin comparaciones con compañeros.

**Head of sales:** recibe el informe semanal de equipo, ve la página Equipo con el mismo dato y puede preguntar a Ask por el equipo con las mismas cifras que el panel.

### 1.3 Lo que le cuesta al comercial (facilidad de uso)

| Momento | Esfuerzo hoy | Tras el plan |
|---|---|---|
| Capturar una llamada | 0 clics (dialer o HubSpot) | Igual |
| Capturar una visita | Una nota de voz, pero sale sin nota del playbook, sin compromisos en Hoy y sin reunión | Una nota de voz, y sale **con todo** (E1) |
| Actualizar el CRM | Una revisión; 0 clics con autoaprobación | Igual, pero con autoaprobación la etapa y la reunión llegan como **un clic en Hoy** (E7) en lugar de perderse |
| Preparar una llamada de seguimiento | 3 líneas genéricas, solo en la extensión | 3 líneas útiles en la extensión, el dialer y Hoy (E3) |
| Preparar un cold call | «Sin conversación todavía» | Quién es, por qué y cómo abrir (E4) |
| Preparar una reunión | Nada | Tarjeta en Hoy el día de la reunión, con su brief (E5) |
| Tareas | Las escribe Vocify, a veces con otra fecha que la dicha | La fecha exacta que se dijo (E2) |
| Follow-up | Editar hasta que aprende su estilo | Su estilo desde el primer día (E6) |
| Coaching | Llega solo (según su preferencia) | Igual, también por las visitas (E1) |

### 1.4 Cambio de enfoque (decisión del founder, 26 sep): Vocify es el espacio de trabajo del comercial

Hasta ahora la idea era que el comercial casi no entrara en Vocify: todo pasaba por la extensión, el CRM y los emails (`EXPERIENCIA_PRODUCTO.md`: «por encima, un solo gesto»). Con Hoy, las preparaciones, las confirmaciones, los follow-ups y Ask, **el comercial va a pasar tiempo dentro de Vocify e interactuar con él**. Eso cambia el esquema:

- **Vocify tiene una casa para el comercial:** una pantalla principal, sencilla, bonita y ordenada, donde ve y trabaja su día. Incluye:
  - las reuniones de hoy;
  - a quién llamar y por qué;
  - las confirmaciones pendientes;
  - los follow-ups por enviar;
  - las próximas tareas;
  - lo hecho hoy.
- **Desde esa casa se hace todo sin saltar de pantalla:** preparar (brief), llamar (dialer), confirmar, enviar el follow-up y preguntar a Ask.
- **Lo que no cambia:**
  - Menos clics y lo esencial primero.
  - Sin paneles de analítica para el comercial.
  - Peso visual proporcional a la frecuencia de uso.
  - Estados vacíos, de carga y de error diseñados.
  - La referencia de calidad sigue siendo Granola.
- **Las superficies se reparten el trabajo:**
  - la extensión sigue siendo el sitio para preparar una llamada desde el CRM;
  - el desktop captura reuniones (Dani);
  - el dashboard pasa a ser el sitio donde el comercial organiza su día.

Esto se concreta en la entrega **E10** (diseño primero, aprobado por el founder antes de construir) y en que las piezas de UI de E3–E7 se colocan dentro de ese espacio, no repartidas por pantallas sueltas.

---

## 2. Principios de arquitectura (se aplican a todas las entregas)

1. **Un hecho, un productor, muchos consumidores.** Cada hecho se extrae una vez (C04, `intelligence_v2`, con cita exacta) y los consumidores lo leen de ahí. Ningún consumidor vuelve a deducirlo con su propio prompt o heurística.
   - Hoy lo incumplen el brief (lee `objections` y `next_steps` de la extracción CRM antigua, en `api/briefs.py`) y las tareas del CRM (salen de `nextSteps`).
2. **`memos` es la Interaction.** No se crea otra tabla. Toda captura inserta con `insert_memo_row`/`with_author_company` y pasa por `run_post_extraction_hooks`. `interaction_kind` dice el canal: llamada, reunión o visita.
3. **Una sola revisión, y nada pendiente en silencio.** Lo que va al CRM se confirma en la revisión que ya existe. Si la autoaprobación la salta, lo que necesita al comercial le llega a Hoy.
4. **Vocify propone, el comercial confirma lo que tiene consecuencias:** la etapa del deal, la reunión en el CRM y el envío del email. El resto se rellena solo.
5. **Determinista donde se pueda.** Preparación, prioridad, avisos y agregados salen de hechos guardados, sin LLM. Los LLM solo en extracción (C04), follow-up, scoring y Ask, y cada prompt con sus evals.
6. **Flag por empresa en todo lo nuevo** (`is_enabled`), apagado por defecto y encendido primero en Vocify sobre staging.
7. **Sin AI slop y UI proporcional.** Frases cortas con hechos, estados vacíos honestos, ningún panel nuevo si un elemento existente lo absorbe.

---

## 3. Estudio: ¿se cumplen los cuatro objetivos?

### 3.1 Todas las features, qué aportan y a quién

| Feature | Objetivo | Produce | Lo consumen | Estado |
|---|---|---|---|---|
| Captura: dialer, HubSpot calling, extensión, subida | 1 | conversación (`memos`) con transcripción | todo lo demás | Funciona |
| Captura desktop de reuniones (F01) | 1 | conversación `meeting` | todo lo demás | Dani (macOS hecho, Windows pendiente) |
| Captura por WhatsApp (nota de voz) | 1 | conversación | CRM | **Se salta el pipeline común** → E1 |
| Extracción CRM | 2 | campos, nota y `nextSteps` | revisión, CRM | Funciona |
| Inteligencia C04 (`intelligence_v2`) | 1–4 | los seis hechos, con cita | Hoy, reunión, etapa, informes, Equipo | Funciona (flag; encendida en Vocify; evals 16/16) |
| Revisión y aprobación (HubSpot, Pipedrive, Salesforce) | 2 | escritura en el CRM | CRM | Funciona |
| Autoaprobación (interruptor por usuario en Ajustes del CRM) | 2 | escritura sin revisión con contacto o deal claros | CRM | Funciona. **Deja la etapa y la reunión sin confirmar** → E7 |
| Reunión agendada (F14) | 2, 3 | propuesta de reunión con hora | CRM (al aceptar), informes | Funciona (hoy) |
| Etapa confirmada por el comercial | 2 | etapa sugerida en la revisión | CRM | Funciona (flag, hoy) |
| Tareas del CRM | 2, 3 | tarea con fecha | CRM, Hoy | **Salen de `nextSteps`, no de los compromisos** → E2 |
| Hoy (F05) + prioridad (F04) + acciones (F06) | 3 | lista diaria con motivo | comercial | Funciona (hechos de memos y no respuesta, hoy) |
| Contactos sin llamar | 3 | tarjetas de primer contacto | Hoy, Ask | Funciona (arreglado hoy) |
| Brief previo (F03) | 3 | 3 líneas | extensión, dashboard, desktop | **Genérico y sin cold call** → E3, E4 |
| Preparación de reunión | 3 | — | — | **No existe** → E5 |
| Follow-up (F02) | 3 | borrador de email | comercial | Funciona. **Sin evals ni estilo inicial** → E6 |
| Aviso de no respuesta | 3 | tarjeta a los 10 días | Hoy | Funciona (flag; HubSpot necesita el permiso pendiente) |
| Ask (F07) | 3, 4 | respuestas con datos y botón de llamar | comercial, manager | Funciona (flags, hoy) |
| Playbooks (F08) | 4 | pasos por tipo de venta | scoring, brief, live | Funciona |
| Nota contra playbook (F09) | 4 | nota y pasos cumplidos | brief posterior, informes, Equipo | Funciona (no llega a las visitas → E1) |
| Brief posterior (F11) | 4 | qué hizo bien y qué mejorar | comercial | Funciona (no llega a las visitas → E1) |
| Informes (F13): diario, semanal, de equipo, campana | 4 | resumen por periodo | comercial, manager | Funciona (flags; el email diario sigue apagado) |
| Equipo (F15) + adherencia semanal | 4 | agregados sin ranking | manager, Ask | **Casi** → E8 |
| Asistencia en vivo (F12) | 4 | checklist y tarjeta de objeción | comercial | Dani (desktop) |

### 3.2 Cómo encajan: seis hechos y quién los usa

| Hecho (productor) | CRM | Hoy | Preparación | Follow-up | Coaching e informes | Qué cambia el plan |
|---|---|---|---|---|---|---|
| **Dolor confirmado** + cita (C04) | nota | prioridad 1 (F04) | **gancho** | contexto | informe | E3 |
| **Objeción** tipada + resolución + cita (C04) | nota | tarjeta si sigue abierta | «qué decir» + respuesta del playbook | — | Equipo, informe, nota F09 | E3 (hoy el brief lee la objeción antigua) |
| **Compromiso** + fecha resuelta (C04) | **tarea con esa fecha** | tarjeta el día que toca | «por qué llamas» | «quedamos en…» | informe | E2 y E3 |
| **Reunión** acordada + hora (C04) | actividad (al aceptar) | **tarjeta el día de la reunión** y confirmación si hubo autoaprobación | brief de reunión | confirma la reunión | reuniones agendadas | E5 y E7 |
| **En qué punto está** (pasos del playbook, F09) | sugerencia de etapa | confirmación de etapa si hubo autoaprobación | **etiqueta** y «falta del playbook» | — | adherencia | E3, E5 y E7 |
| **Competidor** (C04) | nota | — | «qué decir» si no hay objeción | — | **nombres en Equipo e informe** | E3 y E8 |

Y para todos: **la visita por WhatsApp tiene que producir los seis hechos igual que una llamada** (E1).

Regla: si una entrega necesita un hecho nuevo, se añade a C04 con evals. Nunca se deduce aparte.

### 3.3 Por objetivo: qué falla hoy, qué arregla el plan y qué queda fuera

| Objetivo | Falla hoy | Lo arregla | Queda fuera (honesto) | Cómo sabremos que funciona |
|---|---|---|---|---|
| 1. Captura | Las visitas no generan hechos; no se sabe el canal | E1 | Reuniones de Windows (Dani), bot de reuniones, Aircall/Ringover (ideas) | % de conversaciones con inteligencia, por canal |
| 2. CRM | Tareas con otra fecha; etapa y reunión perdidas con autoaprobación | E2, E7 | — | % de conversaciones escritas en el CRM; confirmaciones pendientes con más de 2 días |
| 3. Admin | Brief genérico, sin cold call ni reunión; follow-up sin estilo ni evals | E3, E4, E5, E6 | Envío de email desde Vocify, calendario (ideas) | % de borradores que se abren; % de edición media; tarjetas de Hoy resueltas |
| 4. Coaching | Visitas sin nota; Equipo sin cerrar | E1, E8 | Coaching en vivo (Dani), mejores llamadas (V2) | Adherencia semanal; briefs posteriores vistos |

Las consultas de «cómo sabremos que funciona» se entregan en E9 para ejecutarlas sobre staging.

### 3.4 Decisiones de las reuniones y cómo las respeta el plan

| Decisión (reunión) | Dónde se cumple |
|---|---|
| Hoy por temperatura: dolor sin demo primero, contactos sin llamar después | F04/F05 (hecho); E2 hace que los compromisos coincidan |
| Tareas inteligentes con contexto y botón «Llamar ahora» | Hoy + Ask (hecho); E3 pone el brief en la tarjeta |
| Brief previo: gancho, 2–3 puntos (por qué llamas, qué decir, quién es), en qué punto está, corto, sin LinkedIn | E3 (seguimiento) y E4 (cold call) |
| Follow-up automático, aprobado por el comercial, en su estilo | F02 (hecho); E6 |
| «Si no responde en X días, rellamar» | Aviso de no respuesta (hecho, flag) |
| Reunión solo con día y hora acordados, usando la fecha confirmada | C04 + F14 (hecho) |
| La etapa la confirma el comercial (decisión de hoy) | Revisión (hecho); E7 para la autoaprobación |
| Ask: el comercial ve lo suyo, el manager ve el equipo | F07 (hecho); E8, misma cifra que el panel |
| Playbook por empresa; la nota distingue prospecto fácil de objeción real; feedback en segundo plano y configurable | F08/F09/F11 (hecho); E1 lo lleva a las visitas |
| Informes diario y semanal para comercial y manager; adherencia como métrica principal; pocos botones | F13/F15 (hecho, flags); E1 cuenta visitas |
| Vistas de equipo sin ranking | E8 mantiene el orden alfabético |
| Gmail directo solo si el ICP lo exige; sincronización del CRM | Se respeta (el análisis está en el documento de ideas) |
| Coaching en vivo solo en reuniones; mejores llamadas V2; calendario más adelante; pricing con Dani | Fuera de este plan |

---

## 4. Entregas

Formato común de cada entrega:
- addendum al spec antes del código (el spec manda);
- tests primero;
- flag por empresa apagado;
- evals si toca un prompt;
- sin UI nueva salvo la indicada con su peso visual;
- un commit por entrega.

Cada entrega dice qué resulta: qué es verdad cuando termina.

### E1 · Un solo pipeline para llamadas, reuniones y visitas (objetivos 1 y 4)
- **Por qué:** la visita presencial es uno de los tres canales de captura. Hoy `whatsapp/processor.py` extrae en línea (`extract_memo`, ~L1790) y no llama a `run_post_extraction_hooks`. Una visita no tiene inteligencia, nota del playbook, brief posterior ni reunión detectada.
- **Qué:**
  - Tras la extracción, WhatsApp llama a `run_post_extraction_hooks` igual que `api/memos.py` (~L302), en segundo plano para no retrasar la respuesta.
  - `interaction_kind` se estampa en todas las capturas, en `services/captures.py` y en los puntos de inserción: dialer y HubSpot → `call`, WhatsApp → `visit` (el valor que ya admite la base de datos), desktop de reunión → `meeting` (ya existe).
  - Los informes y Equipo cuentan por canal: «llamadas, reuniones y visitas».
- **Archivos:** `services/whatsapp/processor.py`, `services/captures.py`, `services/hubspot/call_processor.py`, `services/reporting/*` (el recuento).
- **UI:** ninguna.
- **Flag:** ninguno nuevo. Repara el pipeline común, y la inteligencia sigue detrás de `INTELLIGENCE_EXTRACT_ENABLED`.
- **Spec:** addendum en `03-f0-f0.1-inteligencia-y-jobs.md` (C05) y una línea en `ESTRUCTURA_INTELIGENTE.md`.
- **Tests:**
  - WhatsApp dispara los hooks una vez, y reintentar no los duplica.
  - Un fallo en los hooks no rompe la respuesta de WhatsApp.
  - `interaction_kind` correcto por origen.
  - Nota sin contacto encontrado: los hooks corren y la propuesta de reunión sigue la regla vigente de F14 (con acuerdo y evidencia, sí; sin acuerdo, no).
  - Los informes cuentan visitas.
- **Resulta:** una visita por WhatsApp produce lo mismo que una llamada y aparece en Hoy, en el coaching y en los informes.

### E2 · Un compromiso, un pendiente (objetivos 2 y 3)
- **Por qué:** «te llamo el jueves» tiene que ser lo mismo en el CRM, en Hoy, en la preparación y en el follow-up. Hoy la tarea sale de `nextSteps` y Hoy sale de los compromisos de C04.
- **Qué:**
  - Con C04 vigente, las filas de tareas de la revisión (`next_step_task_i`) salen de `commitments`: texto y `due_at`.
    - Fecha con hora: esa hora.
    - Solo día: 9:00 hora local.
    - Sin día: sin fecha.
  - Sin C04, se sigue usando `nextSteps`.
  - En Hoy, un compromiso ya escrito como tarea sale una sola vez, como tarjeta del compromiso marcada «en el CRM».
- **Archivos:** `hubspot/preview.py`, `hubspot/tasks.py`, `hubspot/sync.py`, `pipedrive/preview.py` (+ su sync), `salesforce/preview.py`, `hoy/signals.py`, `hoy/materialize.py`.
- **UI:** las mismas filas de tareas de la revisión. Solo cambia de dónde salen.
- **Flag:** `COMMITMENT_TASKS_ENABLED`.
- **Spec:** addendum en `07-f05-hoy.md` y `08-f06-acciones-y-cola.md`.
- **Antes de empezar:** solo 16 de los 150 memos del backfill tienen compromisos. Reviso unos 20 memos con `nextSteps` pero sin compromisos. Si C04 se queda corto, añado casos a los evals C04 y ajusto el prompt, con evals 3× en verde.
- **Tests:**
  - Fecha con hora, solo día y sin fecha.
  - Promesa del comercial y petición del prospecto.
  - Sin C04, se usa `nextSteps`.
  - No se duplica en Hoy.
  - El comercial quita una tarea en la revisión y no se crea.
  - HubSpot, Pipedrive y Salesforce.
- **Resulta:** la tarea del CRM, la tarjeta de Hoy y la línea «por qué llamas» dicen lo mismo, con la misma fecha.

### E3 · Brief previo v2 para llamadas de seguimiento (objetivo 3)
- **Por qué:** la reunión pidió gancho, por qué llama, qué decir y en qué punto está. Hoy el brief enseña un resumen genérico y lee la objeción antigua, no la de C04. Tampoco enseña el dolor (que ya recibe como `pain_confirmed`), el pitch ni el competidor.
- **Se mantiene del 22 sep:**
  - Como mucho tres líneas.
  - Solo hechos, con fuente y sin LLM.
  - Sin LinkedIn.
  - El mismo texto en todas las superficies.
  - Los estados vacíos y parciales.
- **Líneas (deterministas, desde C04):**
  1. **Gancho:** la última conversación con fecha. Si hubo dolor confirmado, con sus palabras: «12 sep: “se nos quedan leads sin llamar”».
  2. **Por qué llamas:** el primer hecho que exista entre estos:
     - el compromiso vencido o de hoy;
     - el email sin respuesta (si `HOY_NO_REPLY_ENABLED`);
     - la tarea abierta del CRM.
  3. **Qué decir:** la objeción abierta con la respuesta del playbook. Si no hay, el competidor mencionado («Usa Ringover»).
  - **Etiqueta:** «Pitch hecho · falta cualificar», con los pasos cumplidos y pendientes en la última nota F09. Solo si hay playbook y nota.
- **Dónde:**
  - Extensión (principal, como hoy).
  - **Dialer del dashboard**, encima del botón de llamar, en texto pequeño. Reutiliza `ContactBrief`.
  - **Tarjeta de Hoy desplegada.**
  - Desktop, que lee el mismo API.
- **Archivos:** `api/briefs.py` (`_from_memos` pasa a leer `extraction.intelligence`), `services/briefs/preparation.py`, `src/components/dashboard/memos/ContactBrief.tsx`, `DashboardDialer.tsx`, la tarjeta de Hoy del dashboard, `chrome-extension/shared/ui/brief.js`.
- **Flag:** `BRIEF_V2_ENABLED`.
- **Spec:** «Corrección 26 sep» en `09-f03-preparacion.md` y en `00-decisiones.md`.
- **Tests:**
  - Cada regla y su orden.
  - Sin hecho no hay línea.
  - Lectura parcial.
  - Sin playbook no hay etiqueta.
  - Objeción resuelta no sale.
  - El mismo texto para todas las superficies.
- **Resulta:** antes de llamar a alguien con quien ya habló, el comercial sabe con qué abrir, por qué llama y qué responder, en cinco segundos y en cualquier superficie.

### E4 · Preparación de cold call (objetivo 3)
- **Por qué:** la reunión pidió «quién es» como uno de los tres puntos, sin LinkedIn. Hoy un contacto sin conversación sale como «Sin conversación todavía», justo en los contactos sin llamar que Hoy pone en segundo lugar.
- **Líneas (deterministas, desde el CRM y el playbook):**
  1. **Quién es:** cargo · empresa · origen y fecha de alta del CRM. Por ejemplo: «Directora comercial en Acme · lead de formulario web, 3 sep».
  2. **Por qué llamas:** la tarea abierta del CRM o el motivo de Hoy. Por ejemplo: «Nuevo, sin llamar desde el 3 sep».
  3. **Cómo abrir:** la apertura del playbook de su tipo de venta (el paso de apertura con su frase de referencia). Solo si existe.
  - Sin datos del CRM: se queda la frase actual «Sin conversación todavía».
- **Archivos:** `services/briefs/preparation.py`, `api/briefs.py` (lectura de propiedades reutilizando la capa de lectura de CRM de Ask: `crm_copilot` para HubSpot y `pipedrive_reads.py`), `services/playbooks/store.py`.
- **UI:** las mismas superficies que E3, sin elementos nuevos.
- **Flag:** `BRIEF_V2_ENABLED` (misma feature).
- **Spec:** en la misma «Corrección 26 sep» de `09-f03-preparacion.md`.
- **Tests:**
  - Contacto con todos los datos, con parte y sin ninguno.
  - Error de CRM → estado parcial honesto.
  - Sin playbook → sin línea de apertura.
  - HubSpot y Pipedrive.
- **Resulta:** el primer contacto también tiene preparación, sin inventar nada ni salir de Vocify.

### E5 · Preparación de reunión sin calendario (objetivo 3)
- **Por qué:** tu objetivo 3 incluye preparar las reuniones. El brief desde el calendario se dejó para más adelante, pero Vocify ya conoce las reuniones que se agendaron en sus conversaciones (F14, con hora aceptada por el comercial).
- **Qué:**
  - Hoy incluye «Reunión hoy 11:00 · Marina (Acme)» para las propuestas F14 aceptadas con `starts_at` hoy, en su zona horaria.
  - Al desplegarla: el brief de E3 más «Falta del playbook: decisor, presupuesto», con los pasos que la última nota F09 marca como no cumplidos.
- **Archivos:** `hoy/signals.py`, `hoy/materialize.py`, `services/meetings/*` (lectura), la tarjeta de Hoy (dashboard y extensión).
- **UI:** la tarjeta de Hoy que ya existe, con otro motivo.
- **Flag:** `HOY_MEETINGS_ENABLED`.
- **Spec:** addendum en `07-f05-hoy.md` y `12-f14-meeting-booked.md`.
- **Edge cases:**
  - Reunión solo con día: tarjeta sin hora.
  - Propuesta omitida o no aceptada: no sale.
  - Movida en el CRM: no lo sabemos, así que la tarjeta dice «acordada el {fecha}».
  - Reuniones no captadas por Vocify: no salen (honesto hasta tener calendario).
- **Resulta:** el día de una reunión que salió de una llamada, el comercial la ve en Hoy con lo que necesita saber y lo que le falta averiguar.

### E6 · Follow-up: evals, flag por empresa y estilo desde el primer día (objetivo 3)
- **Por qué:** es el primer «wow» del comercial. Hoy aprende su estilo solo cuando edita mucho un borrador, y el prompt no tiene evals (regla 3).
- **Qué:**
  - Evals en `backend/evals/F02/`, que se corren 3 veces:
    - no inventa precios, fechas, adjuntos ni nombres;
    - idioma y español de España;
    - 60–120 palabras;
    - asunto específico;
    - tú o usted según los ejemplos;
    - un paso vago sigue vago;
    - sin frases de relleno.
  - `FOLLOWUP_ENABLED` pasa a comprobarse por empresa con `is_enabled`, manteniendo `True` por defecto.
  - **Estilo desde el primer día:** en Ajustes, en la sección existente junto a las preferencias del brief (`BriefHighlightSettings.tsx`), un campo plegado «Tu forma de escribir» para pegar hasta 3 emails. Guarda en `user_profiles.writing_samples`, que ya alimenta `voice_samples` (`services/followup.py`). Las ediciones siguen añadiendo ejemplos.
- **UI:** un campo plegado, de peso secundario, en una sección que ya existe. Se usa una vez.
- **Archivos:** `backend/evals/F02/`, `services/followup.py`, `api/followup.py`, `src/components/dashboard/settings/BriefHighlightSettings.tsx` (o su sección hermana), la API de perfil.
- **Spec:** addendum en `02-f02-followup.md`.
- **Tests:**
  - Los ejemplos pegados llegan al prompt.
  - Máximo 3 ejemplos y límite de longitud.
  - Vaciar el campo quita los ejemplos.
  - Las ediciones no borran los pegados.
  - Flag apagado por empresa → sin borrador.
- **Resulta:** el primer follow-up ya suena al comercial, y el prompt tiene evals que avisan si se rompe.

### E7 · Nada pendiente en silencio tras la autoaprobación (objetivo 2)
- **Por qué:** la autoaprobación (interruptor «aceptar automáticamente» en Ajustes del CRM, `auto_sync_hubspot_calls`) ya guarda en el CRM cualquier conversación con contacto o deal claros. Es el «más o menos autónomo» que pides. Pero con la decisión de hoy, una conversación autoaprobada no escribe la etapa, y su propuesta de reunión solo se ve si el comercial abre la ficha. Las dos se quedan sin confirmar sin que nadie se entere.
- **Qué:** tras una autoaprobación, si hay una etapa sugerida distinta de la actual o una propuesta de reunión sin aceptar, Hoy enseña una tarjeta de confirmación de un clic:
  - «Confirma: reunión jue 11:00 con Marina · etapa → Meeting booked» con [Confirmar] y [Revisar].
  - Confirmar escribe exactamente lo que habría escrito la revisión (mismas funciones, mismo registro).
  - Revisar abre la ficha.
- **Archivos:** `hubspot/auto_sync.py`, `services/deal_stage_confirm.py`, `services/meetings/accept.py`, `hoy/signals.py`, las acciones de Hoy (F06) y la tarjeta de Hoy.
- **UI:** la tarjeta de Hoy existente con dos acciones. Sin pantallas nuevas.
- **Flag:** `HOY_CONFIRMATIONS_ENABLED`.
- **Spec:** addendum en `12-f14-meeting-booked.md` y `08-f06-acciones-y-cola.md`.
- **Tests:**
  - Autoaprobación con etapa distinta → tarjeta.
  - Etapa igual → sin tarjeta.
  - Reunión pendiente → tarjeta.
  - Confirmar escribe una vez (idempotente).
  - Deshacer en el plazo de F06.
  - Sin autoaprobación → nada nuevo (la revisión ya lo cubre).
- **Resulta:** el CRM se actualiza solo en lo seguro, y lo que tiene consecuencias le llega al comercial en un clic, nunca se pierde.

### E8 · Cierre de Equipo (F15) (objetivo 4)
- **Por qué:** F15 quedó bloqueado por dos cosas: Ask no daba las cifras del panel y faltaba verificar la pantalla. La primera ya está en código: `get_team_metrics` usa `load_team_adherence_inputs` + `team_adherence`, igual que `GET /team/adherence`. Falta demostrarlo y cerrar el resto.
- **Qué:**
  - Un test de paridad: para los mismos filtros, Ask y el panel devuelven el mismo agregado.
  - **Competidores con nombre** en la tarjeta de objeciones de Equipo y en el informe semanal de equipo, desde C04 `competitor_mentions`, con su número.
  - Arreglar el test `src/lib/team-insights.test.ts` que falla (ya fallaba antes de hoy).
  - Verificación de `/dashboard/insights` en el navegador sobre staging con tu sesión: filtros → bloques → tablas. Reticle no está disponible en esta sesión.
  - Actualizar `docs/superpowers/deliveries/F15/report.md`.
- **Archivos:** `team_insights/objections.py`, `reporting/*` (informe de equipo), `src/features/team-insights/*`, `tests/team_insights/`.
- **Flag:** `TEAM_COMPETITORS_ENABLED` para los nombres. La paridad no lleva flag.
- **Spec:** addendum en `16-f15-equipo.md`.
- **Tests:** paridad; sin nombres, vacío honesto; muestra pequeña; el miembro sin permiso no ve cifras.
- **Resulta:** F15 pasa de BLOCKED a cerrado, y el manager ve qué competidores salen y obtiene la misma cifra en Ask y en el panel.

### E9 · Prueba de armonía, salud y activación en staging
- **Test de integración** «una conversación, todas las salidas», en `backend/tests/e2e/`:
  - Una conversación de ejemplo con objeción de precio, dolor confirmado, «llámame el jueves» y «quedamos el jueves a las 11» recorre extracción (C04 simulado con su fixture), hooks, revisión y autoaprobación, Hoy, preparación, follow-up, nota F09, brief posterior, informe y Equipo.
  - Se ejecuta **por llamada y por WhatsApp**.
  - Comprueba que todas las salidas enseñan los mismos hechos: misma tarea y fecha, misma reunión, misma objeción y respuesta, mismo gancho, misma nota, y la confirmación en Hoy cuando hubo autoaprobación.
- **Consultas de salud** (`docs/superpowers/plans/2026-09-26-salud-vocify.sql`), una por objetivo:
  - % de conversaciones con inteligencia, por canal;
  - % escritas en el CRM y confirmaciones pendientes con más de 2 días;
  - borradores abiertos y edición media;
  - adherencia semanal y briefs posteriores vistos.
- **Activación en staging para Vocify:** el SQL de los flags nuevos y los ya hechos, para que los ejecutes tú. El email diario sigue apagado hasta que lo revises.
- **Recorrido manual** en dashboard, extensión y WhatsApp con una llamada y una nota de voz reales, siguiendo la sección 1.2.
- **Actualización del estado** en `MASTER_PLAN.md` y `PENDIENTES.md`.
- **Resulta:** una prueba automática que falla si una pieza deja de enseñar lo mismo que las demás, y una forma de medir cada objetivo con datos reales.

### E10 · El espacio de trabajo del comercial (objetivo 3 y adopción)
- **Por qué:** el comercial va a vivir en Vocify (sección 1.4). Hoy el dashboard está pensado para entrar poco: pantallas sueltas (Hoy, memos, dialer, Ask, Ajustes) sin una casa que ordene el día.
- **Fase de diseño (antes de construir, la aprueba el founder):**
  - análisis del dashboard, la extensión y el desktop actuales (rutas, navegación, componentes, tokens y copy);
  - diseño en `docs/features/F16-espacio-comercial/` (`spec.md` + `design.md`);
  - el recorrido del día con sus momentos críticos;
  - la estructura de la casa del comercial (vista de manager aparte);
  - dónde va cada pieza de E3–E7, con su peso visual;
  - navegación simplificada, estados vacío, carga y error, teclado y transiciones;
  - qué componentes se reutilizan y qué archivos se tocan;
  - el cambio en `EXPERIENCIA_PRODUCTO.md`.
- **Fase de construcción:**
  - la casa del comercial en el dashboard (Hoy como pantalla principal, con sus secciones);
  - el panel de contacto con brief, historial y follow-up sin salir de la casa;
  - el dialer integrado;
  - la navegación ajustada.

  Todo detrás de `REP_WORKSPACE_ENABLED`, y la vista actual se queda para quien no tenga el flag.
- **Verificación:** navegador sobre staging con tu sesión, recorriendo el día del comercial (sección 1.2).
- **Resulta:** el comercial abre Vocify y en una pantalla ve y trabaja su día, bonita, ordenada y sin buscar nada.

---

## 5. Orden de ejecución

Máximo dos entregas a la vez (regla del plan maestro), elegidas para no tocar los mismos archivos. Cada una va a un subagente con su addendum. Yo reviso, paso la suite completa y los evals, commiteo por entrega y subo a `staging` al final de cada ola. Todo va apagado por flag y nada llega a `main`.

| Ola | Entregas | Por qué juntas |
|---|---|---|
| 1 | E1 (pipeline) + E2 (compromisos), y en paralelo el **diseño de E10** (sin código) | Los cimientos son solo backend; el diseño no toca código. |
| — | **Aprobación del diseño de E10 por el founder** | Regla del repo: una pantalla nueva o un cambio de flujo se propone antes de construirse. |
| 2 | E10 (construcción de la casa del comercial) + E6 (follow-up) | Las piezas de UI siguientes se colocan dentro de la casa. |
| 3 | E3 (brief v2) + E7 (confirmaciones) | Se enchufan a la casa y al panel de contacto. |
| 4 | E4 (cold call) + E5 (reuniones en Hoy) | E4 amplía el brief; E5 lo reutiliza. |
| 5 | E8 (Equipo) + E9 (armonía, salud y activación) | Cierre sobre todo lo anterior. |

Las entregas en paralelo trabajan en ramas y carpetas separadas (`.worktrees/l2-eN`, rama `l2/eN`) y se integran en `feat/lista-2`, creada desde `origin/staging`. La rama `staging` local no se sube, porque lleva el commit del permiso de HubSpot pendiente de `hs project upload`. Lo integrado se sube a `staging` con `git push origin feat/lista-2:staging`.

**Gates de cada entrega:**
- addendum escrito antes del código;
- tests del spec en verde;
- suite backend completa en verde;
- `tsc` sin errores nuevos (39 hoy);
- evals 3× si toca un prompt;
- revisión mía del diff;
- las pantallas que cambian, vistas en el navegador sobre staging.

---

## 6. Riesgos

- **Calidad de C04:** casi todo depende de ella. Los evals están al 100 %, pero con 16 casos; se añaden casos reales cuando fallen (ver E2).
- **Hoy con ruido:** entran compromisos, reuniones y confirmaciones. Se mantiene el límite de 7 tarjetas (`hoy/signals.py`, `DEFAULT_LIMIT`) y el orden de F04. Si hace falta, las confirmaciones van agrupadas en una sola tarjeta.
- **Cold call:** depende de lo que el cliente tenga rellenado en su CRM. Con pocos datos, la preparación es corta; nunca se rellena con suposiciones.
- **Autoaprobación:** hoy la usan quienes la activan. E7 no la activa para nadie.
- **Verificación de UI:** Reticle no está disponible en esta sesión. Las pantallas se verifican en el navegador sobre staging con tu sesión.
