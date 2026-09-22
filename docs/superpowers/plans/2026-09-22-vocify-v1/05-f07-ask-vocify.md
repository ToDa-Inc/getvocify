# F07 — Ask Vocify en dashboard y audio bidireccional: plan ejecutable

> **Ejecución futura:** usar `executing-plans` dentro del subagente dedicado a esta entrega; la coordinación secuencial usa `subagent-driven-development`. Este documento es planificación, no una implementación ni una autorización para desplegar. Ninguna casilla de ejecución está completada.

**Objetivo:** Hacer accesible el loop CRM existente mediante chat web y pregunta por voz con permisos e idempotencia.

**Arquitectura:** Un loop, transportes independientes. Web persiste turno y consulta por polling; herramientas dependen de capacidades CRM pequeñas. Confirmación ligada a operación/revisión/contacto.

**Stack:** FastAPI/Python, Supabase/PostgreSQL, React 18/TypeScript y módulos JS compartidos; Electron/extensión cuando figuren entre las superficies de esta entrega.

**Posición:** 5 de 16. **Estado:** planificada; no iniciada.

**Navegación:** [plan maestro](/Users/danizal/getvocify/proposed_plan.md) · [contratos](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-contracts.md) · [integración y gates](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-integration-and-gates.md)

**Fuentes de esta entrega:** P: [Prompt técnico](/Users/danizal/getvocify/docs/TECHNICAL_PLANNING_PROMPT_VOCIFY_V1.md) · A: [Análisis de producto](/Users/danizal/getvocify/docs/PRODUCT_PLANNING_ANALYSIS_2026-09-21.md).

## Entrada, salida y frontera de responsabilidad

| Tipo | Contrato de esta entrega |
|---|---|
| Recibe | run_copilot_turn existente; identidad C01/C04 cuando disponible; proveedores y scopes reales. |
| Produce | C07 AskTurn/Operation; C08 lecturas CRM con cobertura; panel de chat y audio editable. |
| Dependencias de código | Código auditado y diseños existentes; ninguna entrega V1 previa. |
| Migración propia | 041_copilot_web_sessions.sql |
| No le corresponde | No otro agente, streaming simulado, TTS, Gmail directo ni ejecución CRM sin confirmación. F0 no es dependencia dura para consultar datos legacy. |

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

## Feature: F07 — Ask Vocify en dashboard y audio bidireccional

**Fuente:** A §6.1–6.3; P §4.2; código de `crm_copilot`.  

**Prioridad:** V1.

### En una frase

El comercial puede preguntar por sus contactos, revisar lo que ocurrió y pedir acciones desde el dashboard o mediante una nota de voz.

### Por qué (first principles)

Evita buscar información y operar manualmente varias pantallas. Debe compartir el comportamiento del WhatsApp existente, incluyendo sus confirmaciones para escribir.

### Qué ya existe (auditoría)

- Loop, historial, cambio de foco, selección y confirmación.

- Tablas de conversaciones y mensajes.

- Speechmatics y grabación de voz.

- Gap real: transporte web, permisos por herramienta, soporte Pipedrive y superficie conversacional.

### Backend

- Reutilizar `run_copilot_turn`; no crear otro agente.

- Sustituir el acceso obligatorio a `HubSpotBundle` por adaptadores de herramientas sobre los proveedores.

- Mantener herramientas discretas: buscar contacto, leer contexto, listar tareas, proponer cambio, crear nota/tarea/contacto/deal.

- La capa de permisos valida cada objeto antes de devolver datos o ejecutar acciones.

- Migración 041:

  - Añadir aislamiento de empresa a las sesiones web.

  - `copilot_turns`: conversación, `client_turn_id`, estado, resultado, revisión y lease.

  - `copilot_operations`: operación confirmada, clave idempotente, estado y resultado remoto.

- Endpoints:

  - `POST /api/v1/ask/conversations`.

  - `GET /api/v1/ask/conversations/{id}`.

  - `POST /api/v1/ask/conversations/{id}/turns`.

  - `GET /api/v1/ask/conversations/{id}/turns/{turn_id}`.

- El POST devuelve el resultado o `202` si continúa; la UI consulta el turno persistido. No hace falta otro WebSocket en V1.

- La confirmación referencia una operación concreta y su revisión. No equivale a confirmar «lo último que haya pendiente» después de cambiar de contacto.

- Mantener `CRM_COPILOT_MODEL`.

- Añadir lectura de emails y meetings al contexto; la función actual contempla esos tipos, pero la hidratación del contacto no los solicita.

- Mantener API de proveedores. No introducir MCP como requisito: A §6.2 dejó expresamente abierta su conveniencia y el código ya tiene un camino funcional.

**SOLID:** un loop compartido; transportes independientes; herramientas pequeñas; proveedores sustituibles con pruebas de contrato.

### Frontend / Dashboard

- Crear `/Users/danizal/getvocify/src/features/ask/`.

- Panel integrado en el dashboard, accesible desde «Preguntar», sin convertirlo en otra navegación principal.

- Historial, respuesta, selección y confirmación como estados explícitos.

- Voz → transcripción editable → mismo turno conversacional → respuesta textual. No añadir voz sintetizada.

- En landing, las consultas CRM requieren sesión; conservar la experiencia pública existente.

- En extensión, separar «anotar una interacción» de «preguntar», para no crear memos comerciales al hacer consultas.

- Copy: «¿Qué quedó pendiente con Marina?».

#### Panel, espera y voz — A9

**Archivos previstos:** `/Users/danizal/getvocify/src/features/ask/components/AskPanel.tsx`, `ConversationThread.tsx`, `TurnStatus.tsx` y `VoiceComposer.tsx`; transporte y estado en `/Users/danizal/getvocify/src/features/ask/hooks/useAskConversation.ts`. Integrar el acceso en `/Users/danizal/getvocify/src/components/dashboard/DashboardLayout.tsx`. `CopilotNote` puede representar el texto de una respuesta, pero no es el contenedor de conversación ni su máquina de estados.

- Panel lateral derecho en escritorio, con cabecera «Preguntar a Vocify», contexto de contacto/empresa cuando proceda, historial desplazable y compositor fijo al pie. En pantallas estrechas ocupa el ancho disponible; cerrar devuelve el foco al botón que lo abrió y conserva la conversación.
- Mensajes del comercial en burbuja alineada a la derecha con fondo de contraste suave; respuestas de Vocify a la izquierda, en superficie neutra. Usar los tokens existentes, ancho de lectura limitado, nombre/rol accesible y separación por turnos. Las fuentes y acciones se sitúan debajo del texto, no mezcladas como mensajes del usuario.
- Selecciones entre contactos y confirmaciones de escritura son tarjetas dentro del turno que las originó. Muestran destinatario y acción concreta, con «Confirmar»/«Cancelar»; al cambiar de contacto o revisión quedan inactivas y explican por qué. Un «sí» de otra conversación no confirma esa tarjeta.
- Conversación nueva: «Pregunta por un contacto o por lo que quedó pendiente», con ejemplos de preguntas, sin métricas inventadas ni mensajes de historial ficticios. Una respuesta sin datos lo dice y permite ajustar la consulta; una lectura CRM parcial identifica la limitación sin convertirla en «no hay actividad».

| Estado del turno persistido | Representación | Comportamiento |
|---|---|---|
| Envío inicial | Mensaje del usuario visible; espacio de respuesta reservado con «Enviando…». | Conservar `client_turn_id`; un doble clic no crea otro turno. |
| HTTP `202` / pendiente | Burbuja de Vocify con indicador discreto y «Consultando la información…», anunciada por `role="status"`. | Polling del turno, sin tokens simulados. Consultar a 1 s al inicio y después cada 3 s; suspender al ocultar el panel y retomar el mismo ID al abrirlo. |
| Espera prolongada | Tras 30 s: «La consulta sigue en curso. Puedes cerrar y volver». | Reducir polling a 5 s; no declarar fallo ni reenviar el POST por tardanza. El job recuperable determina el estado final. |
| Respuesta completa | Sustituir el estado de espera por el resultado completo, selección o confirmación. | No animar letra a letra. Hacer scroll solo si el usuario estaba al final; de lo contrario, indicar nueva respuesta. |
| Error de consulta o sesión | Conservar mensaje y borrador. «No pudimos consultar el resultado» / «Vuelve a iniciar sesión». | Reintentar lectura del mismo turno. Un fallo terminal permite reintento controlado con el estado/idempotencia del backend, sin duplicar operaciones remotas. |

El botón Enviar queda deshabilitado mientras el turno de esa conversación está en curso. El usuario puede consultar historial y cerrar el panel. No se presenta una cancelación de efectos CRM como si cerrar la UI pudiera revertirlos.

| Estado de voz | Indicador y controles |
|---|---|
| Inactivo | Botón «Grabar pregunta» junto al campo de texto, con nombre accesible. |
| Grabando | Punto de grabación, temporizador `mm:ss`, medidor de amplitud basado en audio real y botones «Detener»/«Cancelar». Con reducción de movimiento, conservar texto y temporizador sin onda animada. |
| Transcribiendo | «Transcribiendo tu pregunta…»; la grabación ha parado. Reservar el espacio del texto editable y no mostrar una onda como si siguiera grabando. |
| Texto disponible | Transcripción en el compositor para revisar y editar; «Enviar» inicia el mismo turno que una pregunta escrita. Nunca enviar automáticamente al detener. |
| Silencio, permiso denegado o fallo | «No se detectó voz» o explicación concreta, con «Volver a grabar» y alternativa de escribir. Cancelar descarta la grabación no enviada y libera micrófono. |

### Criterio de aceptación (Definition of Done)

- [ ] La misma pregunta usa el mismo loop en web y WhatsApp.

- [ ] HubSpot y Pipedrive pasan pruebas equivalentes de las capacidades anunciadas.

- [ ] Ninguna escritura ocurre sin su confirmación válida.

- [ ] Doble clic, recarga o reintento no duplica una operación.

- [ ] Cambiar de contacto invalida la propuesta anterior.

- [ ] Un miembro no obtiene información de otro equipo mediante preguntas o IDs manipulados.

- [ ] Audio y texto producen respuestas basadas en las mismas herramientas.

- [ ] Respuestas breves, sin mostrar llamadas a herramientas ni IDs internos.

- [ ] Un `202` muestra espera sin streaming ficticio; cerrar y reabrir recupera el mismo turno. Error de polling y respuesta tardía no duplican el mensaje ni la operación.

- [ ] Se distingue grabando de transcribiendo; el temporizador se detiene, el texto se puede corregir y solo se envía al pulsar «Enviar». Silencio y permiso denegado permiten seguir escribiendo.

- [ ] La conversación vacía, una consulta sin resultados y una lectura parcial CRM tienen textos y acciones distintos. La navegación de foco y el scroll preservan la lectura del historial.

### Riesgos / edge cases conocidos

Permisos CRM incompletos, expiración de sesión, operaciones remotas de resultado incierto y cambio de CRM principal. Una operación incierta se reconcilia antes de reintentarse; no se repite a ciegas.

## Mapa de archivos y responsabilidades

| Acción futura | Ruta | Responsabilidad |
|---|---|
| Crear | `/Users/danizal/getvocify/backend/app/api/ask.py` | Conversaciones y turnos web. |
| Crear | `/Users/danizal/getvocify/backend/app/services/crm_copilot/web_sessions.py` | Sesión/turno/operación idempotentes. |
| Modificar | `/Users/danizal/getvocify/backend/app/services/crm_copilot/loop.py` | Reutilización, sin motor paralelo. |
| Modificar | `/Users/danizal/getvocify/backend/app/services/crm_copilot/tools.py` | Capacidades neutrales a CRM. |
| Modificar | `/Users/danizal/getvocify/backend/app/services/crm_providers/protocols.py` | Protocolos de lectura pequeños. |
| Modificar | `/Users/danizal/getvocify/backend/app/services/crm_providers/hubspot_provider.py` | Adapter C08. |
| Modificar | `/Users/danizal/getvocify/backend/app/services/crm_providers/pipedrive_provider.py` | Adapter C08. |
| Crear | `/Users/danizal/getvocify/backend/tests/crm_copilot/test_web_turns.py` | 202/poll/confirmación. |
| Crear | `/Users/danizal/getvocify/backend/tests/crm_providers/test_context_contract.py` | Pruebas equivalentes ambos CRMs. |
| Crear | `/Users/danizal/getvocify/src/features/ask/components/AskPanel.tsx` | Host de conversación. |
| Crear | `/Users/danizal/getvocify/src/features/ask/components/ConversationThread.tsx` | Burbujas y confirmaciones. |
| Crear | `/Users/danizal/getvocify/src/features/ask/components/VoiceComposer.tsx` | Micrófono/transcripción/revisión. |
| Crear | `/Users/danizal/getvocify/src/features/ask/hooks/useAskConversation.ts` | Polling del turno persistido. |
| Modificar | `/Users/danizal/getvocify/src/components/dashboard/DashboardLayout.tsx` | Acceso Preguntar. |

Los archivos marcados «Crear» todavía no existen por esta planificación. Los marcados «Modificar» pueden ser producidos por una dependencia; su procedencia debe quedar indicada. Los tests y fixtures se crean en ejecución, nunca se confunden con datos de producción.

## Tareas secuenciales con ciclo TDD

Cada tarea termina con evidencia revisable. Los ejemplos de contrato y prueba fijan entradas/salidas futuras; no se han ejecutado ahora. Dividir los pasos de implementación en cambios pequeños dentro del mismo ciclo rojo → verde → revisión. No iniciar otra feature para esquivar un fallo.

### F07.01 — Desacoplar herramientas del CRM concreto

**Archivos:** tools.py y protocols/providers; tests/crm_providers/test_context_contract.py.

**Interfaz y propiedad:** C08 read_contact_context y list_assigned_tasks; coverage complete/partial/forbidden/unavailable. Ampliaciones de otras capacidades se entregan con su consumidor.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"items":[],"coverage":"forbidden","observed_at":"2026-09-22T10:00:00Z","next_cursor":null,"reason":"email_scope_missing"}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| HubSpot/Pipedrive misma consulta | Mismo contrato lógico y errores normalizados. |
| Email scope ausente | Partial/forbidden, no ausencia de emails. |
| Objeto ajeno solicitado por ID | Denegado antes de devolver datos. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/crm_providers/test_context_contract.py tests/crm_copilot/test_tools.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Sustituir obligatoriedad de HubSpotBundle por capacidades inyectadas sin reescribir loop.

- [ ] Hidratar emails/meetings accesibles y paginación; conservar conexión en cada referencia.

- [ ] Separar errores de permiso/transporte de lista vacía y registrar scopes concretos faltantes.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/crm_providers/test_context_contract.py tests/crm_copilot/test_tools.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Contrato común real con fixtures de ambos proveedores, sin datos cruzados.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F07.01`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F07.02 — Persistir turnos y confirmar una operación concreta

**Archivos:** web_sessions.py, api/ask.py, migration041, tests/crm_copilot/test_web_turns.py.

**Interfaz y propiedad:** C07 POST turno devuelve 200 o 202 con turn_id; confirmación lleva operation_id+revision+target, no un sí global.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"conversation_id":"conv-1","turn_id":"turn-2","status":"pending","client_turn_id":"web-2"}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| POST repetido con client_turn_id | Mismo turno; una operación lógica. |
| Cambio contacto entre propuesta y confirmar | Conflicto; ninguna escritura al contacto nuevo. |
| Respuesta remota incierta | Reconciliar antes de repetir operación. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/crm_copilot/test_web_turns.py tests/crm_copilot/test_confirm_and_reset.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Crear aislamiento tenant y claves de turno/operación; no mover sesiones WhatsApp a un almacenamiento incompatible.

- [ ] Invocar run_copilot_turn desde transporte web, persistir resultado y lease recuperable.

- [ ] Validar operación/revisión/contacto y consentimiento de escritura en servidor en cada ejecución.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/crm_copilot/test_web_turns.py tests/crm_copilot/test_confirm_and_reset.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Doble envío y recarga no duplican efectos, sesión web no lee otra empresa.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F07.02`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F07.03 — Construir conversación y polling sin perder contexto

**Archivos:** AskPanel.tsx, ConversationThread.tsx, TurnStatus.tsx, useAskConversation.ts; DashboardLayout.tsx.

**Interfaz y propiedad:** Estados/intervalos A9; api-client base ya incluye /api/v1. Cierre UI no cancela escrituras ya aprobadas.

**Ejemplo concreto de contrato o prueba a incorporar:**

```text
POST /ask/conversations/conv-1/turns -> 202 turn-2
GET /ask/conversations/conv-1/turns/turn-2 -> pending
GET /ask/conversations/conv-1/turns/turn-2 -> completed
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| 202 más de 30s | Mensaje de espera prolongada; no reenvía POST. |
| Cerrar/reabrir | Consulta mismo turn_id y recupera resultado. |
| Respuesta mientras lee arriba | No desplaza lectura; indica nuevo mensaje. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `npm run build` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Implementar layout de A9 y tarjetas de selección/confirmación ligadas al turno.

- [ ] Añadir polling con cleanup al ocultar/cambiar sesión y revalidación al abrir; conservar borrador y mensaje en fallos.

- [ ] Probar conversación nueva, datos parciales y denegación con las respuestas reales del endpoint de prueba.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `npm run build` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Reticle verifica texto enviado -> pending -> respuesta y recuperación al reabrir.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F07.03`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F07.04 — Añadir pregunta por voz sin crear memo de venta

**Archivos:** VoiceComposer.tsx y adaptador STT existente; tests de estado puro bajo src/lib/ask-voice.test.ts.

**Interfaz y propiedad:** Voz -> transcripción editable -> mismo POST del turno. No sintetizar respuesta ni subir como interacción comercial.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"composer_state":"ready_to_send","text":"¿Qué quedó pendiente con Marina?","auto_send":false}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Silencio/cancelar | Ningún turno enviado; micrófono liberado. |
| Detener grabación | Timer se para, estado transcribiendo, luego texto editable. |
| Error permiso | Permite escribir sin bloquear panel. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `node --experimental-strip-types --test src/lib/ask-voice.test.ts` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Reutilizar captura/STT para texto, separar esta intención del guardado de memo en extensión.

- [ ] Medir amplitud real y tiempo; aplicar reduced-motion; cleanup de audio en desmontaje.

- [ ] Enviar solo al confirmar texto editado y verificar mismas herramientas que mensaje escrito.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `node --experimental-strip-types --test src/lib/ask-voice.test.ts` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Flujo voz y texto llega al mismo loop; no aparece un memo falso.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F07.04`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

## Verificación integrada y criterios de salida adicionales

Consultar un contacto, mostrar lectura parcial de email, seleccionar otro, proponer acción y confirmar la operación correcta. Simular 202 y recarga. Repetir pregunta con voz y corregir texto antes de enviar. Probar member intentando datos ajenos.

### Regresiones y comandos al cerrar

- `cd backend && .venv/bin/python -m pytest tests/crm_copilot tests/crm_providers -q`
- `npm run build`
- `make test-js`

Ejecutar los comandos desde `/Users/danizal/getvocify`, salvo el `cd` explícito. Un directorio de pruebas indicado como nuevo solo estará disponible después de sus tareas; que hoy no exista no autoriza a omitirlo al ejecutar. Las pruebas de IA usan datos reales autorizados y anonimizados; los ejemplos sintéticos de este plan sirven solo para contratos y tests deterministas.

### Qué vuelve al coordinador

- [ ] Informe de `F07` con tarea/criterio → resultado → prueba o veredicto → commit, migración aplicada y contrato entregado.

- [ ] Comparación de interfaces producidas con `00-contracts.md`; ninguna divergencia silenciosa de campos, estados, permisos o semántica de `null`.

- [ ] Revisión SOLID y limpieza de listeners/jobs/efectos; los servicios no duplican interpretación que corresponde a extracción.

- [ ] Evidencia de todos los estados de UI especificados. En web, `reticle_act_and_wait` o `reticle_assert` con consecuencia explícita; en desktop/extensión, además el recorrido nativo. `unknown` y `no-fault` no cierran.

- [ ] Bloqueos y edge cases nuevos en `docs/superpowers/deliveries/F07/report.md` y en el commit/PR. No marcar completa mientras haya criterios pendientes; una suspensión debe nombrar las dependencias no afectadas.

## Handoff a la siguiente entrega

F04 reutiliza lecturas/contexto C08; F15 amplía herramientas de lectura scoped sin modificar reglas de confirmación. No reemplazar el loop por MCP ni otro agente.
