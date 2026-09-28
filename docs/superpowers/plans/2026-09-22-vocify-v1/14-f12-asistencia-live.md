# F12 — Checklist y tarjeta de ayuda en meetings: plan ejecutable

> **Ejecución futura:** usar `executing-plans` dentro del subagente dedicado a esta entrega; la coordinación secuencial usa `subagent-driven-development`. Este documento es planificación, no una implementación ni una autorización para desplegar. Ninguna casilla de ejecución está completada.

**Objetivo:** Mostrar checklist y ayuda respaldada en el overlay existente sin duplicar captura ni motor de copiloto.

**Arquitectura:** Núcleo puro compartido para turnos/SSE/estado; React y Electron son adaptadores. Backend valida playbook/evidencia y extrae observaciones live. Overlay solo renderiza.

**Stack:** FastAPI/Python, Supabase/PostgreSQL, React 18/TypeScript y módulos JS compartidos; Electron/extensión cuando figuren entre las superficies de esta entrega.

**Posición:** 14 de 16. **Estado:** planificada; no iniciada.

**Navegación:** [plan maestro](/Users/danizal/getvocify/proposed_plan.md) · [contratos](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-contracts.md) · [integración y gates](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-integration-and-gates.md)

**Fuentes de esta entrega:** A: [Análisis de producto](/Users/danizal/getvocify/docs/PRODUCT_PLANNING_ANALYSIS_2026-09-21.md) · S: [Diseño Spine](/Users/danizal/getvocify/docs/superpowers/specs/2026-09-21-copilot-spine-design.md) · PF: [Plan previo de fundamentos/follow-up](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-21-copilot-spine-foundation-and-followup.md).

## Entrada, salida y frontera de responsabilidad

| Tipo | Contrato de esta entrega |
|---|---|
| Recibe | C01 captura/canales, C02 kernel, C04 evidencia, C06 playbook snapshot; SSE beta existente. |
| Produce | C17 SuggestResult/checklist/overlay state; adaptadores unificados y pillReducer. |
| Dependencias de código | [F01](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/01-f01-captura-desktop.md), [F0-F0.1](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/03-f0-f0.1-inteligencia-y-jobs.md), [F08](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/04-f08-playbooks.md) |
| Migración propia | Sin nueva migración; estado final usa intelligence.playbook_observations/C04 y snapshot de captura. |
| No le corresponde | Solo meetings para nueva asistencia; no nueva ventana ni STT; no tratar SuggestionCard React como componente transportable a vanilla. |

La posición en la cola no convierte todas las entregas anteriores en dependencias técnicas. Los contratos nombrados aquí deben existir y tener evidencia de aceptación antes de ejecutar tareas que los consuman. Una dependencia suspendida solo permite avanzar si la parte consumida ya está verificada y el coordinador lo documenta.

## Restricciones globales aplicables

- «Una feature a la vez, hasta el final, antes de pasar a la siguiente».

- Cada entrega sigue TDD y se valida contra SOLID antes de darse por cerrada — no son sugerencias de estilo, son parte del Definition of Done de cada una.

- Un subagente/sesión por entrega, sin implementación simultánea de features. Los bloqueos externos se registran y permiten preparación de trabajo independiente según §5; nunca cuentan como cierre ni permiten saltar una dependencia incumplida.

- Cada feature cubre ausencia de datos y datos parciales/ambiguos. Todo caso nuevo descubierto durante su implementación se resuelve y prueba en esa entrega, o se registra como bloqueo de producto si exige una decisión que el agente no puede tomar.

- «ICP: empresas con CRM estructurado (HubSpot o Pipedrive) con 2-way email sync nativo».

- «Email vía Gmail directo: no se construye».

- «Composio: no se usa».

- «Detección de tono/emoción real desde transcripción: fuera de scope».

- «Meeting booked ≠ close».

- «Slack/Teams: no se construye».

- «WhatsApp para notificaciones push de equipo: no se construye».

- «Onboarding de playbook: 100% self-serve manual».

- Checklist y nueva asistencia en vivo: **solo meetings**.

- No incorporar bots de reuniones, fuentes nuevas de captura, roleplay, leaderboards ni dashboards personalizables por chat.

- No introducir datos ficticios en producción.

- La UI debe mostrar primero el motivo o la acción útil; detalles, puntuaciones y configuración aparecen al ampliar o una forma de descubrirlo más.

- Todo contenido generado debe ser breve, específico y respaldado por información disponible.

- Todo componente del kernel de UI compartido (`shared/ui/`) hereda las reglas de motion y accesibilidad de [copilot-spine-design.md §2.3 y §7](/Users/danizal/getvocify/docs/superpowers/specs/2026-09-21-copilot-spine-design.md:36): no se repiten por feature, se cumplen por construcción. La carga reserva el espacio del componente final; los cambios de altura se animan con medidas reales; `prefers-reduced-motion` elimina movimiento y conserva solo opacidad; el texto mantiene contraste ≥4.5:1 y cada control tiene foco visible. También se heredan los objetivos de interacción, regiones de estado e idioma definidos en §7. Esta restricción incluye F02, F05, F06, F09 y F12, y se verifica al integrar el kernel en cada superficie.

## Especificación funcional conservada

Este bloque conserva la especificación y los criterios aprobados para planificar. Las tareas posteriores la concretan; no eliminan estados de UI, restricciones ni decisiones pendientes. Las referencias §2–§6 que aparezcan en el bloque remiten al plan maestro. Las citas al repo hermano son auditoría; los cambios futuros del desktop se realizan en el monorepo tras F01.

## Feature: F12 — Checklist y tarjeta de ayuda en meetings

**Fuente:** A §4.7–4.8; S §6.2; copiloto existente de agosto.  

**Prioridad:** V1.

### En una frase

Durante un meeting, los pasos del proceso se marcan automáticamente y el comercial puede activar ayuda breve basada en su playbook.

### Por qué (first principles)

Permite mantener el proceso sin añadir tareas manuales durante la conversación. La ayuda debe aparecer solo cuando tenga respaldo y el usuario quiera utilizarla.

### Qué ya existe (auditoría)

- Transcripción en vivo y canales rep/prospect.

- Endpoint SSE de sugerencias.

- [ObjectionCopilotPage.tsx](/Users/danizal/getvocify/src/pages/dashboard/ObjectionCopilotPage.tsx:1) es un módulo funcional de 255 líneas: integra los hooks `useObjectionSuggestions`, `useTurnDetector` y `useRealtimeTranscription`, controles, sugerencias y enrolamiento de voz. Sus hooks contienen estado y efectos ligados a React; el renderer vanilla de Electron no puede consumirlos directamente.

- La extensión ya tiene lógica de turnos y parsing SSE en [turn-detector.js](/Users/danizal/getvocify/chrome-extension/lib/turn-detector.js:1) y [copilot-sse.js](/Users/danizal/getvocify/chrome-extension/lib/copilot-sse.js:1). Se contrastan con sus equivalentes React al extraer el núcleo compartido, conservando los comportamientos existentes y sus pruebas.

- El desktop ya dispone de overlay flotante, controles Stop/volver y puente `shell:state` → `overlay:state`; véase la auditoría de superficies de §2. Su puente `saas:request` actual utiliza `proxyJsonRequest`, por lo que todavía no proporciona transporte de eventos SSE.

- Máquina de estados `pillReducer` diseñada.

- Playbook y captura identificada serán aportados por F08 y F01 antes de esta entrega; no son capacidades ya completas del copiloto beta.

- Gap real: extraer lógica reutilizable, adaptar los hosts React/Electron y su transporte, integrar el meeting y el overlay existentes, y añadir checklist y respaldo comprobable. El coste incluye regresión de la beta, cancelación, limpieza de suscripciones y descarte de respuestas tardías; no se estima como un simple traslado de `SuggestionCard`.

### Backend

- Extender el endpoint de sugerencias con `capture_id` y tipología.

- Mantener el contrato SSE consumido por la beta al añadir los campos del meeting. Las peticiones antiguas sin `capture_id` conservan su contrato; nunca se utilizan para dar por validado el respaldo de F12. Añadir pruebas de compatibilidad para el consumidor React y para los eventos que recibirá Electron. El checklist y la validación del respaldo siguen siendo trabajo nuevo de backend, aunque la beta ya genere sugerencias.

- Resolver empresa y playbook desde la sesión; no aceptar del cliente una afirmación de que la respuesta está respaldada.

- Añadir `grounded`, `source_label`, `source_id` y versión del playbook al resultado.

- `grounded=true` solo si el servidor ha localizado y validado una entrada activa o un patrón expresamente validado.

- En V1, el playbook publicado proporciona respaldo suficiente. No inventar un umbral automático de «patrón ganador».

- Añadir `POST /api/v1/copilot/checklist`:

  - Entrada: captura, revisión, nuevos turnos finalizados.

  - Salida: pasos observados con evidencia.

- La interpretación de turnos pasa por el dominio de extracción; checklist y scoring consumen sus observaciones.

- Los pasos se identifican por el playbook fijado al comenzar.

- Guardar el resultado final con la captura; el análisis posterior puede corregirlo conservando la distinción entre observación en vivo y evaluación final.

**SOLID:** extracción detecta evidencia; checklist registra progreso; generador propone respuesta; controlador cliente decide visibilidad.

### Frontend / Dashboard

- **Decisión de reutilización:** conservar la página beta y sus componentes como host React, y convertir `useTurnDetector` y `useObjectionSuggestions` en adaptadores de la lógica compartida. Extraer a `/Users/danizal/getvocify/shared/ui/copilot/turn-detector.js` las reglas de turnos, a `sse.js` el parsing de eventos y a `suggestion-state.js` las transiciones de solicitud, deduplicación y descarte por captura/revisión. Estos módulos no abren micrófonos, conexiones ni ventanas; los hosts gestionan los efectos. El transporte web permanece en `/Users/danizal/getvocify/src/features/copilot/api/suggest.ts`. La distribución sigue `scripts/sync-shared.mjs` de PF.

- Adaptar los hooks en `/Users/danizal/getvocify/src/features/copilot/hooks/` y los módulos equivalentes de la extensión a ese núcleo, preservando las pruebas y el comportamiento actual. Esto elimina duplicación técnica sin ampliar la asistencia de cold calling. `useRealtimeTranscription` sigue siendo el adaptador de captura de React; en el meeting desktop se consumen los turnos de su captura existente, sin iniciar otro micrófono ni otra sesión de transcripción para el copiloto.

- Crear el adaptador de sesión del desktop en `/Users/danizal/getvocify/desktop/renderer/copilot.js`, conectado desde `/Users/danizal/getvocify/desktop/renderer/app.js`: entrega turnos con identidad de captura, solicita ayuda y checklist, cancela al detener/cambiar meeting y publica el estado para el overlay. El overlay renderiza ese estado; no realiza una segunda solicitud de sugerencias.

- Añadir transporte SSE autenticado y cancelable mediante `/Users/danizal/getvocify/desktop/electron-main.mjs` y `/Users/danizal/getvocify/desktop/preload.cjs`, con identificador de solicitud y limpieza al cerrar la sesión. Mantener la restricción existente de hosts API y enviar los eventos solo al renderer solicitante. No enviar SSE a través del proxy JSON actual. Es trabajo de integración explícito, además del endpoint backend.

- Reutilizar `<v-pill-suggestion>` y `pillReducer` en el overlay existente, adaptando `renderer/overlay.html` y `overlay.js` del desktop importado. Además de Live/Idle, puede mostrar una sugerencia respaldada y un resumen compacto del checklist de la reunión actual; el detalle completo queda accesible al volver a la principal. El comercial puede recibir ayuda y ver progreso sin mantener abierta la app completa.

- **Contrato de overlay — A6:** ampliar el estado existente con `capture_id`, revisión, ayuda activada, sugerencia (`grounded`, texto, fuente y categoría) y progreso de checklist (pasos observados/aplicables y evidencia). Reutilizar `shell:state` → `overlay:state`, `showOverlay()` y `hideOverlay()`. El renderer ignora revisiones de otra captura y limpia sugerencias/evidencias al detener; una última línea antigua no permanece como estado de la nueva sesión.

- Mostrar la tarjeta de sugerencia solo con `grounded=true` validado por backend. El progreso solo marca pasos respaldados por evidencia de esa captura y versión de playbook; no reutilizar el booleano de una sugerencia como prueba de todos los pasos. Sin respaldo o playbook, conservar controles Live/Idle/Stop y ocultar la ayuda no disponible, sin fabricar un checklist completado.

- Diseñar dos alturas acotadas del overlay: estado de captura y estado con ayuda/progreso. Medir y comunicar al proceso principal la altura necesaria, manteniendo ancho y posición dentro del área visible; `resizable: false` impide el redimensionado manual, no obliga a recortar contenido. Aplicar el contrato de motion sin robar foco a Zoom/Meet y mantener el botón Stop accesible.

- La asistencia se activa voluntariamente para la reunión. El checklist no exige clics para marcar pasos.

- Conservar los tiempos de S: mínimo 4 segundos, máximo 10 y 60 de espera entre repeticiones de categoría.

- Convertir el formato SSE existente al formato del controlador; no renombrar silenciosamente la API antigua.

- Una sola pastilla de ayuda, alojada en la ventana flotante que Electron ya tiene. No crear otra ventana de asistencia ni duplicar la sugerencia como popup en la principal. Esta precisión resuelve la contradicción de «no una segunda ventana» con la arquitectura real del desktop.

- No mostrar tokens parciales antes de validar el resultado respaldado.

- Sugerencia de una línea, hasta 90 caracteres.

- No ampliar esta funcionalidad a cold calling.

### Criterio de aceptación (Definition of Done)

- [ ] Los pasos se marcan por evidencia, no por hablar durante cierto tiempo.

- [ ] Sin playbook o respaldo, la tarjeta permanece silenciosa.

- [ ] La ayuda está desactivable.

- [ ] Se respetan duración mínima, retirada y espera por categoría.

- [ ] La intervención del comercial evita que la tarjeta siga molestando.

- [ ] Cancelar o cambiar de meeting descarta respuestas pendientes del anterior.

- [ ] La beta conserva escucha, detección de turnos, sugerencia manual y enrolamiento al consumir el núcleo compartido. Sus pruebas de regresión cubren el contrato SSE antiguo y la cancelación.

- [ ] Una captura desktop utiliza una sola sesión de transcripción y una sola solicitud activa de sugerencias; el overlay no duplica procesamiento. Detener/cambiar meeting limpia listeners y cancela el stream; un resultado antiguo no aparece en la nueva captura.

- [ ] La sugerencia aparece en el overlay existente con la ventana principal minimizada y en fullscreen; Stop y volver a la principal siguen funcionando. La configuración estática de Electron no sustituye esta comprobación nativa.

- [ ] El flujo real desktop queda verificado, no solo la página beta.

- [ ] Con la principal minimizada, el overlay muestra sugerencia respaldada y progreso con evidencia; sin respaldo mantiene solo el estado útil de captura. No hay una nueva ventana ni dos tarjetas de sugerencia.

- [ ] Pasar entre Live/Idle y ayuda no recorta contenido, roba foco ni conserva evidencia de otra reunión. Stop y doble clic para volver mantienen su comportamiento.

### Riesgos / edge cases conocidos

Canal desconocido, respuesta tardía, reconexión y correcciones de transcripción. No añadir inferencia de emoción ni forzar consejo cuando no existe una objeción clara.

## Mapa de archivos y responsabilidades

| Acción futura | Ruta | Responsabilidad |
|---|---|
| Modificar | `/Users/danizal/getvocify/backend/app/api/copilot.py` | Backward compatible SSE y checklist. |
| Modificar | `/Users/danizal/getvocify/backend/app/services/copilot/suggest.py` | Grounding servidor. |
| Crear | `/Users/danizal/getvocify/backend/app/services/intelligence/live_observations.py` | Observación de pasos en dominio extracción. |
| Crear | `/Users/danizal/getvocify/backend/tests/copilot/test_live_meetings.py` | Grounding/checklist/compatibilidad. |
| Crear | `/Users/danizal/getvocify/shared/ui/copilot/turn-detector.js` | Lógica pura consolidada. |
| Crear | `/Users/danizal/getvocify/shared/ui/copilot/sse.js` | Parser SSE compartido. |
| Crear | `/Users/danizal/getvocify/shared/ui/copilot/suggestion-state.js` | Revisión/dedup/solicitudes. |
| Crear | `/Users/danizal/getvocify/shared/ui/pill.js` | Visibilidad/timing S. |
| Crear | `/Users/danizal/getvocify/shared/ui/pill.test.js` | Tiempos deterministas. |
| Modificar | `/Users/danizal/getvocify/src/features/copilot/hooks/useTurnDetector.ts` | Adapter React. |
| Modificar | `/Users/danizal/getvocify/src/features/copilot/hooks/useObjectionSuggestions.ts` | Adapter requests. |
| Modificar | `/Users/danizal/getvocify/src/features/copilot/api/suggest.ts` | Transporte web. |
| Crear | `/Users/danizal/getvocify/desktop/renderer/copilot.js` | Sesión de meeting. |
| Modificar | `/Users/danizal/getvocify/desktop/electron-main.mjs` | SSE IPC scoped/cancelable y tamaño overlay. |
| Modificar | `/Users/danizal/getvocify/desktop/preload.cjs` | Bridge limitado. |
| Modificar | `/Users/danizal/getvocify/desktop/renderer/overlay.js` | Render estado actual. |
| Modificar | `/Users/danizal/getvocify/desktop/renderer/overlay.html` | Ayuda/progreso y controles. |

Los archivos marcados «Crear» todavía no existen por esta planificación. Los marcados «Modificar» pueden ser producidos por una dependencia; su procedencia debe quedar indicada. Los tests y fixtures se crean en ejecución, nunca se confunden con datos de producción.

## Tareas secuenciales con ciclo TDD

Cada tarea termina con evidencia revisable. Los ejemplos de contrato y prueba fijan entradas/salidas futuras; no se han ejecutado ahora. Dividir los pasos de implementación en cambios pequeños dentro del mismo ciclo rojo → verde → revisión. No iniciar otra feature para esquivar un fallo.

### F12.01 — Extraer núcleo compartido con regresión de beta

**Archivos:** shared/ui/copilot/; hooks React; chrome-extension/lib/turn-detector.js y copilot-sse.js como adapters.

**Interfaz y propiedad:** C17 preserves beta defaults; turn detector y parser no conocen React/window/auth.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"capture_id":"memo-1","input_revision":"live-7","request_id":"sug-3","event":"result"}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Mismo transcript en React/vanilla | Mismos límites de turno. |
| Evento SSE dividido entre chunks | Un evento completo solo al cerrar frame. |
| Cambio sesión/cancel | Respuesta vieja descartada. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `node --test shared/ui/copilot/*.test.js shared/ui/pill.test.js` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Caracterizar hooks y módulos extensión existentes antes de mover lógica; pruebas comparten fixtures.

- [ ] Extraer lógica pura, conectar adapters y conservar controls/voice enrollment beta sin otra captura.

- [ ] Incluir subdirectorio copilot en discovery de tests: Makefile debe ejecutar esos tests, no solo shared/ui/*.test.js.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `node --test shared/ui/copilot/*.test.js shared/ui/pill.test.js` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Beta/extension comportamientos equivalentes y nuevas reglas no amplían cold calling.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F12.01`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F12.02 — Añadir grounding y observación de pasos en backend

**Archivos:** api/copilot.py, suggest.py, intelligence/live_observations.py; test_live_meetings.py.

**Interfaz y propiedad:** C17 campos nuevos opcionales para beta; F12 exige capture_id accesible + snapshot. Checklist tiene evidencia propia, no hereda grounded del consejo.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"type":"result","capture_id":"memo-1","input_revision":"live-7","grounded":true,"source_id":"entry-2","source_label":"Playbook discovery","playbook_version_id":"pv-2","suggestion":{"isObjection":true,"category":"price","text":"¿Qué coste tiene mantener el proceso actual?"}}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Sin entrada de playbook | grounded false y tarjeta invisible. |
| Cliente dice grounded true | Ignorado; servidor valida fuente. |
| Paso observado con fuente de otra captura | Rechazo. |
| Beta sin capture_id | Contrato antiguo sigue funcionando, no prueba grounding F12. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/copilot/test_live_meetings.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Resolver empresa/captura y versión fija desde servidor; no aceptar product_context del cliente como evidencia autoritativa.

- [ ] Añadir source_id/source_label/playbook_version_id al resultado final y validarlo antes de mostrar.

- [ ] Observar turnos finalizados mediante extracción live; guardar pasos+evidencia por revisión, dedup por turno y permitir corrección posterior con marca live/final.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/copilot/test_live_meetings.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: No token parcial mostrado como recomendación validada; contrato legacy pasa.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F12.02`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F12.03 — Conectar SSE nativo y un único dueño de sesión

**Archivos:** desktop/electron-main.mjs/preload.cjs/renderer/copilot.js; desktop/lib/copilot-session.test.js nuevo.

**Interfaz y propiedad:** C17 request_id/cancel; proceso main mantiene fetch SSE por renderer; app renderer coordina; overlay no solicita LLM.

**Ejemplo concreto de contrato o prueba a incorporar:**

```text
app renderer -> startSSE(request_id) -> main fetch
main -> events(request_id) -> app state -> overlay:state
stop/cambio -> cancel(request_id) -> abort + unsubscribe
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Cerrar renderer o meeting | Abort del stream y limpieza listeners. |
| API host no permitido | Rechazado antes de fetch. |
| Main minimizada | Captura y sesión siguen, overlay actualiza. |
| Respuesta vieja | No aparece en nueva captura. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd desktop && node --test lib/copilot-session.test.js` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Añadir bridge SSE separado de proxyJsonRequest con eventos dirigidos al emisor y cancelación explícita.

- [ ] Alimentar controlador desde turnos de la captura existente; una sesión STT y máximo una sugerencia activa.

- [ ] Publicar estado limpio vía shell:state y cerrar lifecycle al stop/cambio; preservar audio y captura aunque falle asistencia.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd desktop && node --test lib/copilot-session.test.js` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Cierre/cancel verificados con flujo Electron real y stream de prueba.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F12.03`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F12.04 — Ampliar overlay y respetar visibilidad por contrato

**Archivos:** pill.js; shared components v-pill-suggestion; overlay html/js; desktop/lib/shell tests.

**Interfaz y propiedad:** C17: 4 s mínimo, 10 s máximo, 60 s cooldown; usuario opt-in; checklist con evidencia separado de sugerencia.

**Ejemplo concreto de contrato o prueba a incorporar:**

```js
import assert from 'node:assert/strict';
import { initialPill, pillReducer } from './pill.js';
const s = { isObjection: true, grounded: true, category: 'price', text: 'Aclara el coste actual' };
const shown = pillReducer(initialPill, { type: 'suggestion', suggestion: s, at: 0 });
assert.ok(shown.visible);
assert.equal(pillReducer(shown, { type: 'tick', at: 10000 }).visible, null);
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Sugerencia a 0 s y tick a 10 s | Se retira. |
| rep_speaking antes de 4 s | Respeta mínimo, se retira cuando corresponda. |
| Misma categoría antes de 60 s | No repite. |
| Sin datos/playbook | Live/Idle/Stop, sin ayuda fabricada. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `node --test shared/ui/pill.test.js` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Usar reducer S con adaptación explícita de snake_case API a contrato JS.

- [ ] Añadir progreso compacto y alturas acotadas del overlay existente; resize IPC validado y sin robar foco.

- [ ] Conservar Stop y doble clic; verificar app minimizada/fullscreen y reduced-motion.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `node --test shared/ui/pill.test.js` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Overlay real cumple tiempos, limpieza, evidencia y controles nativos.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F12.04`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

## Verificación integrada y criterios de salida adicionales

Meeting con playbook publicado: activar ayuda, recibir objeción fundamentada, minimizar principal y ver overlay sobre app de reunión. Mostrar paso observado y abrir detalle. Cambiar meeting con stream pendiente: no aparece respuesta anterior. Beta sigue operativa.

### Regresiones y comandos al cerrar

- `cd backend && .venv/bin/python -m pytest tests/copilot/test_live_meetings.py -q`
- `node --test shared/ui/copilot/*.test.js shared/ui/pill.test.js`
- `make test-js`
- `npm run build`
- `make check-generated`

Ejecutar los comandos desde `/Users/danizal/getvocify`, salvo el `cd` explícito. Un directorio de pruebas indicado como nuevo solo estará disponible después de sus tareas; que hoy no exista no autoriza a omitirlo al ejecutar. Las pruebas de IA usan datos reales autorizados y anonimizados; los ejemplos sintéticos de este plan sirven solo para contratos y tests deterministas.

### Qué vuelve al coordinador

- [ ] Informe de `F12` con tarea/criterio → resultado → prueba o veredicto → commit, migración aplicada y contrato entregado.

- [ ] Comparación de interfaces producidas con `00-contracts.md`; ninguna divergencia silenciosa de campos, estados, permisos o semántica de `null`.

- [ ] Revisión SOLID y limpieza de listeners/jobs/efectos; los servicios no duplican interpretación que corresponde a extracción.

- [ ] Evidencia de todos los estados de UI especificados. En web, `reticle_act_and_wait` o `reticle_assert` con consecuencia explícita; en desktop/extensión, además el recorrido nativo. `unknown` y `no-fault` no cierran.

- [ ] Bloqueos y edge cases nuevos en `docs/superpowers/deliveries/F12/report.md` y en el commit/PR. No marcar completa mientras haya criterios pendientes; una suspensión debe nombrar las dependencias no afectadas.

## Handoff a la siguiente entrega

Resultado checklist final entra a C04 con procedencia live y versión; F09/F11 pueden revisar final sin confundir observación provisional con evaluación cerrada. F13/F15 agregan solo la revisión final elegible.
