# F06 — Tareas inteligentes, gesto único y cola: plan ejecutable

> **Ejecución futura:** usar `executing-plans` dentro del subagente dedicado a esta entrega; la coordinación secuencial usa `subagent-driven-development`. Este documento es planificación, no una implementación ni una autorización para desplegar. Ninguna casilla de ejecución está completada.

**Objetivo:** Convertir señales de Hoy en acciones recuperables y una cola de llamadas usable con teclado.

**Arquitectura:** Backend decide transición e idempotencia; reducers deciden cola y animación; hosts ejecutan acciones de llamada/navegación existentes.

**Stack:** FastAPI/Python, Supabase/PostgreSQL, React 18/TypeScript y módulos JS compartidos; Electron/extensión cuando figuren entre las superficies de esta entrega.

**Posición:** 8 de 16. **Estado:** planificada; no iniciada.

**Navegación:** [plan maestro](/Users/danizal/getvocify/proposed_plan.md) · [contratos](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-contracts.md) · [integración y gates](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-integration-and-gates.md)

**Fuentes de esta entrega:** A: [Análisis de producto](/Users/danizal/getvocify/docs/PRODUCT_PLANNING_ANALYSIS_2026-09-21.md) · S: [Diseño Spine](/Users/danizal/getvocify/docs/superpowers/specs/2026-09-21-copilot-spine-design.md) · I: [Integración de superficies](/Users/danizal/getvocify/docs/features/PLAN_INTEGRACION.md).

## Entrada, salida y frontera de responsabilidad

| Tipo | Contrato de esta entrega |
|---|---|
| Recibe | C10 TodayView/Signal.version; C02 UI; marcador existente y screening_outcome. |
| Produce | C11 resolve/undo con expected_version, undo_deadline y estado revisado; queueReducer y v-today-card. |
| Dependencias de código | [F05](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/07-f05-hoy.md) |
| Migración propia | Sin nueva migración; usa campos de acción/undo previstos en 043 de F05. |
| No le corresponde | No interpreta abrir correo como envío; no completa tarea por pulsar Llamar; no depende del brief pendiente F03. |

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

## Feature: F06 — Tareas inteligentes, gesto único y cola

**Fuente:** A §3.3; S §2 y §6.1; I §1.1.  

**Prioridad:** V1.

### En una frase

Cada tarjeta explica por qué actuar y permite llamar, escribir o abrir el registro correspondiente sin volver a buscarlo.

### Por qué (first principles)

Una lista de títulos genéricos añadiría otra bandeja de trabajo. El valor está en reunir contexto, momento y acción.

### Qué ya existe (auditoría)

- Feed F05, marcador y navegación CRM.

- Controlador de cola definido en S.

- Gap real: conexión entre esas piezas, estado de acciones y componentes compartidos.

### Backend

- Extender F05 con:

  - `POST /api/v1/today/{id}/resolve`.

  - `PATCH /api/v1/today/{id}/resolve` para deshacer.

- El POST recibe acción, `request_id`, versión esperada y `until` para aplazamiento.

- Devuelve nueva versión y posibilidad de deshacer durante cinco segundos.

- Una versión concurrente incompatible responde `409` y obliga a refrescar.

- Deshacer restaura el estado de la señal; nunca promete revertir una llamada ni retirar un email.

- Una llamada conectada dispara reconciliación. Abrir el CRM o pulsar «Llamar» no marca por sí solo el compromiso como cumplido.

- Una respuesta por correo solo afecta a recordatorios de silencio cuando el proveedor ha confirmado actividad entrante relevante.

- Abrir `mailto:` no prueba que se haya enviado un follow-up ni inicia una cuenta atrás de «sin respuesta».

**SOLID:** el servicio valida transiciones; la tarjeta emite intención; cada host ejecuta navegación o llamada.

### Frontend / Dashboard

- Crear `<v-today-card>` y su renderizador en `/Users/danizal/getvocify/shared/ui/components/`.

- Reutilizar el kernel y `useVElement`.

- Web/extensión: conectar «Llamar» al marcador existente cuando esté disponible.

- Desktop: abrir el registro o destino disponible; no construir un marcador nuevo.

- Implementar `queueReducer`, `currentItem` y `prefetchTarget` de S.

- Adaptar `call_ended`: buzón/no respuesta salta revisión aunque exista memo.

- Mostrar acciones secundarias como texto o menú; una sola acción principal.

- Foco de teclado y anuncios de posición en cola.

- Sin preparación aprobada, la cola muestra el contexto de la tarjeta; no depende de F03.

#### Salida y restitución de tarjetas — A8

Al resolver, descartar o posponer, medir la altura real de la tarjeta y su espacio antes de retirarla. Animar opacidad y colapso desde esa medida con los tiempos de S §7, y eliminar el nodo al terminar; no usar un `max-height` arbitrario ni permitir que un refetch reconstruya la lista en mitad de la transición. La acción conserva el contrato de versión/idempotencia del backend.

Con `prefers-reduced-motion`, omitir desplazamiento y animación de altura: usar solo opacidad, retirar después el espacio y conservar el foco en la siguiente acción válida. Si era la última tarjeta, el foco pasa al estado vacío o a «Deshacer», sin perderse en el documento. Deshacer restaura la tarjeta con su identidad; un `409` o fallo restaura/refresca el estado verdadero sin hacerla desaparecer definitivamente. La animación no modifica la ventana de cinco segundos de deshacer concedida por el servidor.

Sin tarjetas se hereda el estado vacío de F05. Una tarjeta con teléfono o permisos incompletos mantiene su motivo y ofrece la acción disponible; no se borra por no poder llamar.

### Criterio de aceptación (Definition of Done)

- [x] «Llamar» utiliza el contacto correcto sin búsqueda adicional.

- [x] Posponer, descartar y deshacer sobreviven a una recarga.

- [x] Otra superficie refleja la acción al recuperar foco.

- [x] Buzón/no respuesta avanza sin tratarlo como conversación.

- [x] Una llamada fallida no completa una tarea.

- [x] La cola funciona con teclado.

- [x] Razones cortas, concretas y consistentes en todas las superficies.

- [x] Resolver/descartar/posponer retira la tarjeta con altura medida, sin salto brusco; un refetch concurrente no interrumpe la transición ni duplica nodos.

- [x] En reducción de movimiento solo cambia la opacidad. Deshacer, error y `409` restituyen el estado correcto, y el foco queda en una acción útil incluso al retirar la última tarjeta.

### Riesgos / edge cases conocidos

Teléfono ausente, marcador no configurado, permisos de llamadas y acciones concurrentes. Si no puede llamar, la acción se presenta honestamente como «Abrir en CRM».

## Mapa de archivos y responsabilidades

| Acción futura | Ruta | Responsabilidad |
|---|---|
| Crear | `/Users/danizal/getvocify/backend/app/services/hoy/actions.py` | Transiciones y deshacer. |
| Modificar producido F05 | `/Users/danizal/getvocify/backend/app/api/today.py` | POST/PATCH resolve. |
| Crear | `/Users/danizal/getvocify/backend/tests/hoy/test_actions.py` | Concurrencia e idempotencia. |
| Crear | `/Users/danizal/getvocify/shared/ui/queue.js` | Reducer y foco de cola. |
| Crear | `/Users/danizal/getvocify/shared/ui/queue.test.js` | Screening y navegación. |
| Crear | `/Users/danizal/getvocify/shared/ui/components/today-card.js` | Render puro. |
| Crear | `/Users/danizal/getvocify/shared/ui/components/v-today-card.js` | Elemento/animación con altura real. |
| Modificar | `/Users/danizal/getvocify/shared/ui/vocify-ui.css` | Motion y focus. |
| Modificar producido F05 | `/Users/danizal/getvocify/src/features/today/components/TodayPanel.tsx` | Acciones y cola. |
| Modificar | `/Users/danizal/getvocify/chrome-extension/popup/popup.js` | Conectar dialer existente. |

Los archivos marcados «Crear» todavía no existen por esta planificación. Los marcados «Modificar» pueden ser producidos por una dependencia; su procedencia debe quedar indicada. Los tests y fixtures se crean en ejecución, nunca se confunden con datos de producción.

## Tareas secuenciales con ciclo TDD

Cada tarea termina con evidencia revisable. Los ejemplos de contrato y prueba fijan entradas/salidas futuras; no se han ejecutado ahora. Dividir los pasos de implementación en cambios pequeños dentro del mismo ciclo rojo → verde → revisión. No iniciar otra feature para esquivar un fallo.

### F06.01 — Aplicar transiciones con versión y request_id

**Archivos:** hoy/actions.py, api/today.py, tests/hoy/test_actions.py.

**Interfaz y propiedad:** C11 POST resolve; request_id idempotente. PATCH undo referencia acción y versión, máximo 5 s desde aceptación servidor.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"action":"dismiss","request_id":"act-2","expected_version":3,"until":null}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Doble click mismo request_id | Devuelve misma transición; no cambia deadline. |
| Otra superficie con versión vieja | 409 más versión actual, sin pisar acción. |
| Deshacer después de 5 s | Rechazado; no revierte efectos externos. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/hoy/test_actions.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Persistir estado previo, request_id y deadline en transacción usando campos de 043.

- [ ] Validar acción resolve/dismiss/snooze y fecha until; nunca aceptar author/company del cliente.

- [ ] Undo restaura señal solo si sigue siendo la versión de esa acción; no deshace llamada/email.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/hoy/test_actions.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Concurrencia DB, reloj fijo y expiración exacta comprobados.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F06.01`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F06.02 — Implementar cola que respeta resultado de llamada

**Archivos:** queue.js y queue.test.js; adapters dialer web/extensión.

**Interfaz y propiedad:** C11 call_ended agrega screeningOutcome; memoId por sí solo no implica conversación. API reducer de S se conserva.

**Ejemplo concreto de contrato o prueba a incorporar:**

```js
import assert from 'node:assert/strict';
import { queueReducer } from './queue.js';
const state = { mode: 'calling', items: [{ id: 'a' }, { id: 'b' }], index: 0 };
const next = queueReducer(state, { type: 'call_ended', memoId: 'voicemail-memo', screeningOutcome: 'voicemail' });
assert.equal(next.mode, 'queue');
assert.equal(next.index, 1);
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Buzón con memo | Avanza sin revisión. |
| Conversación con memo | Abre revisión del memo correcto. |
| Call failed | No completa señal; permite acción siguiente sin falso éxito. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `node --test shared/ui/queue.test.js` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Trasladar reducer y keyboard map S corrigiendo su antigua suposición de buzón sin memo.

- [ ] Adaptar estados reales del dialer; resolver acción solo cuando la evidencia permita reconciliar.

- [ ] prefetchTarget solo precarga contexto disponible; no construye F03 por accidente.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `node --test shared/ui/queue.test.js` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Distingue intento/conversación usando screening real.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F06.02`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F06.03 — Integrar tarjetas, animación, deshacer y foco

**Archivos:** today-card.js/v-today-card.js, vocify-ui.css, TodayPanel y hosts; pruebas shared/ui/today-card.test.js nuevas.

**Interfaz y propiedad:** C02 v-action + C11 action response. Transición visual no prolonga undo_deadline.

**Ejemplo concreto de contrato o prueba a incorporar:**

```text
pending(v3) -> dismissed(v4, undo_deadline)
undo(v4) -> pending(v5)
conflicto -> refrescar estado actual, sin borrado definitivo local
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Última tarjeta retirada | Vacío útil y foco conservado. |
| Undo durante salida o refetch | Una tarjeta con identidad estable. |
| Reduced motion | Solo opacidad, sin desplazamiento/altura animada. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `node --test shared/ui/today-card.test.js shared/ui/queue.test.js` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Medir altura antes de salida; retener nodo hasta transición y reconciliar por ID.

- [ ] Mostrar undo hasta deadline servidor; on409 restaurar/refrescar verdad sin duplicar nodo.

- [ ] Conectar acción principal real y fallback Abrir CRM cuando no haya teléfono/permiso.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `node --test shared/ui/today-card.test.js shared/ui/queue.test.js` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Reticle y hosts nativos prueban teclado, undo/error/refetch y foco.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F06.03`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

## Verificación integrada y criterios de salida adicionales

Empezar cola, llamar y recibir buzón con memo; comprobar avance sin revisión. Después conversación real y revisión. Posponer/descartar desde una superficie, recuperar foco en otra y deshacer dentro/fuera del plazo; retirar última tarjeta con teclado.

### Regresiones y comandos al cerrar

- `cd backend && .venv/bin/python -m pytest tests/hoy -q`
- `node --test shared/ui/queue.test.js shared/ui/today-card.test.js`
- `make test-js`
- `npm run build`
- `make check-generated`

Ejecutar los comandos desde `/Users/danizal/getvocify`, salvo el `cd` explícito. Un directorio de pruebas indicado como nuevo solo estará disponible después de sus tareas; que hoy no exista no autoriza a omitirlo al ejecutar. Las pruebas de IA usan datos reales autorizados y anonimizados; los ejemplos sintéticos de este plan sirven solo para contratos y tests deterministas.

### Qué vuelve al coordinador

- [ ] Informe de `F06` con tarea/criterio → resultado → prueba o veredicto → commit, migración aplicada y contrato entregado.

- [ ] Comparación de interfaces producidas con `00-contracts.md`; ninguna divergencia silenciosa de campos, estados, permisos o semántica de `null`.

- [ ] Revisión SOLID y limpieza de listeners/jobs/efectos; los servicios no duplican interpretación que corresponde a extracción.

- [ ] Evidencia de todos los estados de UI especificados. En web, `reticle_act_and_wait` o `reticle_assert` con consecuencia explícita; en desktop/extensión, además el recorrido nativo. `unknown` y `no-fault` no cierran.

- [ ] Bloqueos y edge cases nuevos en `docs/superpowers/deliveries/F06/report.md` y en el commit/PR. No marcar completa mientras haya criterios pendientes; una suspensión debe nombrar las dependencias no afectadas.

## Handoff a la siguiente entrega

F03, si se aprueba, puede enriquecer la tarjeta con brief; no altera reducer ni contrato de acciones. Reporting consumirá acciones/actividad reales, no clics como resultados.

### Addendum E2 — Tareas del CRM desde los compromisos de C04 (26 sep 2026)

**Motivo:** «Te llamo el jueves» tiene que ser lo mismo en el CRM y en Hoy. Las tareas del CRM salían de `nextSteps` (texto libre de la extracción, fecha por heurística) y Hoy sale de los `commitments` de C04. Podían no coincidir ni en el texto ni en la fecha.

**Flag:** `COMMITMENT_TASKS_ENABLED`, por empresa con `feature_flags.is_enabled` (sin fila, manda el global de `config.py`, apagado). Apagado: filas de revisión y tareas salen de `nextSteps` exactamente como antes.

**Cuándo mandan los compromisos:** flag encendido y C04 vigente en el memo (`intelligence.extract.is_current`: mismo `prompt_version` e `input_revision`). Sin C04 vigente (memo sin inteligencia, de otra revisión, de un prompt anterior, o ya aprobado tras revisión), `nextSteps` como antes. Con C04 vigente y ningún compromiso, no hay filas de tarea: C04 no encontró acciones y `nextSteps` no las suple.

**Qué compromisos:** los que tiene que hacer el comercial. En C04 los dos `origin` ya son acciones del comercial: `rep_promise` (lo prometió él) y `prospect_request` (el prospecto le pidió que lo hiciera); Hoy los lee igual («Le prometiste…», «Te pidió…»). Lo que el prospecto dice que hará él mismo («te llamo yo», «te paso el contrato») no es un compromiso: no tiene `origin` posible y el caso de eval `c04_prospect_calls_back_is_not_a_rep_commitment` lo vigila. Paso 0 encontró uno real mal etiquetado como `rep_promise`: si el modelo se equivoca así, esa acción acaba como tarea del comercial.

**Texto:** el `text` del compromiso, con la primera letra en mayúscula (solo presentación).

**Fecha**, según la precisión que ya guarda C04 (`temporal_precision`):

| Precisión C04 | Fecha de la tarea |
|---|---|
| `time` | Esa hora (`due_at`, con su zona). |
| `date` | Ese día a las 9:00 en la zona del comercial: la de Hoy (preferencia del usuario, por defecto `Europe/Madrid`). |
| `unknown` (`due_at` null) | Sin fecha. HubSpot exige `hs_timestamp`: se escribe el valor por defecto de siempre (+3 días, 9:00) y la fila de revisión va sin fecha, como ya pasaba con un `nextStep` sin fecha. Pipedrive: actividad sin `due_date`. |

C04 conserva ahora los compromisos sin día (`due_at: null`, `temporal_precision: "unknown"`), como ya decía el contrato (`00-contracts.md`: `due_at nullable`). Antes se descartaban. El prompt pasa a `intelligence_v3` (`intelligence_v2.md` no se toca; un prompt publicado nunca se edita) con tres líneas más por fallos reales de Paso 0: con etiquetas genéricas («SPEAKER: S1») el comercial es quien vende y una nota de un solo hablante es el comercial dictando; una reunión acordada no sustituye las otras acciones («el lunes te llamo para confirmar»); «en dos semanas» es un día (captured_at más ese plazo). Los memos con C04 de `intelligence_v2` dejan de estar vigentes: con el flag encendido vuelven a `nextSteps` (Hoy, Ask y el resto no miran la versión y siguen leyendo su C04). Los compromisos sin día: Hoy los sigue ignorando porque no vencen. Un `due_at` mal formado (sin zona, día imposible, texto libre) se sigue descartando.

**Revisión (filas `next_step_task_i`):** una fila por compromiso, en el orden de C04, con `due_date` = día de la tarea y `commitment_id`. En HubSpot y Pipedrive. La extensión toma de esas filas el número de tareas y sus fechas; sin filas con `commitment_id`, las filas de siempre.

**Aprobación:**
- Sin revisión (auto-aprobación, WhatsApp, Ask): se escriben todos los compromisos.
- Un C04 vigente sin compromisos es el modo antiguo, igual que sin C04: filas y tareas de `nextSteps`.
- Con revisión: una fila cuyo texto es el de un compromiso (sin distinguir mayúsculas ni espacios) es ese compromiso, con su fecha y su `crm_task_id`. Las filas se emparejan en orden y cada compromiso se usa una vez: con dos compromisos de texto idéntico y una sola fila, esa fila es el primero en el orden de C04. Un compromiso sin fila lo quitó el comercial: no se crea. Una fila editada o añadida se escribe como un `nextStep` de siempre.
- `raw_extraction.nextStepSchedules`: una fila que es un compromiso nunca lo usa (el dashboard reenvía las fechas antiguas sin tocarlas). Una fila editada o añadida conserva la fecha de su posición, como con el flag apagado; en la extensión es la fecha de esa fila.
- Resultado de la llamada «en espera»: el seguimiento toma el día del compromiso conservado con fecha más temprana, el lugar que ocupaba la primera fecha de `nextSteps`. Sin ninguno con fecha, lo de siempre.
- HubSpot: con compromisos no se usa la fusión con las tareas del deal (reescribe texto y fecha). Una tarea ya asociada es la del compromiso solo si no está completada (`hs_task_status`), tiene el mismo asunto y vence el mismo día (en la zona de la fecha del compromiso; sin día, el valor por defecto que se escribiría). Entonces no se duplica y su id queda en el compromiso, así un reintento tras un fallo a medias vuelve a enlazar. Si no, se crea otra. Dos compromisos de texto idéntico con días distintos son dos tareas. La idempotencia de reintentos (`crm_updates.create_tasks`) es la de siempre.
- Pipedrive: `due_date` y `due_time` en UTC, como pide su API.
- Salesforce: fuera de este modo (no tiene escritura de tareas). Con el flag encendido, revisión y sync son los de siempre.

**Vínculo con Hoy:** al aprobar, cada tarea creada deja su id en su compromiso (`extraction.intelligence.commitments[i].crm_task_id`). Sin migración: el memo es la Interaction. Hoy lo usa según el addendum E2 de `07-f05-hoy.md`.

**Casos que deben fallar antes de implementar:**

| Caso | Resultado exigido |
|---|---|
| Compromiso con hora | Tarea a esa hora. |
| Compromiso solo con día | Tarea ese día a las 9:00 en la zona del comercial (Madrid por defecto; la suya si la tiene). |
| Compromiso sin día | Fila sin fecha; Pipedrive sin `due_date`; HubSpot con el valor por defecto de siempre. |
| `rep_promise` y `prospect_request` | Los dos generan tarea. |
| Flag apagado | Filas y tareas de `nextSteps`, idénticas a antes. |
| Memo sin C04 o con C04 no vigente | Filas y tareas de `nextSteps`. |
| C04 vigente sin compromisos | Modo antiguo: siguientes pasos como hoy. |
| El comercial quita una fila | Esa tarea no se crea; las demás sí, con su fecha. |
| El comercial edita el texto de una fila | Se crea con su texto, como un `nextStep`. |
| Revisión del dashboard: textos intactos, `nextStepSchedules` antiguos | Los compromisos se crean con su fecha, no con la antigua. |
| Revisión de la extensión | Filas y fechas de los compromisos; se crean todos los conservados. |
| Aprobación sin revisión | Se escriben todos los compromisos. |
| HubSpot y Pipedrive | Construyen las filas desde los compromisos. |
| Salesforce con el flag encendido | Revisión y sync como antes. |
| Memo con C04 de un prompt anterior | Filas y tareas de `nextSteps`. |
| HubSpot, deal existente con tareas | Sin fusión; una tarea abierta con el mismo asunto y el mismo día se enlaza, no se duplica. |
| HubSpot, tarea con el mismo asunto completada u otro día | Se crea una tarea nueva. |
| HubSpot, dos compromisos de texto idéntico con días distintos | Dos tareas, dos ids. |
| Dos compromisos de texto idéntico, el comercial quita una fila | Se conserva el primero en el orden de C04, con su fecha. |
| La extensión corrige una errata en una fila | Se crea como `nextStep` con la fecha de esa fila. |
| Resultado «en espera» con compromisos | Seguimiento el día del compromiso con fecha más temprana. |
| Pipedrive con hora | `due_date`/`due_time` en UTC. |
| Tarea creada | Su id queda en el compromiso (`crm_task_id`). |
| C04 con compromiso sin día | Se conserva con `due_at` null; uno mal formado se descarta. |

### Addendum E7 — confirmación de un clic (26 sep 2026)

Tras una autoaprobación del CRM (`auto_sync_hubspot_calls`), si queda una etapa sugerida distinta de la actual (con `DEAL_STAGE_CONFIRM_ENABLED`) o una propuesta de reunión acordada sin aceptar, Hoy materializa una señal `type: confirm_pending` (una por memo, `dedupe_key: confirm:{memo_id}`). Flag `HOY_CONFIRMATIONS_ENABLED` por empresa; apagado: no se materializa y `POST /today/{id}/resolve` con `action: confirm` responde 404.

`POST /today/{id}/resolve` acepta `action: confirm` solo en señales `confirm_pending`. Marca la señal como `resolved` con ventana de deshacer de 5 s (F06). La escritura en el CRM (etapa vía `write_confirmed_stage`, reunión vía `accept_meeting_proposal`) se aplaza hasta que venza el plazo de deshacer; deshacer solo reabre la señal. Dos confirmaciones idempotentes escriben una vez (`write_applied` en el payload).

| Caso | Comportamiento esperado |
|---|---|
| Autoaprobación, etapa sugerida distinta | Señal `confirm_pending` |
| Etapa igual a la actual | Sin señal |
| Reunión acordada sin aceptar | Señal |
| Reunión aceptada u omitida | Sin señal |
| Etapa + reunión | Una señal con las dos partes en `reason`/`detail` |
| Sin autoaprobación | Sin señal nueva |
| `confirm` escribe etapa y reunión como la revisión | Una sola escritura por parte |
| Deshacer dentro de 5 s | Señal `pending`; sin escritura CRM |
| `confirm` en otra señal | 422 |
| Flag apagado | Sin señal; `confirm` → 404 |
| Hecho hoy | Fila `kind: confirmation` |
