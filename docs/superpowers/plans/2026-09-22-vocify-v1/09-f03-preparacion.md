# F03 — Preparación de llamada o meeting: plan ejecutable

> **Ejecución futura:** usar `executing-plans` dentro del subagente dedicado a esta entrega; la coordinación secuencial usa `subagent-driven-development`. Este documento es planificación, no una implementación ni una autorización para desplegar. Ninguna casilla de ejecución está completada.

**Objetivo:** Precisar e implementar solo tras aprobación la preparación previa sobre contacto HubSpot como acceso principal.

**Arquitectura:** Agregación de lectura sin LLM nuevo; componente shared único, hosts obtienen identidad y descartan respuestas obsoletas.

**Stack:** FastAPI/Python, Supabase/PostgreSQL, React 18/TypeScript y módulos JS compartidos; Electron/extensión cuando figuren entre las superficies de esta entrega.

**Posición:** 9 de 16. **Estado:** bloqueada para implementación hasta aprobar formato y ubicación.

**Navegación:** [plan maestro](/Users/danizal/getvocify/proposed_plan.md) · [contratos](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-contracts.md) · [integración y gates](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-integration-and-gates.md)

**Fuentes de esta entrega:** P: [Prompt técnico](/Users/danizal/getvocify/docs/TECHNICAL_PLANNING_PROMPT_VOCIFY_V1.md) · A: [Análisis de producto](/Users/danizal/getvocify/docs/PRODUCT_PLANNING_ANALYSIS_2026-09-21.md) · I: [Integración de superficies](/Users/danizal/getvocify/docs/features/PLAN_INTEGRACION.md).

## Entrada, salida y frontera de responsabilidad

| Tipo | Contrato de esta entrega |
|---|---|
| Recibe | C04 evidencia, C06 playbook, C08 contexto, C10 tarjetas; aprobación explícita de formato/ubicación. |
| Produce | C12 PreparationBrief y v-brief; screen-contact con independencia de captura. |
| Dependencias de código | [F05](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/07-f05-hoy.md), [F08](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/04-f08-playbooks.md), [F07](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/05-f07-ask-vocify.md) |
| Migración propia | Ninguna; cache por revisión, no tabla nueva. |
| No le corresponde | No ejecutar ninguna tarea de UI/API hasta aprobación; no convertir en dependencia F06/F10. No nueva captura ni panel inyectado en HubSpot. |

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

## Feature: F03 — Preparación de llamada o meeting

**Fuente:** A §3; I §2.4 y §3.3; P §7.  

**Prioridad:** V1, **propuesta pendiente de aprobación**.

### En una frase

Antes de hablar con un contacto, el comercial puede revisar en segundos lo último que ocurrió y lo que quedó pendiente.

### Por qué (first principles)

Elimina la búsqueda previa en notas y tareas. Debe ser suficientemente breve para utilizarse antes de una llamada real.

### Qué ya existe (auditoría)

- Resumen y próximos pasos.

- Señales de «Hoy».

- Playbooks y contexto CRM.

- El diseño anterior propone cuatro filas, pero has pedido mantenerlo sin aprobar.

### Backend

**Contrato propuesto, no autorizado para implementación:**

- `/Users/danizal/getvocify/backend/app/services/briefs/preparation.py`.

- `GET /api/v1/briefs?connection_id=&contact_id=&deal_id=`.

- Devuelve hasta cuatro bloques:

  - Última vez.

  - Quedó pendiente.

  - Objeción abierta.

  - Respuesta aplicable del playbook.

- Cada bloque incluye referencia al memo, tarea o regla de origen.

- Sin una nueva llamada al LLM: reutiliza resúmenes, evidencia y plantillas.

- Sin nueva tabla; caché identificada por revisión de las fuentes.

**SOLID:** agregación de lectura independiente del scoring y del brief posterior.

### Frontend / Dashboard

- **Propuesta de superficie primaria — A3:** `<v-brief>` en la extensión al abrirla sobre la página de un contacto de HubSpot, antes de iniciar la llamada y sin exigir una captura activa. Es el acceso principal a validar con Dani junto con el formato; dashboard, marcador y home desktop son accesos secundarios al mismo contenido.

- `usePreparationBrief`.

- Prefetch del siguiente contacto durante la cola.

- No añadir una página ni notificaciones de calendario.

- Copy: «Quedó pendiente: enviar el caso de logística».

#### Entrada desde el contacto y estados propuestos

Si Dani aprueba F03, añadir `screen-contact` en `/Users/danizal/getvocify/chrome-extension/popup/index.html` e integrar su selección en `popup.js`; gestionar la identidad activa mediante `background.js` y el parser CRM existente. La pantalla muestra nombre del contacto, procedencia, `<v-brief>` y la acción existente de llamada. No inyectar un nuevo panel en HubSpot ni crear otra captura para obtener contexto.

- Abrir la extensión sobre un contacto y sin sesión de llamada/revisión activa lleva a `screen-contact`. Iniciar llamada conserva los estados existentes. Una captura o revisión pendiente tiene prioridad y conserva su contacto de origen, aunque el usuario navegue por otra pestaña.
- Cambiar de contacto cancela/descarta la lectura anterior y muestra carga del nuevo. La clave incluye usuario, empresa, conexión, contacto, deal y revisión; nunca reutilizar el brief de A mientras carga B. Un deal ambiguo exige selección contextual y no combina compromisos incompatibles.
- Sin página de contacto compatible: «Abre un contacto en HubSpot para ver su contexto». Sin sesión de Vocify: login. Esta propuesta prioriza HubSpot y no anuncia una integración de preparación Pipedrive sin verificarla.

| Información disponible | Qué se muestra |
|---|---|
| Interacciones Vocify con evidencia | Hasta cuatro filas del formato propuesto, con origen y fecha accesibles al ampliar. |
| Contacto sin interacciones Vocify | «Sin interacciones registradas todavía». Mostrar solo datos/tareas de HubSpot que sí estén disponibles, etiquetados como CRM, y acción «Ver contacto en HubSpot». No inventar última conversación ni objeciones. |
| Historial parcial o permiso insuficiente | «No pudimos cargar todo el contexto», con bloques verificables, fuente afectada y reintento. No sustituirlo por «sin interacciones». |
| Lectura en curso | Reservar las cuatro filas; no mostrar datos del contacto anterior ni el vacío antes de terminar. |

La API propuesta añade estado de cobertura y fecha de fuente al contrato de lectura ya descrito; no añade generación LLM ni una tabla de brief. Todo este bloque sigue condicionado a la aprobación de formato y ubicación: documentarlo no autoriza construirlo.

### Criterio de aceptación (Definition of Done)

- [ ] Dani valida primero formato y ubicación.

- [ ] Ninguna afirmación carece de fuente.

- [ ] Abrir el brief no genera análisis nuevo.

- [ ] El contacto sin historial tiene un estado explícito.

- [ ] La precarga no muestra datos de un contacto anterior.

- [ ] La lectura principal cabe en cuatro filas.

- [ ] Tras aprobación, abrir la extensión en un contacto HubSpot muestra el brief antes de llamar; dashboard y desktop reutilizan el contenido como accesos secundarios.

- [ ] Sin historial Vocify se muestra el estado explícito y una acción CRM útil; una lectura incompleta no se presenta como ausencia de historial.

- [ ] Navegar entre contactos no mezcla datos y no desplaza una captura/revisión que siga activa sobre el contacto original.

### Riesgos / edge cases conocidos

Historial antiguo, varios deals del mismo contacto y contexto contradictorio. Hasta validar esta propuesta no se crea su UI ni se convierte en dependencia de las demás entregas.

## Mapa de archivos y responsabilidades

| Acción futura | Ruta | Responsabilidad |
|---|---|
| Crear condicionado | `/Users/danizal/getvocify/backend/app/services/briefs/preparation.py` | Agregación de lectura. |
| Crear condicionado | `/Users/danizal/getvocify/backend/app/api/briefs.py` | GET briefs scoped. |
| Crear condicionado | `/Users/danizal/getvocify/backend/tests/briefs/test_preparation.py` | Fuente, vacío y stale. |
| Crear condicionado | `/Users/danizal/getvocify/shared/ui/components/brief.js` | Render cuatro filas. |
| Crear condicionado | `/Users/danizal/getvocify/shared/ui/components/v-brief.js` | Elemento compartido. |
| Crear condicionado | `/Users/danizal/getvocify/shared/ui/brief.test.js` | Render/identidad. |
| Modificar condicionado | `/Users/danizal/getvocify/chrome-extension/popup/index.html` | screen-contact. |
| Modificar condicionado | `/Users/danizal/getvocify/chrome-extension/popup/popup.js` | Entrada primaria. |
| Modificar condicionado | `/Users/danizal/getvocify/chrome-extension/background.js` | Contexto y prioridad captura. |
| Crear condicionado | `/Users/danizal/getvocify/src/features/briefs/hooks/usePreparationBrief.ts` | Accesos secundarios. |

Los archivos marcados «Crear» todavía no existen por esta planificación. Los marcados «Modificar» pueden ser producidos por una dependencia; su procedencia debe quedar indicada. Los tests y fixtures se crean en ejecución, nunca se confunden con datos de producción.

## Tareas secuenciales con ciclo TDD

Cada tarea termina con evidencia revisable. Los ejemplos de contrato y prueba fijan entradas/salidas futuras; no se han ejecutado ahora. Dividir los pasos de implementación en cambios pequeños dentro del mismo ciclo rojo → verde → revisión. No iniciar otra feature para esquivar un fallo.

### F03.01 — Registrar decisión de formato y superficie antes de ejecutar

**Archivos:** Spec/report de entrega F03; no código en este paso.

**Interfaz y propiedad:** Aprobación debe incluir cuatro filas, extensión contacto primaria y secundarios. Decisión se referencia en reporte.

**Ejemplo concreto de contrato o prueba a incorporar:**

```text
DECISION F03: formato + ubicación + fecha + autor
Sin decisión: tareas F03.02–F03.04 permanecen bloqueadas
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Sin respuesta o negativa | Estado bloqueado y no hay código F03. |
| Aprobación con cambio | Actualizar spec/contrato y casos antes de siguiente tarea. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `git diff --stat` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Presentar propuesta concreta ya descrita y registrar decisión; el silencio no aprueba.

- [ ] Si sigue bloqueada, preparar F10 y registrar independencia según maestro; no crear v-brief preventivamente.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `git diff --stat` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Decision record explícito; no se finge cierre de feature por haber redactado propuesta.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F03.01`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F03.02 — Agregar bloques con fuentes y cobertura

**Archivos:** briefs/preparation.py, api/briefs.py, tests/briefs/test_preparation.py.

**Interfaz y propiedad:** C12 GET briefs por connection/contact/deal; blocks[0..4], coverage, source_revision, contact ref.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"connection_id":"crm-A","contact_id":"42","deal_id":null,"status":"no_interactions","coverage":"complete","source_revision":"ctx-1","blocks":[],"crm_url":"https://app.hubspot.com/"}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Contacto sin Vocify y CRM disponible | Sin interacciones; datos CRM etiquetados. |
| Fuente inaccesible | Partial, no ausencia de historial. |
| Dos deals conflictivos | Requiere elegir ámbito; no fusiona compromisos. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/briefs/test_preparation.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Seleccionar última interacción y compromisos vigentes por identidad completa; evidencia cada bloque.

- [ ] Resolver guía de playbook publicada por tipología cuando hay respaldo, sin generar respuesta nueva.

- [ ] Cache revisionada y permisos en servicio; registrar API cuando esté autorizado.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/briefs/test_preparation.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Cero invocaciones LLM y ninguna afirmación sin source reference.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F03.02`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F03.03 — Crear componente y navegación del contacto

**Archivos:** components/brief.js/v-brief.js, popup index/popup.js/background.js; shared/ui/brief.test.js.

**Interfaz y propiedad:** C12 .data; clave tenant/connection/contact/deal/revision. Captura/revisión activa tiene prioridad.

**Ejemplo concreto de contrato o prueba a incorporar:**

```text
contacto A (request A) -> contacto B (request B)
response A -> ignorar
response B -> render brief B
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Navegar A->B, A responde último | No se muestra A en B. |
| Abrir sobre contacto sin llamada | screen-contact con contexto. |
| Captura A activa y pestaña B | No cambia identidad de captura ni su revisión. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `node --test shared/ui/brief.test.js` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Renderizar cuatro filas/skeleton/empty/partial con la misma altura inicial.

- [ ] Añadir screen-contact al controlador existente sin reemplazar auth/record/review states.

- [ ] Descartar respuestas por key/revisión y conservar retorno a captura; conectar call existente.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `node --test shared/ui/brief.test.js` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Recorrido real en side panel HubSpot sin llamada y durante captura.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F03.03`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F03.04 — Integrar secundarios y precarga acotada

**Archivos:** usePreparationBrief.ts; TodayPanel/marcador y desktop renderer; tests de clave compartida.

**Interfaz y propiedad:** Mismo C12, sin otra versión de contenido por host.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"cache_key":["user-1","company-1","crm-A","42",null,"ctx-1"]}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Prefetch siguiente contacto | Datos no visibles hasta cambiar identidad. |
| Logout/cambio empresa | Cache purgada y solicitudes canceladas. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `npm run build && make check-generated` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Añadir expansión de tarjeta, marcador y home desktop como secundarios al mismo componente.

- [ ] Precargar solo próximo contacto de queue cuando permitido; evitar amplificar lecturas de todos los contactos.

- [ ] Verificar idioma/fuentes y comportamiento sin audio ni historial.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `npm run build && make check-generated` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Igual contenido/fuentes en todas las superficies para la misma revisión.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F03.04`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

## Verificación integrada y criterios de salida adicionales

Solo tras aprobación: abrir contacto HubSpot nuevo, revisar estado sin historial, llamar y volver. Navegar rápido A/B y verificar que no aparece contexto obsoleto. Abrir el mismo brief en dashboard y desktop.

### Regresiones y comandos al cerrar

- `cd backend && .venv/bin/python -m pytest tests/briefs/test_preparation.py -q`
- `node --test shared/ui/brief.test.js`
- `npm run build`
- `make check-generated`

Ejecutar los comandos desde `/Users/danizal/getvocify`, salvo el `cd` explícito. Un directorio de pruebas indicado como nuevo solo estará disponible después de sus tareas; que hoy no exista no autoriza a omitirlo al ejecutar. Las pruebas de IA usan datos reales autorizados y anonimizados; los ejemplos sintéticos de este plan sirven solo para contratos y tests deterministas.

### Qué vuelve al coordinador

- [ ] Informe de `F03` con tarea/criterio → resultado → prueba o veredicto → commit, migración aplicada y contrato entregado.

- [ ] Comparación de interfaces producidas con `00-contracts.md`; ninguna divergencia silenciosa de campos, estados, permisos o semántica de `null`.

- [ ] Revisión SOLID y limpieza de listeners/jobs/efectos; los servicios no duplican interpretación que corresponde a extracción.

- [ ] Evidencia de todos los estados de UI especificados. En web, `reticle_act_and_wait` o `reticle_assert` con consecuencia explícita; en desktop/extensión, además el recorrido nativo. `unknown` y `no-fault` no cierran.

- [ ] Bloqueos y edge cases nuevos en `docs/superpowers/deliveries/F03/report.md` y en el commit/PR. No marcar completa mientras haya criterios pendientes; una suspensión debe nombrar las dependencias no afectadas.

## Handoff a la siguiente entrega

Ninguna entrega posterior requiere F03. Si no se aprueba, entregar informe de bloqueo y continuar secuencia independiente sin UI de preparación encubierta.
