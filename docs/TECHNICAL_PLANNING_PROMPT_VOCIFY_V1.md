# Prompt de Planning Técnico — Vocify V1 (Dashboard + Backend)

> **Cómo usar este documento:** esto NO es el plan técnico. Es el prompt/metodología que se le da a un agente (Plan agent, una sesión nueva de Claude Code, u otro) para que **él** produzca el plan técnico correcto, feature por feature, spec por spec. Pégalo completo como instrucción inicial de esa sesión. Todo lo que sigue, a partir de la sección "ROL", está escrito en segunda persona dirigido a ese agente.

---

## 0. Fuentes de verdad y su jerarquía

Estos son los documentos con autoridad sobre lo que se construye. En caso de conflicto entre ellos, se resuelve con esta jerarquía:

1. **El código real del repo** (lo que existe hoy) — gana siempre sobre lo que cualquier documento *diga* que existe. Si un documento dice "ya se hace" y el código no lo confirma, el código manda.
2. **Los pares plan+spec de `docs/superpowers/` que ya tradujeron parte de estas decisiones de producto a diseño de código, verificados contra el repo real** (tests corridos, línea exacta, commit citado) — en concreto, para esta build queue:
   - [`docs/superpowers/specs/2026-09-21-copilot-spine-design.md`](../superpowers/specs/2026-09-21-copilot-spine-design.md) + [`docs/superpowers/plans/2026-09-21-copilot-spine-foundation-and-followup.md`](../superpowers/plans/2026-09-21-copilot-spine-foundation-and-followup.md)
   - [`docs/superpowers/specs/2026-08-11-realtime-objection-copilot-design.md`](../superpowers/specs/2026-08-11-realtime-objection-copilot-design.md) + [`docs/superpowers/plans/2026-08-11-realtime-objection-copilot.md`](../superpowers/plans/2026-08-11-realtime-objection-copilot.md)

   Para el **cómo** (arquitectura, secuencia, qué reutiliza qué) de cualquier feature que estos documentos ya cubran, **ganan sobre el juicio de §5.1 de este prompt** — §5.1 fue razonado sin verificar contra código corrido; estos sí. Donde §5.1 contradiga uno de estos documentos, la corrección ya está aplicada en §5.1 (ver notas "Corregido por spine spec" inline); si encuentras otra, corrígela igual y dilo explícitamente, no la seas leal a mi versión anterior.
3. **[`docs/PRODUCT_PLANNING_ANALYSIS_2026-09-21.md`](./PRODUCT_PLANNING_ANALYSIS_2026-09-21.md)** — el análisis estructurado y anotado de la sesión de planning del 21 sep. Es la fuente de decisiones de producto (el **qué**, no el cómo). Dentro de este documento, **una nota específica de sección (p. ej. una anotación en mayúsculas dentro de §8) prevalece sobre un resumen general (p. ej. la lista de §9 "Roadmap")** si ambas entran en conflicto — el resumen se escribió antes y puede haber quedado desactualizado por una anotación posterior más específica.
4. **[`product_planing.md`](../product_planing.md)** — la transcripción cruda. Solo se consulta si el análisis estructurado (fuente 3) no cubre el punto o si hace falta el contexto/razonamiento textual exacto detrás de una decisión.

Adicionalmente, y por encima de mi propio §5.1 en lo que toque UX/modelo de datos: el propio spec de spine (fuente 2) cita `docs/features/PLAN_INTEGRACION.md`, `docs/EXPERIENCIA_PRODUCTO.md`, `docs/features/ESTRUCTURA_INTELIGENTE.md` y `docs/features/MASTER_PLAN.md` como los contratos ya aprobados de UX y modelo de datos — los cuatro existen en el repo. No los he leído en profundidad todavía; ábrelos antes de especificar cualquier feature de UI o de datos que puedan cubrir, en vez de asumir que §5.1 ya tiene la última palabra.

**Conflicto real detectado que debes resolver así, como ejemplo de aplicación de esta jerarquía:** §8 del análisis marca Slack/Teams como **"NO HACER"** dos veces explícitamente, pero §9 (Roadmap V1) todavía lista "Notificaciones Slack/Teams para equipo" como parte del V1. Por la regla anterior, **prevalece §8: Slack/Teams no se construye.** Aplica este mismo criterio de resolución a cualquier otra discrepancia que encuentres entre una sección de detalle y una sección de resumen — repórtala explícitamente en tu output, no la resuelvas en silencio.

---

## 1. ROL

Eres el arquitecto/planner técnico encargado de convertir las decisiones de producto ya tomadas (fuentes §0) en un **spec técnico ejecutable**, cubriendo tanto el dashboard (frontend) como el backend, para el monorepo `getvocify` (Dani Zal, founder/lead dev; stack Python/FastAPI + React/TypeScript; equipo 2-5 devs, workflow PR-based).

No eres tú quien decide **qué** se construye — eso ya está decidido en el documento de análisis. El **cómo** — con qué piezas existentes se conecta cada feature, qué es reutilización y qué es pieza nueva, en qué orden real se construye según dependencia técnica — **ya está resuelto en §5.1 de este documento**, con juicio de arquitectura ya aplicado sobre el código auditado. Tu trabajo no es re-derivar esa arquitectura desde cero: es tomar cada veredicto de §5.1 y convertirlo en el spec completo y detallado (migraciones exactas, endpoints, componentes) siguiendo el formato del Paso 4 de la metodología (§3). Si al abrir un archivo real encuentras que el código no coincide con lo que asume un veredicto de §5.1, el código manda (regla de §0) — corrige el veredicto y dilo explícitamente, no lo sigas a ciegas ni lo ignores en silencio.

---

## 2. Reglas no negociables

1. **No inventes decisiones de producto.** Si el documento de análisis no resolvió algo (ver §7 de este prompt, "cosas explícitamente sin resolver"), no decidas por tu cuenta cuál es el comportamiento correcto — repórtalo como pregunta abierta con las opciones que ves, y sigue con el resto del plan. No bloquees todo el planning por un punto sin resolver.
2. **No diseñes nada sin antes auditar qué ya existe.** Antes de proponer un servicio, endpoint, tabla o componente nuevo para una feature, primero confirma si ya existe algo que cubra total o parcialmente esa necesidad (ver el mapa de sistema en §4 de este prompt — es tu punto de partida obligatorio, no una sugerencia). Si extiendes algo existente, dilo explícitamente y explica qué cambia. Si construyes algo nuevo, justifica por qué lo existente no alcanza.
3. **Cada pieza de tu plan debe citar su origen.** Toda decisión de spec debe poder trazarse a una sección concreta del documento de análisis (`§N.M`) o a un archivo concreto del repo (`path/al/archivo.py:linea`). Si no puedes citar el origen, no lo incluyas.
4. **Una feature a la vez, hasta el final, antes de pasar a la siguiente.** Esto es una decisión explícita del propio Dani sobre cómo quiere que se ejecute este plan (§1.7 y §11 del análisis): "que no me meta 20 features al tirón y las haga mal, sino que vaya una por una". Tu plan de salida debe estar secuenciado, no ser una lista plana de features en paralelo.
5. **Define "hecho" antes de pasar a la siguiente feature.** Cada feature de tu plan debe tener criterio de aceptación explícito (qué se puede verificar en el dashboard o en el backend para decir que esta feature está terminada) antes de que se autorice pasar a la siguiente.
6. **Respeta los guardrails de alcance** listados en §6 de este prompt — son decisiones ya tomadas y cerradas en la sesión de planning, no puntos a reabrir.
7. **Escribe para que se entienda, no para impresionar.** Cada paso de cada spec debe poder leerse en lenguaje natural y claro, sin jerga innecesaria ni siglas sin explicar la primera vez que aparecen. Alguien que conoce el producto pero no lee código todos los días (Dani, leyendo esto para revisarlo punto por punto antes de lanzar la ejecución) tiene que poder seguir el hilo de cada feature: qué hace, por qué, y cómo se sabe que quedó bien hecha — sin tener que abrir el repo para entender la frase. Esto no es un adorno de estilo: es un requisito de entrega, igual que el formato del Paso 4.

---

## 3. Metodología obligatoria

Aplica este proceso a **cada feature** del build queue (§5), en este orden, sin saltarte pasos. **Para las 15 features de este build queue, los Pasos 2 y 3 ya están resueltos en §5.1 — úsalos como punto de partida y detállalos, no los repitas desde cero.** Solo vuelve a ejecutar el Paso 2/3 completos desde cero si (a) encuentras una feature que §5.1 no cubre, o (b) el código real contradice lo que §5.1 asume.

### Paso 1 — First principles (por qué existe esta feature)
Antes de tocar código, resume en 2-3 frases: ¿qué carga/problema elimina esta feature?, ¿por qué el equipo decidió que es prioritaria (o no)?, ¿qué pasa si no se construye? Usa el framing y las citas ya documentadas en la sección correspondiente del análisis — no reformules el "por qué" desde cero.

### Paso 2 — Auditoría de reutilización (qué existe ya)
Usa el mapa de sistema (§4 de este prompt) y el veredicto ya dado en §5.1.4 como punto de partida. Para cada feature, confirma contra el código real:
- Qué módulo/servicio/modelo/componente existente cubre parte de esto hoy (§5.1.4 ya lo identifica — verifícalo, no lo repitas de memoria).
- Qué patrón ya establecido en el repo debe replicarse (p. ej.: si es un nuevo tipo de clasificación cerrada, usa `JevClient` — no construyas un clasificador nuevo desde cero; si es una nueva fuente de CRM, implementa el `protocol` en `services/crm_providers/` — no bifurques lógica por `if crm == "hubspot"` fuera de esa capa).
- Qué gap real queda, que sí requiere código nuevo — §5.1.4 lo marca como "Nuevo real" por feature; confírmalo o corrígelo tras abrir el código.

### Paso 3 — Diseño SOLID de la pieza nueva
§5.1.4 ya identifica, por feature, qué principio SOLID es el más relevante y por qué. Usa eso como punto de partida y complétalo con el resto de principios que apliquen al detallar la pieza nueva.
Al proponer cualquier servicio, clase o módulo backend nuevo, o componente/hook frontend nuevo, verifica explícitamente contra estos cinco principios y dilo en el spec (no como checklist genérico, sino aplicado a esta pieza concreta):

- **S — Single Responsibility:** ¿este servicio/componente hace una sola cosa? Sigue el patrón ya existente en `backend/app/services/<dominio>/` (un subpaquete por dominio: `copilot/`, `crm_copilot/`, `crm_providers/`, `llm/`) en vez de amontonar lógica en un servicio genérico.
- **O — Open/Closed:** si esta feature necesita comportamiento distinto por CRM o por tipo de interacción (cold call / meeting / discovery / cierre), ¿se extiende vía una interfaz ya abierta a extensión (`services/crm_providers/protocols.py`, `services/llm/providers/`, playbooks por tipología en §4.2) en vez de añadir condicionales nuevos en código compartido?
- **L — Liskov Substitution:** si implementas un nuevo provider (CRM, LLM, canal de notificación), ¿es intercambiable con los existentes sin romper al que lo consume? (mismo contrato que `HubSpotProvider`/`PipedriveProvider`/`SalesforceProvider` en `services/crm_providers/`).
- **I — Interface Segregation:** ¿el contrato que expones (tool, endpoint, protocolo) es tan chico como haga falta para ese consumidor, en vez de una interfaz gigante compartida? Mira cómo `crm_copilot/tools.py` expone tools discretas y `skills/*.md` se cargan bajo demanda (`load_skill`) en vez de un único prompt monolítico — ese es el patrón a replicar para cualquier capability nueva del copiloto/orquestador.
- **D — Dependency Inversion:** los servicios de negocio nuevos deben depender de las abstracciones ya existentes (`crm_providers.protocols`, `llm.providers`, `llm.jev.JevClient`), nunca de un SDK concreto de HubSpot/Pipedrive/OpenRouter importado directo dentro de lógica de dominio.

### Paso 4 — Spec de la feature (formato de salida obligatorio)
Para cada feature, produce un documento con exactamente estas subsecciones:

```
## Feature: <nombre>
Fuente: §<sección del análisis>
Prioridad: V1 | V2/V3 (según §9 del análisis)

### En una frase
Una o dos frases, en español llano, sin jerga técnica: qué va a poder hacer o ver el usuario que hoy no puede. Si no se puede explicar así de simple, probablemente el alcance de la feature todavía no está claro — resuélvelo antes de seguir, no lo escondas detrás de tecnicismo.

### Por qué (first principles)
...

### Qué ya existe (auditoría)
- Reutiliza: <path> — <qué hace hoy, qué falta>
- Patrón a replicar: <path de referencia>
- Gap real (código nuevo necesario): <...>

### Backend
- Modelos/migraciones: <tabla nueva o columna nueva, siguiendo numeración de backend/migrations/NNN_*.sql>
- Servicio(s): <nuevo paquete en app/services/<dominio>/ o extensión de uno existente>
- Endpoint(s): <verbo + ruta, en app/api/<router>.py, siguiendo el patrón de router existente>
- Integración con el pipeline existente: <dónde engancha: extracción → aprobación → sync CRM → notificación, citando los servicios reales: extraction.py, memo_approval.py, memo_crm.py, crm_updates.py, pipeline_lease.py>
- LLM/clasificación: <qué modelo, cuándo Jev vs. LLM abierto, con justificación según §1.4 del análisis (determinismo donde se pueda)>

### Frontend / Dashboard
- Dónde vive en la UI: <página/ruta en src/pages/dashboard/, siguiendo la convención de src/features/<feature>/>
- Componente(s): <nuevo en src/components/dashboard/<area>/ o extensión>
- Estado/datos: <TanStack Query — qué hook, qué endpoint consume>
- Principio de diseño aplicado: <cómo cumple §7.1 del análisis: mínimo de botones/tabs, progressive disclosure, prioridad para el comercial vs. el manager>
- Copy/interacción: <ejemplo concreto de la frase/gesto, sin AI slop, según §1.2>

### Criterio de aceptación (Definition of Done)
- [ ] ...

### Riesgos / edge cases conocidos
<citar los edge cases ya identificados en el análisis para esta feature, si los hay>
```

### Paso 5 — Secuenciación final
Al terminar todas las specs individuales, produce un **orden de ejecución único** (no una lista de "V1 features" sin orden), con justificación de por qué cada feature va antes o después de la siguiente (dependencias técnicas reales: p. ej. la priorización de contactos §3.1 depende de que el orquestador §3.2 ya tenga acceso a intelligence de llamadas recientes, que a su vez depende del pipeline de extracción ya existente).

---

## 4. Mapa del sistema existente (punto de partida obligatorio)

Esto es lo que confirmé leyendo el repo directamente — no es una suposición. Donde algo está marcado "verificar", significa que solo confirmé que el archivo existe por su nombre/ubicación, no que leí su contenido completo — ábrelo tú antes de asumir qué hace exactamente.

### 4.1 Monorepo y repos hermanos

| Repo | Rol | Ruta |
|---|---|---|
| `getvocify` | Monorepo principal: dashboard React + backend FastAPI + chrome extension + app nativa de HubSpot | `~/getvocify` (este repo) |
| `getvocify-desktop` | App de escritorio (Electron) — la "desktop app" que graba meetings/warm calls (§2 del análisis). Repo git separado. | `~/getvocify-desktop` (`electron-main.mjs`, `preload.cjs`, `renderer/`, `native/`, `server.mjs`) |
| `signalcore` (`signalcore-backend`, `signalcore-frontend`) | Producto hermano de Dani, citado como referencia de patrón para el "Wizard"/orquestador proactivo y la campanita de notificaciones (§3.2 y §8 del análisis) | `~/signalcore/signalcore-backend`, `~/signalcore/signalcore-frontend` |

El propio `getvocify/desktop/` (dentro de este monorepo) es solo un `README.md` — no es la app de escritorio real; la app real vive en el repo hermano `getvocify-desktop`. No confundas ambos al planificar la feature de captura de meetings.

### 4.2 Backend — orquestador / copiloto conversacional (relevante a §3.2 y §6.1 del análisis)

El "Ask Vocify / Wizard" **ya existe parcialmente**, como copiloto de WhatsApp:

- `backend/app/services/crm_copilot/` — el loop conversacional completo:
  - `loop.py` — orquesta el turno de conversación, historial, compactado de mensajes largos.
  - `tools.py` — tools ejecutables (`execute_tool`, `confirmation_required`, `clear_focus`, `expire_stale_focus`).
  - `route.py` — detección de cambio de foco / reset de sesión.
  - `prompts.py` — construcción del system prompt.
  - `soul.md` — el "persona file": define el comportamiento (contact-first, reads inmediatos, writes con confirmación Actualizar/No actualizar, nunca inventa IDs/URLs, nunca muestra tool calls crudos al usuario).
  - `skills/*.md` (`lookup.md`, `voice.md`, `update.md`, `pick.md`) — skills cargables bajo demanda vía `load_skill`, no todo el prompt de una vez.
- `backend/app/services/copilot/` — `suggest.py` + `prompts.py`, un motor de sugerencias separado (**verificar** su relación exacta con `crm_copilot` antes de diseñar el orquestador de tareas proactivas de §3.2 — puede que ya cubra parte de "qué sugerir hoy").

**Implicación para tu plan:** la superficie de WhatsApp de §6.1 ya está construida sobre esta base. Lo que falta, según el análisis, es: (a) el chat equivalente dentro del dashboard, (b) evolucionar la feature de "grabar audio" de la landing/extensión de unidireccional a bidireccional, y (c) la capa de orquestación proactiva diaria de §3.2 (listado diario de tareas imprescindibles, mezclando manuales + detectadas). Ninguna de las tres debería reimplementar el loop conversacional — deben reutilizar `crm_copilot/loop.py` y su patrón de skills, extendiendo el conjunto de tools/skills, no creando un segundo motor de chat.

### 4.3 Backend — clasificación estructurada / determinista (relevante a §5 y §6.4)

**Jev.ai ya está integrado**, no es una integración nueva a construir:

- `backend/app/services/llm/jev.py` — `JevClient`, usa OpenRouter System One (`typesafe/jev-1.13` por defecto, configurable vía `JEV_MODEL`), con `MIN_CONFIDENCE_THRESHOLD = 0.50`, timeout configurable, y un formato de llamada `state + questions → answers` (exactamente el patrón de "outputs acotados" descrito en §6.4 del análisis).

**Implicación para tu plan:** la detección booleana de "meeting booked" (§5) y la clasificación de tipo de objeción (§4.5) **no requieren integrar nada nuevo** — requieren definir nuevos `questions` schemas para `JevClient` y enganchar la respuesta al pipeline de extracción/actualización ya existente. Esto es directamente relevante al principio de "determinismo donde se pueda" (§1.4): el mecanismo determinista-acotado que pedía Dani ya existe como infraestructura, el gap es solo de definición de preguntas + integración de pipeline.

### 4.4 Backend — abstracción multi-CRM (relevante a §3.4, §6.2, §6.3)

- `backend/app/services/crm_providers/` — `protocols.py` (contrato común), `factory.py`, `resolve.py`, `errors.py`, y un provider por CRM: `hubspot_provider.py`, `pipedrive_provider.py`, `salesforce_provider.py`.
- Confirma en `backend/ARCHITECTURE_NOTES.md` que el propio equipo ya documentó como *mejora futura explícita* generalizar el matching/preview/sync a multi-objeto (deals/contacts/companies) mediante un `CRMObjectMatcher`/`CRMUpdatePreview` genérico — actualmente el código es **deal-first** por decisión deliberada ("Deals are the core value proposition").

**Implicación para tu plan:** cualquier feature nueva que necesite leer o escribir en el CRM (meeting booked, scoring, coaching feedback, tareas inteligentes) debe pasar por esta capa de providers, nunca hablar directo con la SDK de HubSpot. Si una feature requiere trabajar con un objeto de CRM que hoy el matcher no soporta bien (p. ej. contactos o companies en vez de deals), señala explícitamente que estás activando la refactorización ya prevista en `ARCHITECTURE_NOTES.md`, no la trates como trabajo nuevo no documentado.

### 4.5 Backend — pipeline de memo → extracción → aprobación → CRM (relevante a §4.6, §5, §7.4)

Ya existe un pipeline completo de: grabación → transcripción → extracción → propuesta de update → aprobación → sync a CRM, con background jobs:

- Modelos: `models/memo.py`, `models/approval.py` (`DealMatch`, `ContactMatch`, `ProposedUpdate`, con `match_confidence` y `match_reason` ya modelados), `models/crm_update.py` (`status: pending/success/failed/retrying`, con `retry_count`).
- Servicios: `services/extraction.py`, `services/extraction_context.py`, `services/extraction_policy.py`, `services/memo_approval.py`, `services/memo_crm.py`, `services/memo_playback.py`, `services/deal_merge.py`, `services/deal_lookup.py`, `services/task_merge.py`, `services/crm_updates.py`.
- Background jobs: `services/pipeline_lease.py`, `services/pipeline_meta.py` — el mecanismo de "background job que corres y revisas cuando quieres", exactamente el patrón que pide §4.6 (brief post-interacción no instantáneo).
- Transcripción multi-proveedor ya existe: `services/deepgram_batch.py`, `services/speechmatics_batch.py`, `services/stt_batch.py`, `services/stt_channels.py`.
- `services/relative_dates.py` — **verificar** si ya resuelve el requisito de §5 de capturar correctamente fecha/hora exacta de un meeting a partir de lenguaje relativo ("el martes a las 5") antes de construir un parser nuevo.

**Implicación para tu plan:** el "brief post-interacción configurable" (§4.6), el "checklist auto-check" (§4.7), la "detección de meeting booked" (§5) y el "reporting diario/semanal" (§4.10, §7.2) son todos, en esencia, **nuevas salidas del mismo pipeline de extracción existente**, no pipelines nuevos. Tu spec debe mostrar explícitamente en qué punto de `extraction.py` → `memo_approval.py` → `crm_updates.py` se engancha cada output nuevo, y qué campo/tabla nueva hace falta para persistirlo (siguiendo el patrón de migraciones numeradas en `backend/migrations/`, la última existente es `036_crm_updates_upsert_deal.sql`).

### 4.6 Backend — routers/API existentes

`backend/app/api/`: `admin.py`, `auth.py`, `billing.py`, `calls.py`, `company.py`, `copilot.py`, `crm.py`, `crm_pipedrive.py`, `crm_salesforce.py`, `glossary.py`, `health.py`, `hubspot_recordings.py`, `memos.py`, `router.py` (registro central), `stripe_webhooks.py`, `transcription.py`, `voice_enrollment.py`, `webhooks.py`. Cualquier endpoint nuevo debe seguir esta convención de un router por dominio, registrado en `router.py`, no amontonarse en un router genérico.

### 4.7 Frontend — estructura y convención

Stack confirmado en `docs/VOCIFY_DEVELOPER_GUIDE.md`: React 18 + TypeScript + Vite 5 + Tailwind + shadcn/ui + TanStack Query.

- `src/features/<dominio>/` — lógica por dominio (`api/`, `hooks/`, `components/`, `types.ts`, `index.ts`). Dominios ya existentes: `admin`, `auth`, `billing`, `calls`, `company`, `copilot`, `integrations`, `memos`, `recording`, `recordings`.
- `src/pages/dashboard/` — páginas/rutas del dashboard.
- `src/components/dashboard/` — componentes de UI del dashboard, ya organizados por sub-área: `crm/`, `hubspot/`, `pipedrive/`, `salesforce/`, `calling/`, `memos/`, `settings/`, `glossary/`, más piezas sueltas como `ActivityPanel.tsx`, `CopilotNote.tsx`, `DashboardLayout.tsx`, `AuthorLabel.tsx`, `AuthorFilter.tsx`, `VoiceRecorderWidget.tsx`.
- `src/lib/api/` — cliente API compartido.

**Implicación para tu plan:** `ActivityPanel.tsx` y `CopilotNote.tsx` son candidatos directos a extender para (a) el listado diario de tareas imprescindibles de §3.2/§3.3, y (b) el chat de Ask Vocify dentro del dashboard de §6.1, respectivamente — **ábrelos y confirma qué hacen hoy antes de decidir si se extienden o se reemplazan.** Cualquier feature nueva de dashboard (settings de playbook, panel de objeciones de equipo, dashboard de head of sales) debe seguir el mismo patrón `feature/` + componente en `components/dashboard/<area>/`, no crear una estructura paralela.

### 4.8 Otras superficies relevantes ya existentes

- `chrome-extension/` — la extensión de captura de cold calls citada en el análisis como la limitación técnica que empuja varias features a V2 (checklist en vivo, tarjeta de objection handling para SDRs — §4.7, §4.8). Antes de diseñar cualquier feature "solo para meetings, no para cold calls", confirma en este código cuál es la limitación técnica real actual, en vez de asumir la que describe la transcripción (puede haber cambiado).
- `hubspot-app/` — app nativa embebida en HubSpot (`hsproject.json`, `src/`). El análisis no la menciona explícitamente como superficie objetivo de ninguna feature — no la uses como destino de ninguna feature de este plan a menos que el propio Dani lo pida; solo se documenta aquí para que no la confundas con el dashboard propio de Vocify al auditar "dónde vive esto en la UI".

### 4.9 Trabajo de diseño ya hecho (21 sep y 11 ago) — léelo antes de especificar 5 de las 15 features

Dos pares plan+spec en `docs/superpowers/` ya resolvieron, con código validado contra el repo, una parte grande de esta build queue. No los estás reabriendo ni reinterpretando — los estás **usando** como ya dijo §0. Esto es lo que cada uno cubre y por qué te importa:

**a) Kernel de UI compartido (fundacional, sin equivalente en mi §5.1 original)**
`docs/superpowers/specs/2026-09-21-copilot-spine-design.md` §3 diseña, y `docs/superpowers/plans/2026-09-21-copilot-spine-foundation-and-followup.md` Tasks 1-5 implementan paso a paso, un kernel de componentes de UI (`shared/ui/`, `shared/tokens/`) escrito una sola vez como *custom elements* de light-DOM (sin frameworks), con un puente ya hecho para React (`useVElement`, Task 13) y copiado automáticamente a la extensión y al desktop (`scripts/sync-shared.mjs`). **Por qué te importa:** cualquier feature de tu build queue cuya tarjeta/UI tenga que verse igual en dashboard + extensión + desktop (candidatas claras: meeting booked, checklist de meeting, la tarjeta de objection handling, el feed diario de tareas) debe construirse como un componente de este kernel, no como tres implementaciones sueltas en React/vanilla-extensión/vanilla-desktop. No diseñes un componente de UI nuevo para esas features sin pasar primero por `shared/ui/components/`.

**b) Follow-up de email — ya tiene plan ejecutable, no lo vuelvas a diseñar**
El plan completo de 14 tasks (migración, lógica pura con 9 tests, servicio con lease de single-flight, endpoints, integración en extensión/desktop/web, verificación end-to-end) ya existe y está verificado línea por línea contra el código real (`docs/superpowers/plans/2026-09-21-copilot-spine-foundation-and-followup.md` Tasks 6-14). **Corrección a mi §5.1.4, ítem 7 de este prompt:** ahí dije que "follow-up email" era un *tipo de tarea* subordinado al orquestador, a construir después de él. Es incorrecto — el plan real lo trata como su propia feature de primera clase (slice 1), que se construye **antes** que el orquestador/feed de tareas (slice 2) y de forma independiente. Cuando llegues a esa feature en tu Paso 4, tu spec es: ejecutar ese plan tal cual, no rediseñar la arquitectura.

**c) "Hoy engine" = tu build queue ítem 7 (orquestador + tiers + tareas inteligentes), ya diseñado con lógica validada**
`docs/superpowers/specs/2026-09-21-copilot-spine-design.md` §5 diseña (con 14 tests corridos, aunque **todavía no convertido en plan task-by-task** — eso sigue siendo trabajo tuyo) el motor que decide qué le sale al comercial cada día: señales derivadas por contacto (`commitment_due`, `going_cold`, `objection_open`) que se recalculan solas y nunca resucitan algo que el comercial ya descartó, más frases explicativas (`reason()`, `due_label()`) escritas con **plantillas deterministas en el servidor, no con un LLM** — esto resuelve mejor que mi propia propuesta el principio de "sin AI slop" de §1.2 del análisis. También revela que 2 de los 4 datos de entrada que yo daba por "nuevos" en mi F0 **ya existen**: la fecha de un compromiso ya se deriva en `services/hubspot/tasks.py` (función `detected_task_due_iso`), y la taxonomía de objeciones ya existe en `services/copilot/prompts.py:39`. Solo `interest` (nivel de interés del contacto) y `origin` de un compromiso (si lo pidió el prospecto o lo prometió el comercial) son campos nuevos de verdad, y el propio spec ya dice cómo clasificarlos: con `JevClient`, igual que ya se usa para los dropdowns de CRM. **Corrección a mi §5.1.2/§5.1.4 (F0):** no diseñes esta capa desde cero — toma `signals_for_contact`, `reconcile`, `reason` y `due_label` del spec (§5.3) como el contrato ya decidido, y tu trabajo en el Paso 4 es convertir eso en un plan task-by-task (con tests), no en inventar otra arquitectura de señales.

**d) La "tarjeta en vivo" (mi ítem 12, el que yo marqué como el mayor riesgo técnico) — ya está construida, no es territorio nuevo**
Antes de este spec, ya se construyó y quedó en beta un copiloto de objeciones en tiempo real: `docs/superpowers/plans/2026-08-11-realtime-objection-copilot.md` (Task 1, backend, ya marcado como hecho) monta `POST /api/v1/copilot/suggest` en streaming (SSE) sobre la transcripción en vivo de Speechmatics, expuesto hoy en una página beta `/dashboard/copilot`. Es el mismo `services/copilot/suggest.py` que yo había encontrado en mi auditoría sin saber para qué era — ahora confirmado. **Corrección a mi §5.1.4, ítem 12:** el riesgo que yo marqué ("requiere señal en vivo durante la llamada, streaming no confirmado") ya no aplica — el streaming ya existe y funciona. Lo que sí falta, y es lo que diseña `2026-09-21-copilot-spine-design.md` §6.2 ("grounded live pill", slice 5, con 6 tests): que esa sugerencia solo se muestre cuando está respaldada por el playbook o por patrones probados (el criterio "grounded" de §1.4 del análisis — determinismo/evidencia antes que opinión del LLM), con una máquina de estados que la mantiene visible un mínimo de tiempo, la oculta si el comercial ya está hablando, y nunca repite la misma categoría de objeción antes de 60 segundos. Esta parte tampoco tiene plan task-by-task todavía — sí tiene el diseño y los tests de la lógica pura (`shared/ui/pill.js`), que debes tomar como contrato, no rediseñar.

**Qué falta hacer con estos cuatro puntos:** (a) y (b) ya son ejecutables tal cual — no les hagas Paso 2/3, ejecuta el plan. (c) y (d) tienen el diseño/algoritmo ya resuelto y validado, pero les falta el plan task-by-task (migraciones exactas, endpoints, wiring por surface) — ahí sí hay trabajo real de Paso 4 para ti, partiendo del contrato ya dado en vez de inventar uno.

---

## 5. Build queue V1 (orden base, ajustar según Paso 5 de la metodología)

Toma esta lista tal cual del §9 del análisis (con la corrección de Slack/Teams aplicada según §0 de este prompt) como el conjunto de features a especificar. No añadas ni quites features de este conjunto — tu trabajo es especificar cada una, no redefinir el alcance:

1. Pilar A: cierre de la integración de captura con la desktop app existente (`getvocify-desktop`) — sin nueva fuente de captura.
2. Enviar mails de follow-up (marcado en el análisis como pendiente de implementar, §3 tabla).
3. Prepararse para la llamada / prepararse para el meeting (resumen de contexto previo — pendiente de implementar, §3 tabla).
4. Priorización de contactos a llamar (tiers) + sitio en la UI del dashboard para esto (§3.1).
5. Orquestador de inteligencia / listado diario de tareas imprescindibles (§3.2).
6. Tareas inteligentes proactivas con contexto + gesto único (§3.3).
7. Ask Vocify / Wizard: chat en dashboard + evolución de audio de landing/extensión a bidireccional (§6.1) — WhatsApp ya construido, no rehacer.
8. Coaching: playbooks por tipología + onboarding self-serve (texto/PDF/audio) (§4.2, §4.3).
9. Coaching: scoring simple, con opción de que el head of sales defina qué es "buena llamada" (§4.4).
10. Clasificación de objeciones (híbrido LLM + Jev) + UI para notas manuales en tiempo real (§4.5).
11. Brief post-interacción como background job configurable (§4.6).
12. Checklist auto-check + tarjeta de objection handling en tiempo real — solo meetings (§4.7, §4.8).
13. Reporting diario/semanal al rep — email (Resend) + campana en dashboard (§4.10, §8).
14. Detección de "meeting booked" vía IA (boolean + fecha/hora exacta), distinguido de "close" (§5).
15. Dashboard de equipo (head of sales): performance, panel de objeciones, menciones de competidores, reportes programados, manager chat, win-loss insights, métrica de adherencia al playbook (§7.2, §7.4).

Explícitamente **fuera de esta build queue** (confirma que tu plan no las incluye): integración directa de Gmail, Composio, detección de tono/emoción real, curso guiado por IA para el playbook, notificaciones Slack/Teams, notificaciones push de WhatsApp, roleplay con IA, coaching en vivo expandido, checklist/tarjeta en tiempo real para SDR/cold-calling, dashboard personalizable por chat, leaderboards. Estas están en §9 del análisis como V2/V3 o descartadas — si alguna te parece trivial de incluir de paso, no lo hagas: es una decisión de scope ya tomada, no un descuido.

---

## 5.1 Juicio técnico aplicado: arquitectura y orden real de construcción

> Esta sección resuelve el Paso 2 (auditoría) y el Paso 3 (diseño SOLID) de la metodología del §3 para las 15 features del build queue, con el juicio ya aplicado — no es una plantilla a rellenar, es el veredicto. Ejecutar el Paso 4 sobre cada veredicto de aquí (migraciones exactas, endpoints, componentes) es tu trabajo; volver a decidir la arquitectura desde cero no lo es. Si al abrir un archivo real un veredicto no encaja con lo que ves, gana el código (regla de §0) — corrígelo aquí explícitamente, no lo sigas a ciegas ni lo descartes en silencio.

### 5.1.1 Por qué el orden de §9 del análisis no es el orden de construcción

El listado de §9 del documento de análisis refleja el orden en que se **habló** de las features en la reunión — prioridad de producto, no dependencia técnica. Varias features comparten una misma pieza de infraestructura subyacente que hoy no existe como tal; construirla una sola vez, bien, y dejar que el resto la consuma, es más barato y más coherente que dejar que cada feature reinvente su propia mini-versión. Ese es el criterio de secuenciación que sigue esta sección — no descartes el orden de producto de §9 (sigue siendo la referencia de qué es V1 vs. V2/V3), pero el orden de **construcción** es el de aquí.

### 5.1.2 Capas fundacionales compartidas (se construyen primero; todo lo demás depende de ellas)

**F0 — Extensión del pipeline de extracción con "señales" estructuradas**
Hoy `extraction.py` produce la extracción de una llamada para el flujo memo→CRM. Al menos cinco de las quince features del build queue (tareas inteligentes, scoring, objeciones, meeting booked, reporting) necesitan leer datos nuevos de esa misma extracción: tipo de interacción (cold call / meeting / discovery / cierre), objeciones detectadas, si hubo compromiso de meeting, si hace falta follow-up.
**Veredicto:** esto se añade una vez, como campos nuevos en el modelo de salida de extracción — por Single Responsibility, la extracción sigue siendo el único lugar que interpreta el transcript crudo. Ninguna feature de intelligence debe volver a tocar el transcript crudo por su cuenta; todas consumen este output ya tipado.

**F0.1 — Módulo central de Jev question-schemas**
`JevClient` ya existe (`services/llm/jev.py`) pero no hay hoy un lugar único donde se definan las preguntas de clasificación del dominio de ventas.
**Veredicto:** crear un módulo (p. ej. `services/llm/jev_schemas.py`) que centralice los `questions` para tipo de objeción, objeción-vs-obstáculo, y meeting-booked. Por Interface Segregation, cada feature importa solo el schema que necesita; por Dependency Inversion, las features dependen de este módulo, nunca del formato crudo de la API de OpenRouter System One.

**F0.2 — Onboarding de playbooks (Settings)**
Scoring, checklist en vivo y la tarjeta de objection handling en tiempo real comparten un mismo insumo: el playbook de la empresa como contexto de prompt.
**Veredicto:** aunque en la conversación se discutió después del scoring, técnicamente va primero — sin playbook cargado no hay contra qué medir adherencia ni qué sugerir en tiempo real. Es la única de las tres piezas fundacionales que además es una feature de cara al usuario (settings del head of sales), así que puede entregarse de forma visible antes de que el resto de coaching exista. Por Open/Closed: el playbook se modela como **dato** de configuración por tipología de interacción, no como código — añadir una tipología nueva no debe requerir tocar código, solo datos.

### 5.1.3 Orden de ejecución recomendado (dependencia técnica real)

1. **Cierre de captura con `getvocify-desktop`** — sin esto, meetings no alimentan el mismo pipeline que cold calls; cualquier feature de intelligence tendría datos incompletos desde el día uno. Nota: la propia app de escritorio ya tiene un plan de importación al monorepo listo para ejecutar (`docs/superpowers/plans/2026-09-21-copilot-spine-foundation-and-followup.md` Task 1) — empieza por ahí, no rediseñes cómo se integra.
1.5. **Follow-up email (slice 1)** — **corrección respecto a la versión anterior de este documento:** aquí yo mismo lo trataba como un *tipo de tarea* dentro del orquestador (ítem 7). Es incorrecto — el plan ya existente y verificado (§4.9.b de este prompt) lo construye como feature independiente, y **no depende de F0/F0.1/F0.2**: lee directamente los campos que `extraction.py` ya produce hoy (`summary`, `nextSteps`, `contactName/Email/Phone`), sin necesitar ninguna señal nueva. Por eso va aquí, justo después del cierre de captura, no esperando a la fundación de señales de abajo. Ejecuta ese plan tal cual — no lo vuelvas a diseñar.
2. **F0 — señales en `extraction.py`**
3. **F0.1 — Jev question-schemas**
4. **F0.2 — Onboarding de playbooks (settings)**
5. **Ask Vocify en dashboard** — depende solo de UI + reutilizar `crm_copilot/loop.py`; no depende de F0/F0.1/F0.2. Puede construirse en paralelo a 2-4 si hay dos personas disponibles, pero no antes del punto 1, porque parte de su valor es responder sobre actividad reciente que aún no existiría.
6. **Priorización de contactos (tiers, §3.1 del análisis)** — depende de F0 (necesita "pain confirmado" y "última interacción" por contacto ya calculados).
7. **Orquestador / listado diario de tareas ("Hoy") + prep de llamada/meeting** — depende de 6 y de F0. **Corrección respecto a la versión anterior:** follow-up email ya NO es un tipo de tarea de este orquestador (se movió al paso 1.5, ver arriba). Lo que sí sigue aquí, y ahora con diseño y algoritmo ya validados (no a inventar), es el motor de señales diarias por contacto (§4.9.c de este prompt) — commitment_due / going_cold / objection_open, con sus reglas de reconciliación y sus frases explicativas ya escritas como plantillas deterministas. La prep de llamada/meeting con resumen de contexto (§3 tabla del análisis, marcada "NECESITAMOS IMPLEMENTARLO") sigue siendo un gap real sin diseño previo que reutilizar — no la confundas con el motor de señales, son dos cosas dentro del mismo feed.
8. **Scoring** — depende de F0.2 (playbook) y F0.
9. **Clasificación de objeciones + UI de notas manuales en tiempo real** — depende de F0.1.
10. **Detección de meeting booked** — depende de F0.1 y del flujo de aprobación existente (`models/approval.py`, `crm_updates.py`).
11. **Brief post-interacción (background job)** — depende de 8 y 9 (necesita scoring y objeciones ya generados para tener contenido que resumir).
12. **Checklist auto-check + tarjeta de objection handling en tiempo real (solo meetings)** — depende de F0.2 y de que la captura de meetings soporte señal en vivo durante la llamada. **Gap técnico a confirmar antes de comprometer alcance:** verificar si `stt_channels.py` / la integración con `getvocify-desktop` ya expone transcripción en streaming, o si eso es en sí mismo el trabajo nuevo más grande de esta feature.
13. **Reporting diario/semanal (email + campana)** — depende de 8, 9, 10 y 11: es la primera feature que consolida datos que las anteriores ya generaron, no genera datos nuevos por sí misma.
14. **Dashboard de equipo (head of sales)** — depende de todo lo anterior. Es una capa de agregación sobre datos que ya deben existir (scoring, objeciones, meeting booked, adherencia al playbook). Construirla antes dejaría un dashboard vacío o con datos mockeados, que es exactamente lo que las instrucciones globales de este proyecto prohíben ("no placeholders, fake data, o filler logic en código de producción") — este es el motivo técnico, no solo de producto, por el que va última.

### 5.1.4 Veredicto de arquitectura por feature

Formato corto por cada punto de la secuencia de §5.1.3: **Reutiliza** → **Patrón aplicado** → **Nuevo real**.

**1 — Cierre de captura con desktop app**
- Reutiliza: pipeline de memos ya existente completo (`api/memos.py`, `deepgram_batch.py`/`speechmatics_batch.py`, `memo_playback.py`) + el repo `getvocify-desktop`.
- Patrón: mantener el límite ya existente (desktop = captura, backend = interpretación) — Single Responsibility ya correcto; no metas lógica de negocio en el Electron app.
- Nuevo real: probablemente ninguno de dominio; a lo sumo, confirmar que el desktop app postea al mismo contrato que usa la extensión contra `api/memos.py` — si no, ese es el único gap.

**F0 — Señales en extraction.py** (fundacional, no es un ítem de cara al usuario)
- Reutiliza: `extraction.py`, `extraction_context.py`, `extraction_policy.py`.
- Patrón: Single Responsibility — un único lugar interpreta el transcript crudo; todo lo demás consume su output tipado.
- Nuevo real: campos nuevos en el modelo de salida (tipo de interacción, objeciones detectadas, meeting_booked, necesita_followup) + la lógica que los llena (LLM abierto para lo cualitativo, Jev para lo booleano/multiselect vía F0.1).

**F0.1 — Jev question-schemas** (fundacional)
- Reutiliza: `JevClient` completo, sin tocar su cliente.
- Patrón: Interface Segregation (un schema por necesidad, no un mega-dict compartido) + Dependency Inversion (las features dependen del módulo de schemas, no de la API cruda).
- Nuevo real: el módulo de schemas en sí y su wiring dentro de F0.

**F0.2 — Onboarding de playbooks**
- Reutiliza: patrón de Settings ya existente en `components/dashboard/settings/`, storage en Supabase.
- Patrón: Open/Closed — tipología de interacción como dato, no como código.
- Nuevo real: tabla de playbooks (texto / PDF parseado / transcript de audio) por tipología + UI de settings para las 3 vías de carga — sin flujo guiado por IA, por el guardrail de §6.

**5 — Ask Vocify en dashboard**
- Reutiliza: `crm_copilot/loop.py`, `tools.py`, `skills/*.md` completos — mismo motor que WhatsApp.
- Patrón: Liskov Substitution — el dashboard es un canal más sobre el mismo loop; debe poder sustituir a WhatsApp sin que el loop lo sepa, la diferencia es solo el adaptador de transporte.
- Nuevo real: adaptador de transporte (websocket o polling desde React) + componente de chat en dashboard, extendiendo `CopilotNote.tsx` — confirmar primero qué hace ese componente hoy antes de decidir si se extiende o se reemplaza.

**6 — Priorización de contactos (tiers)**
- Reutiliza: F0 (pain confirmado, última interacción) + `crm_providers` para el estado real del contacto/deal.
- Patrón: Single Responsibility — un servicio de "prioridad de contacto" separado del orquestador de tareas (#7), que #7 consume; no un cálculo embebido dentro del feed.
- Nuevo real: el servicio de tiers + el sitio en la UI que pide explícitamente §3.1 del análisis — candidato: una sección dentro de `ActivityPanel.tsx`, a confirmar tras abrirlo.

**7 — Orquestador / listado diario de tareas ("Hoy") + prep de llamada/meeting** — *corregido por el spec de spine, ver §4.9.c*
- Reutiliza: el diseño ya validado de `docs/superpowers/specs/2026-09-21-copilot-spine-design.md` §5 (`signals_for_contact`, `reconcile`, `rank_cards`, `reason`, `due_label` — 14 tests) como contrato, no como referencia a reinterpretar. De los 4 datos de entrada que necesita, 2 ya existen: fecha de compromiso (`services/hubspot/tasks.py::detected_task_due_iso`) y taxonomía de objeciones (`services/copilot/prompts.py:39`). F0.1 (Jev schemas) cubre los 2 que faltan: `interest` y `origin` del compromiso.
- Patrón: el motor nunca "crea tareas" — recalcula señales derivadas por contacto y reconcilia contra lo ya mostrado (nunca resucita algo que el comercial ya descartó). Las frases (`reason`, `due_label`) son plantillas deterministas server-side, no LLM — coherente con "sin AI slop" de §1.2 del análisis, y más estricto que mi propuesta original.
- Nuevo real: (i) convertir el diseño de §4.9.c en un plan task-by-task (migraciones para guardar el estado de cada señal — pending/done/dismissed/snoozed —, el job de reconciliación por evento y el cron diario por zona horaria), cosa que el spec deja explícitamente para después; (ii) la prep de llamada/meeting con resumen de contexto, que sí es gap real sin diseño previo — resumen de: si ya se le llamó antes, qué se dijo, y next steps pendientes, generado a partir del mismo F0.

**12 — Checklist en vivo + tarjeta de objection handling** — *corregido por el spec de spine y el plan de agosto, ver §4.9.d*
- Reutiliza: el copiloto de objeciones en tiempo real que **ya está construido** (`services/copilot/suggest.py`, `services/copilot/prompts.py`, endpoint `POST /api/v1/copilot/suggest` en streaming SSE sobre transcripción en vivo de Speechmatics, hoy expuesto en beta en `/dashboard/copilot`) + el diseño ya validado de la máquina de estados "quiet by contract" (`shared/ui/pill.js`, 6 tests: se mantiene visible un mínimo, se oculta si el comercial ya está hablando, nunca repite la misma categoría antes de 60s) + F0.2 (playbook, para el criterio "grounded").
- Patrón: Interface Segregation — el pill solo consume "¿es una objeción?, ¿está respaldada por playbook/patrón probado?", no el transcript completo; Quiet by contract — el servidor solo marca `grounded: true` cuando hay evidencia real, y el cliente no muestra nada que no venga marcado así.
- Nuevo real: embeber esta tarjeta (ya construida como página beta separada) dentro del flujo real de meeting, usando el kernel de UI compartido (§4.9.a) en vez de la página `/dashboard/copilot` aislada actual; añadir el campo `grounded`/`source_label` en la respuesta del suggest existente; y el checklist auto-check en sí (apertura/pitch/objection handling/cualificación como booleans por paso) sigue siendo gap real, aunque ahora se apoya en infraestructura de streaming que ya existe y funciona — **corrección al riesgo que yo marcaba antes:** no hace falta validar si hay streaming en vivo, ya lo hay; el trabajo real es de integración y de UI, no de construir transcripción en tiempo real desde cero.

**8 — Scoring**
- Reutiliza: F0.2 (playbook como prompt) + F0 (transcript ya extraído).
- Patrón: Single Responsibility — el scoring consume F0.2+F0, no re-procesa el transcript crudo.
- Nuevo real: prompt de scoring parametrizado por tipología (§4.4 del análisis) + almacenamiento del score por interacción + que el head of sales pueda configurar qué es "buena llamada" (dato de configuración, no código nuevo por cliente).

**9 — Clasificación de objeciones + notas manuales en tiempo real**
- Reutiliza: F0.1 (schema de tipo de objeción) para la parte cerrada; el LLM abierto ya usado en `crm_copilot`/`extraction.py` para la lectura de contexto/ironía.
- Patrón: separación explícita de responsabilidad entre el clasificador determinista (Jev) y el LLM de lectura contextual — no mezclar ambos en una sola llamada, exactamente la distinción que ya hace §4.5 del análisis.
- Nuevo real: UI de nota manual en tiempo real durante la interacción (confirmar si ocurre en el desktop app o en la extensión — dónde vive hoy la grabación en vivo) + el enganche de esa nota a un timestamp de la transcripción.

**10 — Meeting booked**
- Reutiliza: F0.1 (schema boolean) + `models/approval.py`/`crm_updates.py` (flujo de propuesta-aprobación-sync ya existente, con `match_confidence` ya modelado).
- Patrón: Dependency Inversion — la detección no escribe directo al CRM; pasa por `crm_providers` y el mismo flujo de aprobación que cualquier otro update, heredando su umbral de confianza y su registro de estado (pending/success/failed).
- Nuevo real: el schema de Jev específico + captura de fecha/hora exacta (confirmar primero si `relative_dates.py` ya resuelve esto antes de construir un parser nuevo).

**11 — Brief post-interacción**
- Reutiliza: `pipeline_lease.py`/`pipeline_meta.py` (background job ya existente) + salida de #8 y #9.
- Patrón: el brief es una vista/agregación sobre datos ya generados, no un segundo pipeline de análisis del transcript.
- Nuevo real: el job que arma el brief + el timing configurable (ahora / después / fin del día) como preferencia de usuario.

**13 — Reporting diario/semanal**
- Reutiliza: la salida de #8, #9, #10, #11 + Resend para email (§8 del análisis) + el patrón de campana ya construido en SignalCore, a replicar, no a inventar desde cero.
- Patrón: agregación pura, mismo principio que #11 y #14.
- Nuevo real: job de agregación diaria/semanal + template de email + endpoint de campana en dashboard.

**14 — Dashboard de equipo**
- Reutiliza: todo lo anterior — es agregación pura sobre datos que ya deben existir para el momento en que se construye esto. `activity_scope.py`/`company_scope.py` ya existentes para el scoping por cuenta.
- Patrón: Liskov otra vez — el manager chat es el mismo motor que Ask Vocify (#5) con scope de datos ampliado; debe ser sustituible por el chat individual sin que el loop lo sepa, solo cambia el scope de permisos de lectura.
- Nuevo real: agregaciones por equipo + la métrica de adherencia al playbook (% de pasos cumplidos, computable directamente desde el output de #8/#12) + las vistas de UI siguiendo §7.1 del análisis (mínimo de botones, progressive disclosure).

---

## 6. Guardrails no negociables (decisiones ya cerradas, no las reabras)

- **ICP:** empresas con CRM estructurado (HubSpot o Pipedrive) con 2-way email sync nativo. No diseñes nada que solo tenga sentido para clientes sin CRM.
- **Email vía Gmail directo: no se construye.** Toda lectura de email pasa por el 2-way sync nativo del CRM (`GET` de activity del contacto vía `crm_providers`).
- **Composio: no se usa** como base de integraciones.
- **Detección de tono/emoción real desde transcripción: fuera de scope.** La solución para matices (ironía, sarcasmo) es la nota manual del usuario en tiempo real (§4.5), no sentiment analysis.
- **Meeting booked ≠ close.** Solo se detecta/automatiza el primero (acuerdo verbal de reunión); el cierre (pago) no es detectable por Vocify.
- **Slack/Teams: no se construye** (ver corrección de jerarquía en §0 de este prompt).
- **WhatsApp para notificaciones push de equipo: no se construye** (bloqueado por Meta). El WhatsApp conversacional (Ask Vocify) sí está en scope porque ya existe.
- **Onboarding de playbook: 100% self-serve manual** (texto/PDF/audio). No construyas un flujo de entrevista guiada por IA.
- **Filosofía de UI del dashboard (§7.1):** mínimo de botones/tabs/pantallas, máximo valor por pantalla, progressive disclosure. Cualquier componente nuevo de dashboard debe justificar explícitamente cómo cumple esto, no darlo por sentado.
- **Sin AI slop (§1.2):** cualquier texto generado por IA que vea el usuario (tarea, sugerencia, brief, tarjeta de objection handling) debe ser corto y directo — este es un criterio de aceptación de producto, no solo de estilo, inclúyelo en el "Definition of Done" de cada feature que genere texto.

---

## 7. Cosas explícitamente sin resolver — repórtalas, no las inventes

El propio documento de análisis deja estos puntos abiertos o sin definición clara. No tomes una decisión de producto por tu cuenta en ninguno de estos casos — inclúyelos en tu output como "pendiente de decisión de producto" con las opciones que ves, y sigue adelante con el resto del plan:

- **"Tracking de skills en el tiempo / TTR de objeciones por rep"** (§9, V2/V3) — el propio equipo lo marcó como "duda" en la sesión, nunca se definió qué es exactamente.
- **"Scorecards comparativas entre reps"** — ninguno de los dos entendió qué significaba este punto en su brainstorm original; quedó descartado por falta de definición, no por decisión de producto. No lo definas tú.
- **Alcance exacto de "prepararse para la llamada / el meeting"** — el análisis dice que se hace "con la información que ya se tiene", pero no especifica el formato exacto del resumen ni dónde vive en la UI. Propone una opción razonable basada en los patrones existentes (§4.5 del prompt), pero márcala como propuesta a validar, no como decisión ya tomada.
- **Expansión exacta de scope de HubSpot** mencionada en §6.5 del análisis ("puede necesitar expandirse ligeramente") — no se especificó qué objetos/propiedades nuevas exactamente. Identifica el gap real contra lo que necesita cada feature de tu build queue, no asumas un scope genérico "más amplio".

---

## 8. Output esperado de esta sesión de planning

1. Un documento de auditoría inicial (resultado del Paso 2 de la metodología aplicado a las 15 features de la build queue, antes de diseñar nada) — qué existe, qué se reutiliza, qué es gap real, por feature.
2. Un spec por feature siguiendo exactamente el formato del Paso 4.
3. Un orden de ejecución único con justificación de dependencias (Paso 5).
4. Una lista de discrepancias encontradas entre fuentes (siguiendo el ejemplo de §0 de este prompt) y cómo se resolvieron.
5. Una lista de puntos pendientes de decisión de producto (§7 de este prompt) que requieren que Dani decida antes de poder especificar esa parte del todo.
6. **Un resumen final en lenguaje natural y sencillo de todo el plan** — sin jerga técnica, sin nombres de archivo ni de función — que explique qué se va a construir, en qué orden, y por qué ese orden, como si se lo contaras a alguien que conoce el producto Vocify pero no el código. Este resumen va al final, después de las 15 specs técnicas, no las reemplaza: es la versión que se lee de un tirón para tener claridad antes de entrar al detalle de cada una.

No empieces a escribir código en esta sesión — el entregable es el plan/spec, no la implementación.
