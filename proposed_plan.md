# Vocify V1 — Plan maestro e índice de ejecución

> **Para la ejecución futura:** utilizar `subagent-driven-development` para coordinar las 16 entregas secuenciales y `executing-plans` dentro de cada sesión. Cada entrega tiene un subagente con contexto acotado, un informe de salida y una revisión antes de habilitar la siguiente (§5). Esta sesión actualiza exclusivamente el plan. Las casillas de las features registran implementación futura; las de §6.1 registran únicamente la cobertura documental de esta revisión.

**Objetivo:** conectar la captura existente con seguimiento, prioridades diarias, asistencia comercial y visibilidad de equipo, reutilizando el pipeline y los diseños ya establecidos.

**Arquitectura:** el backend interpreta las conversaciones y devuelve datos preparados para mostrar. Dashboard, extensión y desktop comparten los componentes que representan la misma información. Las operaciones sobre el CRM siguen pasando por sus proveedores y por los mecanismos de aprobación.

**Stack:** Python/FastAPI, Supabase/PostgreSQL, React 18, TypeScript, Vite, TanStack Query, Electron, extensión Chrome, Speechmatics, `LLMClient`, `JevClient` y Resend.

**Estado de este entregable:** planificación y auditoría. Esta revisión actualiza únicamente el plan; no modifica código ni ejecuta la implementación.

## Cómo se organiza ahora este plan

Este archivo es el **plan maestro**: decisiones globales, auditoría, secuencia, migraciones, proceso y bloqueos. Las 15 especificaciones funcionales se han trasladado íntegramente a planes separados y F0/F0.1 tiene su propio plan de cimientos. Cada documento añade tareas secuenciales, archivos, interfaces, ejemplos de contrato/prueba, casos concretos, comandos, verificación y handoff.

- [Índice de los 16 planes](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/README.md).
- [Contratos compartidos C01–C19 y propietarios](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-contracts.md).
- [Grafo de dependencias, integración y gates](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-integration-and-gates.md).

**Fuentes canónicas:** este maestro manda sobre alcance/decisiones/secuencia; el catálogo de contratos manda sobre interfaces compartidas; cada plan de entrega conserva su UX, edge cases y detalle de ejecución. El cierre de una entrega exige las cuatro columnas de [00-cierre.md](/Users/danizal/getvocify/.worktrees/vocify-v1/docs/superpowers/plans/2026-09-22-vocify-v1/00-cierre.md): contrato, Definition of Done, spec de producto vista en la superficie, y la superficie que esa feature nombra. Un test verde no cierra la fila. Los planes históricos PF/S se reutilizan donde se indique, con las correcciones explícitas de esta revisión. Un cambio de contrato exige actualizar productor y consumidores antes de implementar; no hay 16 diseños independientes.

**Cómo se concatena el trabajo:** leer maestro para coordinar → entregar al subagente el plan de su feature y solo los contratos/dependencias relevantes → revisar su resultado y contrato producido → habilitar el siguiente consumidor. No pegar el documento entero en cada sesión ni mantener otra copia editable del conjunto. Las casillas de implementación siguen abiertas; solo se ha redactado documentación.

## 1. Alcance, fuentes y decisiones confirmadas

Se mantienen las 15 funcionalidades del documento de entrada. Los cimientos técnicos descritos más adelante son dependencias de esas funcionalidades, no ampliaciones del producto.

Fuentes utilizadas:

- **P:** [Prompt técnico V1](/Users/danizal/getvocify/docs/TECHNICAL_PLANNING_PROMPT_VOCIFY_V1.md).

- **A:** [Análisis de producto](/Users/danizal/getvocify/docs/PRODUCT_PLANNING_ANALYSIS_2026-09-21.md).

- **S:** [Diseño de Copilot Spine](/Users/danizal/getvocify/docs/superpowers/specs/2026-09-21-copilot-spine-design.md).

- **PF:** [Plan existente de fundamentos y follow-up](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-21-copilot-spine-foundation-and-followup.md).

- **I:** [Plan de integración de superficies](/Users/danizal/getvocify/docs/features/PLAN_INTEGRACION.md).

- **E:** [Experiencia de producto](/Users/danizal/getvocify/docs/EXPERIENCIA_PRODUCTO.md).

- **D:** [Estructura inteligente](/Users/danizal/getvocify/docs/features/ESTRUCTURA_INTELIGENTE.md).

- **M:** [Plan maestro](/Users/danizal/getvocify/docs/features/MASTER_PLAN.md).

- **U:** [Instrucciones completas de actualización UX/UI y ejecución](/Users/danizal/getvocify/docs/PLAN_UPDATE_INSTRUCTIONS_VOCIFY.md). Esta revisión incorpora todos sus puntos A0–A14, A_principio y B1–B6. Sus correcciones prevalecen sobre la redacción anterior del plan; B4 y B5 se conservan sin rediseño.

Decisiones confirmadas en esta conversación:

1. **La preparación previa permanece como propuesta pendiente de validación.** Se especifica una opción concreta, pero no se autoriza su implementación.

2. **La adherencia principal será pasos cumplidos / pasos aplicables**, agregable por interacción, comercial y equipo.

### Restricciones globales

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

### Qué se verificó durante la auditoría

La auditoría inicial examinó el repositorio principal en `4a3d938`, entonces con árbol de trabajo limpio. Esta revisión documental conserva los archivos de planificación sin seguimiento y no modifica código. El repositorio hermano del desktop conserva cambios locales y archivos sin seguimiento.

En la auditoría inicial se ejecutaron estas pruebas; no se han vuelto a ejecutar al editar este documento:

- **53 pruebas existentes del backend:** fechas, permisos de actividad, leases, Jev y copiloto conversacional.

- **14 pruebas existentes del desktop:** canales, escucha, revisión y permisos.

Todas pasaron en aquella ejecución. Una prueba de Jev emitió un aviso por un mock asíncrono no esperado correctamente. Estos resultados validan piezas existentes; no prueban las funcionalidades futuras ni el instalador propuesto.

Se omite Reticle en esta sesión porque no se ha cambiado ninguna funcionalidad de la aplicación.

## 2. Auditoría inicial de las 15 funcionalidades

| ID | Funcionalidad | Qué existe y se reutiliza | Trabajo realmente pendiente |
|---|---|---|---|
| F01 | Captura desktop | Dentro de la repo de getvocify-desktop. Captura micrófono/sistema, transcripción en vivo, permisos y revisión. El desktop ya llama al pipeline de memos. [Punto de envío](/Users/danizal/getvocify-desktop/renderer/app.js:529). | Importar el trabajo local correctamente; adaptar styling, asegurarse de un flow nitido, intentar imitar la UX de Granola lo máximo posible preservar identificación de meeting; conservar audio y tiempos para notas y reproducción; cerrar recuperación y verificación.          |
| F02 | Follow-up | Diseño y plan ejecutable completos en PF, tareas 2–14. `MemoExtraction` ya contiene resumen, próximos pasos y contacto. | Ejecutar ese plan. No existen todavía `shared/`, servicio de follow-up ni su migración. |
| F03 | Preparación previa | Resúmenes y próximos pasos existentes. | Lectura mínima: cero a tres hechos. Aprobada el 22 sep 2026. |
| F04 | Priorización | `painPoints`, historial de memos y proveedores CRM. [Modelo actual](/Users/danizal/getvocify/backend/app/models/memo.py:60). | Distinguir pain confirmado, recencia, reunión acordada y contacto sin llamadas registradas; añadir lectura de candidatos y ubicación en «Hoy». |
| F05 | Orquestador «Hoy» | Algoritmo de señales, reconciliación, agrupación y textos definido en S §5. | Persistencia, adaptación de entradas, trabajos diarios, lectura de tareas manuales y endpoint. El algoritmo del documento aún no está implementado. |
| F06 | Tareas inteligentes | Algoritmo anterior, marcador y navegación CRM existentes; controlador de cola diseñado en S §6.1. | Tarjetas compartidas, acciones, posponer/deshacer, sincronización entre superficies y conexión con estados reales de llamada. |
| F07 | Ask Vocify | Loop conversacional real con confirmaciones y memoria. [Loop](/Users/danizal/getvocify/backend/app/services/crm_copilot/loop.py:152). | PERMITELO. TIENES QUE SIMULAR signalcore-backend Wizard. Chat web, audio conversacional y adaptación multi-CRM. Las herramientas actuales rechazan Pipedrive: [restricción real](/Users/danizal/getvocify/backend/app/services/crm_copilot/tools.py:295) |
| F08 | Playbooks | Settings, permisos de empresa y contexto comercial. | Playbooks por tipología, versiones, entradas aplicables al coaching y carga manual de texto/PDF/audio. |
| F09 | Scoring | Extracción, cliente LLM y contexto comercial. | Evaluación contra playbook, persistencia versionada, evidencia y visualización. No hay backend de scoring implementado. |
| F10 | Objeciones y notas | Objeciones como texto y taxonomía del copiloto en vivo. | Clasificación estructurada, resolución/obstáculo, notas durante captura con tiempo y contexto; almacenamiento para analítica. |
| F11 | Brief posterior | Resumen existente y patrón de ejecución asíncrona. | Agregación de coaching, disponibilidad configurable y recuperación de trabajos. Los leases actuales no son una cola duradera general. |
| F12 | Checklist y ayuda en vivo | WebSocket de transcripción, SSE de sugerencias, módulo React completo de copiloto y overlay nativo del desktop. [API existente](/Users/danizal/getvocify/backend/app/api/copilot.py:18). | Extraer lógica compartida y adaptar sus hosts React/Electron; conectar el meeting real con playbooks; checklist; respaldo verificable; transporte SSE y visibilidad en el overlay existente. No es trasladar una tarjeta. |
| F13 | Reporting al comercial | Resend ya integrado para emails transaccionales. [Cliente actual](/Users/danizal/getvocify/backend/app/integrations/resend_client.py:34). | Agregaciones, preferencias, programación, historial de entrega y campana. |
| F14 | Meeting booked | Jev, propuesta/aprobación, seguimiento de escrituras CRM y resolución parcial de fechas. | Acuerdo confirmado, hora exacta, zona horaria, propuesta editable y escritura específica mediante proveedores. |
| F15 | Dashboard de equipo | Permisos owner/admin, actividad de empresa y gestión de miembros. [Visibilidad actual](/Users/danizal/getvocify/backend/app/services/activity_scope.py:16). | Agregaciones de rendimiento, objeciones, competidores, adherencia, resultados CRM, reportes y herramientas de lectura de equipo para el chat. |

### Discrepancias encontradas y resolución

1. **El desktop ya alimenta el pipeline.** El trabajo no es construir una conexión nueva. Su envío actual utiliza `/memos/upload-and-extract`; el hueco está en conservación de contexto, audio, tiempos y cierre operativo.

2. **El tipo de origen puede perderse.** Ese endpoint utiliza `source_type` para ejecutar la extracción, pero no lo incluye en la inserción del memo ni lo persiste mediante el helper común. Esto puede hacer que una recuperación posterior trate un meeting como una nota de voz. Se corrige en F01. IGUAL PODEMOS PENSAR EN FORMAS DE DIFERENTES ENTITIES Y ADAPTARLAS EN BASE A QUE ACCION REALIZAR.

3. **La captura no garantiza reproducción posterior.** El desktop envía texto; `/memos/upload` también descarta audio y limita el archivo a 10 MB. No basta con apuntar el desktop a ese endpoint para resolver grabaciones largas. [Comportamiento actual](/Users/danizal/getvocify/backend/app/api/memos.py:500). REVISAR Y MEJORAR.

4. **Las marcas temporales no están conservadas de extremo a extremo.** El proxy extrae palabras y hablantes, pero omite sus tiempos. Se preservarán antes de prometer notas en un instante o reproducción de fragmentos. [Transformación actual](/Users/danizal/getvocify/backend/app/api/transcription.py:71).

5. *`CopilotNote` no es un chat.** Es un renderizador de notas. Se reutiliza para mostrar contenido cuando corresponda, pero el chat tendrá su propio componente y estado. [Componente](/Users/danizal/getvocify/src/components/dashboard/CopilotNote.tsx:3).

6. *`ActivityPanel` no es un feed de prioridades.** Muestra actividad e historial. «Hoy» será una sección propia en el inicio; el historial conservará su función.

7. **El loop es reutilizable; sus herramientas todavía no son neutrales al CRM.** La adaptación de herramientas a HubSpot/Pipedrive forma parte de F07. No se presenta como un simple cambio de transporte.

8. **El repositorio ya soporta identidad basada en contacto.** La descripción antigua de sistema exclusivamente centrado en deals no justifica reconstruir todo el matching. Se amplían contratos concretos. [Protocolos actuales](/Users/danizal/getvocify/backend/app/services/crm_providers/protocols.py:80).

9. **Jev no garantiza verdad ni determinismo factual.** Restringe respuestas a categorías y aporta confianza. Se conserva un estado desconocido; una clasificación fallida no se convierte en `false`. Su interfaz genérica actual es privada, por lo que F0.1 necesita exponer un método público pequeño, conservando transporte y comportamiento existentes.

10. **La extensión sí contiene infraestructura de asistencia en vivo.** El motivo técnico antiguo está desactualizado; el recorte de producto sigue vigente: no ampliar el coaching de cold calls en V1.

11. **Las fechas existentes no resuelven meeting booked completo.** `resolve_schedule` devuelve una fecha; `detected_task_due_iso` también devuelve solo fecha y los helpers de tareas pueden aplicar las 09:00. Ese valor por defecto no se utilizará como hora de reunión acordada.

12. **Una llamada sin conversación puede tener memo.** El código guarda memos de buzón/no respuesta. La cola y las métricas deben consultar `screening_outcome`, no asumir que `memo_id != null` significa conversación. [Código](/Users/danizal/getvocify/backend/app/services/telephony/call_processor.py:312).

13. **Follow-up permanece independiente de «Hoy».** Se ejecuta PF y no se retrasa hasta construir el orquestador. Su `sent` interno significa entrega al cliente de correo, no envío confirmado.

14. **El orden de dependencias prevalece sobre la numeración del prompt.** F0 y F0.1 se entregan juntos; las objeciones estructuradas preceden al scoring que las consume.

15. **Las fuentes antiguas proponen WhatsApp proactivo, Gmail OAuth, nuevas capturas y trabajo paralelo.** Se excluyen por las decisiones posteriores de P y A.

16. **La adherencia tenía dos definiciones.** Se resuelve con tu decisión: pasos cumplidos sobre pasos aplicables.

17. **Hay permisos de email pendientes de integración, no una conexión nueva con Gmail.** HubSpot exige `sales-email-read` para contenido de emails; no aparece en la lista local. Pipedrive asigna la lectura de mensajes asociados a personas a `mail:read`; sus permisos instalados no se pueden confirmar solo leyendo este repo. [HubSpot](https://developers.hubspot.com/changelog/announcement-new-scope-required-to-get-the-content-of-email-engagements?hs_amp=true), [Pipedrive](https://pipedrive.readme.io/docs/marketplace-scopes-and-permissions-explanations).

### Auditoría de pantallas reales — A0

Lectura estática del código actual de las tres superficies, revisada el 22 de septiembre de 2026. La configuración encontrada no equivale a una verificación de comportamiento en ejecución.

| Superficie / pantalla | Qué existe hoy | Consecuencia para el plan |
|---|---|---|
| Dashboard — [DashboardHome.tsx](/Users/danizal/getvocify/src/pages/dashboard/DashboardHome.tsx:8), 31 líneas | Saludo «Welcome back», `VoiceRecorderWidget` y `ActivityPanel`. No hay lista de contactos ni sección «Hoy». | F05 dispone de espacio real para crear la sección principal. Se conserva la grabación y el historial con sus funciones actuales; no hay un módulo complejo de prioridades que migrar. |
| Dashboard — [ObjectionCopilotPage.tsx](/Users/danizal/getvocify/src/pages/dashboard/ObjectionCopilotPage.tsx:1), 255 líneas | Página que orquesta captura, detección de turnos y sugerencias. Usa `useObjectionSuggestions`, `useTurnDetector`, `CopilotControls`, `SuggestionCard` y `VoiceEnrollmentPanel` de `@/features/copilot`, y `useRealtimeTranscription` de `@/features/recording`. También gestiona contexto comercial, voz enrolada y acciones manuales. | F12 exige adaptar lógica y ciclo de vida, no mover un componente. Se conserva la página beta como host React del núcleo reutilizado; el desktop consume ese núcleo mediante su propio adaptador y su captura existente. No se mantiene una segunda implementación independiente del motor. |
| Extensión — [popup/index.html](/Users/danizal/getvocify/chrome-extension/popup/index.html:15) | Solo `screen-loading`, `screen-login`, `screen-processing`, `screen-record`, `screen-review` y `screen-success`, dentro del acceso y ciclo de llamada. | Falta una vista dedicada al contexto de un contacto sin llamada activa. Si se aprueba F03 para la extensión, crear ese estado y su entrada/navegación forma parte del alcance; no puede presupuestarse como insertar un componente en una pantalla que ya existe. La aprobación pendiente de F03 se mantiene. |
| Desktop — [electron-main.mjs](/Users/danizal/getvocify-desktop/electron-main.mjs:129), [overlay.js](/Users/danizal/getvocify-desktop/renderer/overlay.js:1) y [preload.cjs](/Users/danizal/getvocify-desktop/preload.cjs:1) | `createOverlay()` ya crea una ventana transparente, sin marco, flotante y configurada para todos los espacios, incluido fullscreen. Hay `showOverlay()`/`hideOverlay()`, envío `shell:state` → `overlay:state`, estado Live/Idle, última línea de transcripción, Stop y retorno a la ventana principal. | F12 amplía este overlay y su puente de estado. Falta integrar sugerencia respaldada, estado del checklist y ciclo de vida del meeting. Se interpreta «una sola pastilla» como reutilizar esta ventana nativa existente, sin crear otra ventana de asistencia. Su visibilidad con la app minimizada y en fullscreen se verificará durante la implementación. |

## 3. Cimientos y contratos compartidos

### 3.1 Separar tres conceptos que hoy se mezclan

- **Origen de captura:** desktop, extensión, WhatsApp, web o llamada importada.

- **Tipo físico de interacción:** llamada, meeting, visita o nota de voz.

- **Tipología comercial:** cold calling, cualificación, discovery, cierre u otra configurada por la empresa.

La tipología comercial es un dato del playbook. Añadir una nueva no debe exigir modificar un enum de código.

No se crea una segunda tabla `Interaction` que duplique memos. Se amplía el memo existente. Origen: D §2 y P §5.1.2.

### 3.2 F0 + F0.1: inteligencia tipada y evidencia

La especificación completa y las tareas están en [plan03: F0/F0.1](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/03-f0-f0.1-inteligencia-y-jobs.md). Mantiene todos los campos, reglas y pruebas de la versión anterior. Produce C04 y C05; no construye los consumidores posteriores.

### 3.3 Trabajos en segundo plano e interfaces de integración

Los contratos [C04–C05](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-contracts.md) fijan revisión, evidencia, claim y protección contra resultados tardíos. Los jobs por memo viven en 039; importaciones 040, ejecuciones diarias 043 y entregas 048 conservan identidad/estado propios con las mismas garantías, sin crear memos ficticios ni una cola polimórfica innecesaria. Followup conserva su lease PF.

El [plan de integración](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-integration-and-gates.md) resuelve anticipaciones entre features y establece qué evidencia debe entregar cada productor antes de activar consumidores.

### 3.4 CRM: interfaces pequeñas y resultados honestos

Ampliar la capa existente de proveedores con capacidades separadas:

- Lectura de contexto de contacto/deal.

- Listado paginado de contactos y tareas asignadas.

- Lectura de actividad y correo asociado.

- Escritura de tareas/notas y actualización confirmada.

- Registro de meeting acordado.

- Lectura del resultado real de deals.

Toda referencia CRM incluye `connection_id`, tipo de objeto e identificador externo. Nunca se mezclan IDs de dos conexiones.

Las lecturas deben devolver, además de datos:

- `complete`, `partial`, `forbidden` o `unavailable`.

- Momento de actualización.

- Cursor de paginación cuando corresponda.

**Una lista vacía por error o permiso no significa ausencia de actividad.** No se generarán afirmaciones como «no respondió» con una lectura incompleta.

El mapeo entre comerciales Vocify y responsables CRM reutiliza el mecanismo de HubSpot y lo extiende a Pipedrive. La coincidencia por email puede proponer una asociación; una asociación ambigua requiere selección del administrador.

### 3.5 Permisos y conservación de datos

- Los roles existentes son `owner`, `admin` y `member`; no se inventa un rol `manager`.

- `owner/admin`: configuración compartida y lectura de equipo.

- `member`: resultados propios y acciones autorizadas sobre sus registros.

- El backend determina empresa y usuario desde la sesión, nunca desde un `company_id` confiado al cliente.

- Las tablas nuevas llevan `company_id`; las que contienen trabajo individual, también `user_id`.

- La empresa original de los nuevos memos queda persistida. Los datos históricos cuya empresa no pueda establecerse con evidencia no se incorporan automáticamente a agregados de equipo.

- RLS como segunda barrera. Los endpoints deben comprobar permisos aunque utilicen el cliente `service_role`.

- Cachés web, desktop y extensión se particionan por usuario, empresa y conexión; se limpian al cerrar sesión.

### 3.6 Migraciones previstas

La última migración existente es la 036. Para esta secuencia se reservan:

| Migración | Cambio |
|---|---|
| `037_memo_capture_context.sql` | Identificador de captura, empresa original, inicio real, metadatos de captura y origen desktop. Índice único de captura por usuario. |
| `038_memos_followup.sql` | Migración de PF, renumerada porque 037 queda ocupada. |
| `039_memo_intelligence_jobs.sql` | Tipo de interacción, revisión de inteligencia y trabajos recuperables. |
| `040_company_playbooks.sql` | Tipologías, playbooks, versiones, entradas y trabajos de importación. |
| `041_copilot_web_sessions.sql` | Aislamiento de sesiones web, turnos idempotentes y operaciones confirmadas. |
| `042_contact_priority_context.sql` | Caché de contexto CRM, mapeos de responsables y parámetros de priorización. |
| `043_action_signals.sql` | Señales, estados, aplazamiento, versiones de acciones y ejecuciones diarias. |
| `044_interaction_annotations_patterns.sql` | Notas temporales y hechos de objeción/respuesta por interacción. |
| `045_memo_scores.sql` | Resultado de scoring y versión del playbook utilizada. |
| `046_meeting_proposals.sql` | Propuesta y decisión de meeting; nuevos tipos de escritura en `crm_updates`. |
| `047_post_interaction_briefs.sql` | Brief persistido y preferencias de disponibilidad. |
| `048_reports_notifications.sql` | Preferencias, informes, entregas y campana. |
| `049_team_outcomes.sql` | Instantáneas de resultados CRM necesarias para win-loss. |

Actualizar `full_reset.sql` y la documentación de esquema junto con cada migración, preservando los valores permitidos que ya existan.

Las migraciones son aditivas. La desactivación de una funcionalidad no elimina sus datos.

## 4. Orden único de ejecución

| Orden | Entrega | Dependencia que justifica su posición |
|---|---|---|
| 1 | [**F01 — Captura desktop, transcripción y distribución**](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/01-f01-captura-desktop.md) | Confirma la entrada real de meetings, preserva sus evidencias e introduce el mínimo kernel que necesita `<v-transcript>`. Incluye distribución macOS, con firma/publicación condicionadas a las decisiones de §6. |
| 2 | [**F02 — Follow-up**](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/02-f02-followup.md), completando PF sobre el kernel de F01 | Reutiliza tokens, base de componentes y sincronización ya introducidos para la transcripción; añade follow-up sin reconstruir el kernel. No necesita la nueva inteligencia. |
| 3 | [**F0 + F0.1 — Inteligencia tipada, Jev y trabajos recuperables**](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/03-f0-f0.1-inteligencia-y-jobs.md) | Contrato común para las funcionalidades posteriores. |
| 4 | [**F08 — Playbooks**](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/04-f08-playbooks.md) | Proporciona el marco que necesitarán scoring y asistencia. |
| 5 | [**F07 — Ask Vocify**](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/05-f07-ask-vocify.md) | Reutiliza el loop y completa las lecturas CRM que también necesitará «Hoy». |
| 6 | [**F04 — Priorización**](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/06-f04-priorizacion.md) | Produce candidatos ordenados usando inteligencia y contexto CRM. |
| 7 | [**F05 — Motor «Hoy»**](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/07-f05-hoy.md) | Convierte la información disponible en señales persistentes y reconciliadas. |
| 8 | [**F06 — Tareas inteligentes y acciones**](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/08-f06-acciones-y-cola.md) | Completa la experiencia de actuar sobre esas señales. |
| 9 | [**F03 — Preparación previa, condicionada**](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/09-f03-preparacion.md) | Consume la información anterior. Si sigue pendiente de aprobación, se registra bloqueada y se prepara F10; ejecutar F10 requiere registrar la suspensión de F03 y comprobar que no depende de ella, conforme a §5. |
| 10 | [**F10 — Objeciones y notas**](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/10-f10-objeciones-y-notas.md) | Completa la clasificación y el contexto humano antes de evaluar calidad. |
| 11 | [**F09 — Scoring**](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/11-f09-scoring.md) | Ya dispone de playbook, evidencia y objeciones contextualizadas. |
| 12 | [**F14 — Meeting booked**](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/12-f14-meeting-booked.md) | Añade el resultado verificable y su traslado aprobado al CRM. |
| 13 | [**F11 — Brief posterior**](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/13-f11-brief-posterior.md) | Resume resultados que ya están calculados. |
| 14 | [**F12 — Checklist y ayuda en meetings**](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/14-f12-asistencia-live.md) | Reutiliza captura, playbook, evidencia y componentes compartidos. |
| 15 | [**F13 — Reporting al comercial**](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/15-f13-reporting.md) | Consolida actividad, coaching y resultados existentes. |
| 16 | [**F15 — Dashboard de equipo**](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/16-f15-equipo.md) | Agrega las funcionalidades anteriores sin depender de datos simulados. |

Cada entrega termina con sus pruebas, revisión y verificación de la superficie afectada. No se inicia otra funcionalidad para ocultar un criterio pendiente de la anterior. Una suspensión por decisión externa se distingue de una entrega completada y se trata mediante §5; nunca se solapan dos implementaciones.

**Dependencia adelantada por A1:** para entregar `<v-transcript>` dentro de F01 se adelantan de PF las tareas 2 y 3 (tokens/kernel) y la parte de la tarea 5 que distribuye los módulos presentes. F01 crea solo los estilos de transcripción en la hoja compartida; F02 añade la tarea 4 de follow-up y completa sus integraciones. Se ejecutan las pruebas correspondientes en cada entrega, sin duplicar cimientos ni crear una entrega número 17.

**Rutas de desktop:** las citas de auditoría apuntan al repo hermano porque ahí está hoy el código. Después de importar mediante PF tarea 1, todos los cambios previstos se realizan en `/Users/danizal/getvocify/desktop/` conservando sus rutas relativas, incluido el workflow adaptado a ese directorio. No se mantienen dos fuentes editables del desktop.

---

### 4.1 Planes ejecutables y contratos de entrada/salida
| Orden | Plan | Dependencias de código | Produce | Migración |
|---|---|---|---|---|
| 1 | [F01](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/01-f01-captura-desktop.md) | Código existente | C01, C02 | 037_memo_capture_context.sql |
| 2 | [F02](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/02-f02-followup.md) | F01 | C03 | 038_memos_followup.sql |
| 3 | [F0-F0.1](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/03-f0-f0.1-inteligencia-y-jobs.md) | F01 | C04, C05 | 039_memo_intelligence_jobs.sql |
| 4 | [F08](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/04-f08-playbooks.md) | F0-F0.1 | C06 | 040_company_playbooks.sql |
| 5 | [F07](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/05-f07-ask-vocify.md) | Código existente | C07, C08 | 041_copilot_web_sessions.sql |
| 6 | [F04](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/06-f04-priorizacion.md) | F0-F0.1, F07 | C09 | 042_contact_priority_context.sql |
| 7 | [F05](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/07-f05-hoy.md) | F0-F0.1, F04 | C10 | 043_action_signals.sql |
| 8 | [F06](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/08-f06-acciones-y-cola.md) | F05 | C11 | Sin nueva migración; usa campos de acción/undo previstos en 043 de F05. |
| 9 | [F03](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/09-f03-preparacion.md) | F05, F08, F07 | C12 | Ninguna; cache por revisión, no tabla nueva. |
| 10 | [F10](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/10-f10-objeciones-y-notas.md) | F01, F0-F0.1 | C13 | 044_interaction_annotations_patterns.sql |
| 11 | [F09](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/11-f09-scoring.md) | F08, F10, F0-F0.1 | C14 | 045_memo_scores.sql |
| 12 | [F14](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/12-f14-meeting-booked.md) | F0-F0.1, F07 | C15 | 046_meeting_proposals.sql |
| 13 | [F11](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/13-f11-brief-posterior.md) | F09, F10, F14, F0-F0.1 | C16 | 047_post_interaction_briefs.sql |
| 14 | [F12](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/14-f12-asistencia-live.md) | F01, F0-F0.1, F08 | C17 | Sin nueva migración; estado final usa intelligence.playbook_observations/C04 y snapshot de captura. |
| 15 | [F13](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/15-f13-reporting.md) | F11, F07 | C18 | 048_reports_notifications.sql |
| 16 | [F15](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/16-f15-equipo.md) | F13, F09, F10, F14, F07 | C19 | 049_team_outcomes.sql |

La dependencia es de contrato, no de numeración: F04 usa el acuerdo de F0 antes de la propuesta CRM F14; F05 usa hechos de objeción F0 antes de la proyección F10; F13 obtiene outcomes mínimos antes de la historia F15. Estos enlaces están desarrollados y probados en el plan de integración.

## 5. Ejecución, pruebas y salida a producción

### Un subagente por entrega, con contexto acotado — B1

Las 16 filas de §4 son las unidades de ejecución: F01, F02, F0/F0.1, F08, F07, F04, F05, F06, F03, F10, F09, F14, F11, F12, F13 y F15. F0/F0.1 comparten una sesión porque producen el mismo contrato. F01 incluye distribución; no se fragmenta silenciosamente en una entrega omitida.

El coordinador lanza **un subagente implementador nuevo por entrega**, con contexto limpio (`fork_turns="none"` si la herramienta permite controlarlo), y conserva la visión de dependencias. Solo uno implementa a la vez. No se envía a cada agente el documento completo ni la conversación histórica; tampoco se le pide deducir restricciones que quedaron fuera de su paquete.

**Paquete de entrada obligatorio, preparado antes de despachar:**

1. Spec completo de esa feature: propósito, auditoría, decisiones, backend, frontend, estados, criterios de aceptación y edge cases. Para F0/F0.1, §3.2–3.3 y sus pruebas.
2. Restricciones globales y reglas de permisos/motion aplicables, copiadas expresamente; incluir el protocolo de bloqueo y la prohibición de empezar otra feature por su cuenta.
3. Contratos de dependencias realmente entregadas: nombres, entradas/salidas, revisiones, rutas y referencias a commits, junto con limitaciones conocidas. El subagente no recibe contratos planeados como si ya existieran.
4. Archivos autorizados, mapa de responsabilidades y migración exacta si aplica. Las rutas del desktop se resuelven según §4 después de su importación.
5. Pruebas de comportamiento y flujo real a verificar, con datos de prueba autorizados, comandos aplicables y criterios que producen fallo. Incluir al menos el caso sin datos y el parcial/ambiguo de la matriz B3.
6. Decisiones confirmadas y bloqueos abiertos con su ID. Una aprobación de F03 o de distribución se adjunta como decisión explícita, no se infiere de esta descripción de trabajo futuro.

Los planes fuente ya están en [el índice de entregas](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/README.md); cada subagente recibe el suyo y las secciones Cxx pertinentes, sin todo el maestro. Durante la implementación futura, guardar la revisión concreta del paquete y su informe en `/Users/danizal/getvocify/docs/superpowers/deliveries/<ID>/spec.md` y `report.md`, donde `<ID>` es la entrega real, por ejemplo `F01` o `F0-F0.1`. Estos archivos se crearán al ejecutar, no se generan ahora como sesiones supuestamente terminadas.

**Informe de salida obligatorio:** comportamiento entregado, archivos/commits, migraciones aplicadas, pruebas ejecutadas con resultado, evidencia de verificación real, edge cases nuevos y su resolución, bloqueos con impacto y trabajo pendiente. «Tests verdes» sin indicar qué comportamiento se probó no es un informe suficiente.

El coordinador contrasta ese informe con todos los criterios y revisa SOLID: separación de responsabilidades, reutilización de contratos, sustitución de proveedores, interfaces limitadas al consumidor y efectos aislados de reglas. Los hallazgos vuelven al mismo subagente para corregir; no se abren otra feature ni una reescritura general. Solo tras aceptar la entrega o documentar una suspensión externa conforme a B2 se habilita la siguiente sesión.

Si no hay herramienta de subagentes, el equivalente es una sesión independiente con ese mismo paquete e informe. No se sustituye por ejecutar las 16 features dentro de una sola conversación acumulada ni por implementarlas en paralelo.

### Ciclo de trabajo por entrega

- [ ] Seleccionar la siguiente entrega de la secuencia y comprobar sus dependencias.

- [ ] Escribir primero pruebas de comportamiento para reglas, permisos y transiciones nuevas.

- [ ] Confirmar que fallan por la capacidad ausente.

- [ ] Implementar el mínimo necesario y ejecutar las pruebas específicas.

- [ ] Buscar edge cases no listados a partir de los datos y flujos reales: ausencia, parcialidad, ambigüedad, cambios de identidad, permisos y reintentos que afecten a esta feature. Diseñar y resolver cada caso dentro de la misma entrega, añadiendo primero una prueba que falle y después la corrección. Si exige una decisión de producto, registrar el bloqueo según B2; anotarlo sin solución ni bloqueo no permite cerrar.

- [ ] Ejecutar regresiones de los módulos afectados.

- [ ] Verificar la experiencia real antes de cerrar la entrega.

- [ ] Registrar evidencia, migraciones aplicadas y limitaciones.

- [ ] Revisar cumplimiento de SOLID, restricciones globales y todos los criterios de aceptación, incluidos los edge cases descubiertos. Registrar el caso, decisión y prueba en el informe y en el mismo commit/PR de la entrega.

- [ ] Crear un commit revisable de esa entrega, añadiendo archivos explícitamente.

- [ ] Devolver el informe al coordinador y obtener su revisión antes de despachar la siguiente entrega. Esta revisión técnica no sustituye las decisiones de producto que correspondan a Dani.

No comenzar con una reorganización general del repositorio.

### Protocolo ante bloqueos de producto o acceso — B2

**Nunca esperar indefinidamente una respuesta humana dentro de una entrega.** Ausencia de aprobación de F03, credenciales de distribución no confirmadas, un permiso externo imprescindible o una regla de producto contradictoria sí pueden bloquear una parte. Un test rojo, un bug, un conflicto de implementación o un comando mal configurado exigen diagnóstico y corrección; no son excusas para aparcar la feature como bloqueo de producto.

1. **Delimitar el bloqueo.** Crear un ID, por ejemplo `F01-DISTRIBUCION`, en el informe de la entrega. Registrar hecho comprobado, decisión/dato faltante, responsable, opciones con consecuencias, recomendación y criterios/archivos afectados. Un hallazgo ya resuelto como el overlay existente de F12 no se vuelve a escalar como decisión pendiente.
2. **Solicitar únicamente la decisión necesaria.** Comunicar una pregunta concreta y dejarla pendiente. No solicitar de nuevo autorización ya concedida, no fingir una respuesta por el tiempo transcurrido y no detener trabajo que no dependa de ella.
3. **Continuar dentro de la entrega.** Separar tareas dependientes e independientes y completar estas últimas con sus pruebas. Ejemplo: sin Developer ID confirmado se pueden terminar captura, transcripción, diseño del DMG y build interno; no se publica una versión como firmada.
4. **Si no queda trabajo independiente, preparar la siguiente entrega viable.** Revisar su spec, contratos y archivos; preparar su paquete de contexto y casos de aceptación. Esta preparación no introduce código de otra feature, no habilita funcionalidades y no se presenta como una implementación terminada.
5. **Resolver el límite de secuencia.** El coordinador puede registrar la entrega como `bloqueada por decisión externa` y suspender su ejecución, con todos los criterios pendientes visibles. Puede entonces habilitar una entrega independiente cuyo paquete demuestre que no consume la parte bloqueada. Se registra expresamente la excepción en la cola; no hay dos subagentes implementando ni se marca la anterior como completa. Si depende de la parte bloqueada, solo se prepara y se informa del bloqueo real.
6. **Persistir antes de salir.** El commit/PR de la entrega incorpora el informe con bloqueos y edge cases, resultados comprobados y la siguiente acción. Si no hubo código que commitear, el registro documental sigue siendo parte de esa entrega. No dejar el único registro en el chat ni guardar secretos en él.
7. **Reanudar con la respuesta.** Incorporar la decisión al spec e informe, volver a la entrega suspendida cuando corresponda según dependencias y comprobar lo que estaba bloqueado. La suspensión no elimina sus criterios ni permite publicar un resultado parcial como completo.

| Ejemplo | Trabajo permitido mientras falta la decisión | Qué sigue bloqueado |
|---|---|---|
| F03 sin formato/ubicación aprobados | Refinar la propuesta, verificar contratos disponibles y preparar F10. Tras suspensión registrada, F10 puede ejecutarse porque no consume F03. | Construir/activar `<v-brief>` o convertirlo en dependencia de la cola. |
| F01 sin Developer ID | Captura, continuidad de transcripción, DMG con marca y paquete de prueba; preparar F02. Solo si los contratos de captura/kernel ya están verificados, F02 puede habilitarse tras suspensión registrada. | Firma/notarización real y publicación del instalador como distribuible. |
| Un permiso CRM imprescindible no confirmado | Probar comportamiento autorizado/denegado y UI de cobertura parcial con fixtures; completar fuentes ya disponibles. | Afirmar cobertura completa o habilitar la operación real que necesita el permiso. |
| Nuevo edge case altera el significado del producto | Documentar reproducción, opciones y prueba del comportamiento seguro ya acordado; avanzar otras tareas de esa misma feature. | Inventar la regla, eliminar el test o dar la entrega por cerrada. |

Estados del informe: `en preparación`, `en ejecución`, `bloqueada por decisión externa`, `en revisión`, `completa`. Son estados de seguimiento del plan; no nuevos estados de base de datos de la aplicación. El informe final de la cola distingue entregas completas, suspendidas y pendientes, sin sumar las suspendidas como éxitos.

### Cobertura de ausencia y parcialidad por entrega — B3

Esta matriz es el mínimo que entra en el paquete de cada subagente y se prueba con el mismo rigor que el camino feliz. Complementa los casos de cada feature; no sustituye la tabla de pruebas por área que ya existía ni autoriza inventar datos de producción.

| Entrega | Sin datos todavía | Datos parciales o ambiguos |
|---|---|---|
| F01 | Captura sin voz: estado de escucha, sin memo de conversación inventado. | Provisional no confirmado, un canal ausente y audio incompleto se conservan con su limitación; no se certifica transcripción final ficticia. |
| F02 | Buzón/no respuesta o contenido insuficiente no produce borrador genérico; estado no disponible de PF. | Destinatario ausente, error de generación o borrador editado: conservar lo válido y explicar el impedimento; no afirmar envío. |
| F0/F0.1 | Memo antiguo sin `intelligence` sigue funcionando; evidencia ausente produce desconocido. | Clasificación de baja confianza o sin respuesta conserva `partial/unavailable` y no fabrica booleanos. |
| F08 | Settings muestra onboarding y permisos adecuados sin playbook publicado. | Importación fallida, borrador y reglas contradictorias no reemplazan la versión activa. |
| F07 | Conversación nueva y consulta sin resultados muestran estados distintos. | CRM parcial y turno `202`/lectura fallida mantienen contexto e idempotencia, sin respuestas o streaming inventados. |
| F04 | No candidatos, no asignación y CRM sin conectar tienen copy/acción propios. | Historial incompleto no significa nunca llamado; varios deals no mezclan motivos. |
| F05 | Distinguir empresa nueva de cero pendientes con cobertura completa; mostrar tareas manuales aunque no haya memos. | Mantener señales ante una fuente caída, con cobertura por origen y fecha. |
| F06 | Cola agotada conserva acceso útil y foco; no deja una tarjeta fantasma. | Sin teléfono/permisos se ofrece destino real; `409`, deshacer y refetch mantienen estado y animación coherentes. |
| F03 | Contacto sin historial muestra «Sin interacciones registradas todavía» y acceso a información CRM existente. | Historial inaccesible, deal ambiguo o cambio de contacto no mezclan briefs ni inventan conversación previa. Solo tras aprobación. |
| F10 | Análisis completo sin objeciones lo indica; no concede crédito por superarlas. | Respuesta no atribuible queda `unknown`; una nota sin turno exacto conserva su offset sin falsa cita. |
| F09 | Playbook/conversación ausentes dan motivo explícito y `null`, nunca cero. | Contradicción del playbook, tipología incierta y cobertura parcial conservan desconocidos y pueden impedir nota global. |
| F14 | Sin acuerdo no hay propuesta CRM; procesamiento pendiente no se confunde con ausencia. | Hora/zona ambigua pide revisión; un resultado de escritura incierto se reconcilia antes de repetir. |
| F11 | Interacción inelegible produce `skipped`, no spinner perpetuo. | `partial`, `unavailable` y `failed` tienen acciones diferentes; ausencia de audio mantiene cita sin reproducción. |
| F12 | Sin playbook/respaldo, overlay mantiene captura y no fabrica ayuda. | Canal desconocido, respuesta tardía y versión de otra captura se ignoran; solo evidencia válida marca pasos. |
| F13 | Periodo sin actividad muestra conteos verificables y ninguna evaluación inventada. | Fuente desconectada se representa como no disponible; email y página usan la misma instantánea parcial. |
| F15 | Onboarding y filtros vacíos se diferencian; sin playbook no hay adherencia. | Deals con múltiples responsables, monedas y fuentes parciales conservan atribución, denominadores y cobertura explícitos. |

Cada edge case nuevo se añade al spec local y al informe con reproducción, decisión, resultado esperado y referencia a su test. El test debe demostrar el comportamiento, no copiar la implementación. Si la decisión está bloqueada, registrar el criterio pendiente y aplicar B2; la feature permanece sin cerrar.

### Pruebas por área

| Área | Casos obligatorios |
|---|---|
| Captura | Reintento, reinicio, desconexión, audio parcial, conservación de origen y reproducción. |
| Jev/inteligencia | Ausencia de respuesta, baja confianza, categorías inválidas, evidencia no existente y reunión larga. |
| Proveedores CRM | Mismos contratos en HubSpot/Pipedrive; paginación; permiso denegado; error distinto de lista vacía. |
| Ask Vocify | Confirmación ligada al contacto, operación repetida, recarga, audio y denegación entre empresas. |
| «Hoy» | Casos de S más concurrencia, zona horaria, aplazamiento, deshacer y tareas manuales. |
| Coaching | Objeción frente a obstáculo, llamada fácil, ironía anotada, playbook ausente y baja cobertura. |
| Meeting booked | Propuesta sin acuerdo, cambio de hora, fecha ambigua, horario de verano y duplicación CRM. |
| Asistencia en vivo | Sin respaldo, respuesta tardía, categoría repetida, intervención del comercial y cambio de sesión. |
| Reporting/equipo | Duplicación, filtros, permisos, denominadores, monedas y resultados CRM ausentes. |

Pruebas nuevas se agrupan bajo `/Users/danizal/getvocify/backend/tests/` por dominio: `intelligence`, `playbooks`, `crm_copilot`, `hoy`, `coaching`, `meetings`, `reporting` y `team_insights`.

Las reglas compartidas de interfaz usan `node --test`, siguiendo el plan existente. No incorporar otro framework de pruebas de frontend como requisito de este proyecto.

Comandos de referencia:

```bash

cd /Users/danizal/getvocify/backend

.venv/bin/python -m pytest tests/intelligence tests/hoy -q

```

```bash

cd /Users/danizal/getvocify

make test-js

npm run build

make check-generated

```

`make check-generated` estará disponible después de ejecutar la tarea correspondiente de PF.

### Evaluación de IA

Seguir M §1 y §3:

- Dataset real autorizado y anonimizado, con casos positivos, negativos y ambiguos.

- Cada prompt tiene versión y resultados guardados.

- Medir falsos positivos de meeting booked, exactitud temporal, clasificación de objeciones, fidelidad de evidencia y acuerdo del scoring con revisión humana.

- Los casos críticos definidos —hora inventada, cita inexistente, contacto incorrecto y escritura sin confirmación— deben pasar todos antes de habilitar la funcionalidad.

- No aceptar una evaluación automática como sustituto de la revisión humana de estos casos.

### Verificación de interfaz

En cada integración del kernel compartido, comprobar las restricciones globales de S §2.3 y §7: carga sin saltos de layout, cambios de altura controlados, `prefers-reduced-motion`, contraste ≥4.5:1 y foco visible al recorrer los controles con teclado. Esta comprobación aplica también a F02, F05, F09 y F12; no queda limitada a la cola F06.

Para cada cambio web:

- Registrar intención del flujo.

- Ejecutar `reticle_act_and_wait` con una consecuencia explícita o `reticle_assert`.

- Guardar el flujo y revisar red, consola y estado cuando corresponda.

- `unknown` y `no-fault` no cierran la entrega.

- Añadir señales y referencias de estado útiles al archivo de instrumentación al tocar esos flujos; la instrumentación actual no registra stores.

- En desktop y extensión, verificar también captura, navegación e integración nativas. Un resultado sobre una tarjeta web no prueba una grabación Electron.

### Despliegue

- Aplicar primero migraciones compatibles.

- Habilitar cada funcionalidad por empresa durante pruebas con founders y betas.

- Mantener interruptores independientes para follow-up, inteligencia, scoring, asistencia y reporting.

- Registrar fallos, duración, revisión de entrada y cobertura sin volcar conversaciones completas a logs.

- Ante un fallo, desactivar el consumidor afectado conservando captura, revisión y sincronización CRM.

- Medir durante dos semanas: uso del follow-up, acciones sobre «Hoy», cobertura de coaching, correcciones de meeting booked y apertura de informes.

## 6. Decisiones pendientes y límites de ejecución

| Punto | Estado y tratamiento |
|---|---|
| Preparación previa | **Aprobada el 22 sep 2026, formato mínimo.** Como mucho tres hechos. Sin conversación, o conversación que no dejó nada, una frase. Extensión sobre el contacto HubSpot; dashboard y escritorio repiten el mismo texto. Detalle en `docs/superpowers/plans/2026-09-22-vocify-v1/00-decisiones.md`. |
| Developer ID y distribución macOS | **Fuera de esta rama.** No se firma ni se publica el instalador. El DMG interno sin firmar es el artefacto. No se vuelve a preguntar. |
| Descarga del desktop | **Pendiente de Dani.** Elegir dashboard, landing o ambos y el alojamiento/acceso del artefacto. Propuesta documentada: dashboard primero, reemplazando el enlace actual al repo en RecordPage. La revisión local confirmó ese enlace, no una distribución pública existente. |
| Tracking de skills / TTR | Sin definición de producto. Fuera de implementación V1; no crear métricas ni tablas preventivas. |
| Scorecards comparativas | Sin definición y fuera del alcance actual. No confundir con filtros por comercial. |
| Scopes HubSpot | Gap concreto identificado para contenido de email. Incorporar solo los permisos exigidos por las operaciones verificadas; no pedir un paquete genérico de permisos ampliados. |
| Permisos instalados Pipedrive | Confirmarlos mediante la conexión autorizada durante la implementación. El código local no demuestra que `mail:read` esté concedido. |
| Etapa «meeting booked» | Configuración por empresa. Sin mapeo explícito, registrar actividad y acuerdo, sin mover etapas. |
| Patrones «que funcionan» | V1 usa playbook publicado como respaldo. Automatizar la declaración de patrón ganador requiere una definición posterior; los hechos ya pueden almacenarse y analizarse. |

Los valores de 7 tarjetas y 10 días proceden de S. La ventana de 14 días para contactos recientes y los horarios propuestos son valores iniciales configurables, que deben identificarse como tales en configuración y documentación.

**Decisiones de diseño cerradas en esta revisión del plan, distintas de las decisiones de negocio pendientes:** F09 evalúa ejecución sin bonus numérico por resultado comercial; F14 muestra meeting booked de forma asíncrona en revisión, no en el overlay en vivo; F12 amplía la ventana flotante existente; F13 y F15 usan los layouts de tablas/gráficos definidos en sus specs. Estas elecciones son explícitas y revisables en el documento; no se atribuyen a una aprobación previa de Dani.

### 6.1 Control de cobertura de las instrucciones de actualización

Las casillas de esta sección significan **incorporado y revisado en el plan**, no implementado ni probado en la aplicación. Fuente: [PLAN_UPDATE_INSTRUCTIONS_VOCIFY.md](/Users/danizal/getvocify/docs/PLAN_UPDATE_INSTRUCTIONS_VOCIFY.md). Cada requisito se desarrolla en la feature correspondiente; este índice permite localizarlo.

- [x] **A0 — Auditoría de superficies:** §2 mantiene pantallas reales, costes de integración y hallazgo del overlay; [F01](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/01-f01-captura-desktop.md) añade auditoría del instalador/enlace real y [F05](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/07-f05-hoy.md)/[F12](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/14-f12-asistencia-live.md) conservan su alcance concreto.
- [x] **A_principio — Kernel accesible y sin saltos:** restricciones globales y verificación de interfaz de §5; aplicación a todas las features que consumen `shared/ui/`.
- [x] **A1 — Transcripción:** [F01](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/01-f01-captura-desktop.md), «Transcripción continua», define reconciliación provisional/definitiva, componente compartido, scroll, motion, archivos y pruebas; §4 adelanta el kernel necesario para eliminar la dependencia circular con [F02](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/02-f02-followup.md).
- [x] **A2 — Distribución:** [F01](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/01-f01-captura-desktop.md), «Distribución macOS», define DMG/ZIP, marca, firma/notarización, prueba de instalación y enlace; §6 identifica decisiones de Developer ID y descarga sin asumirlas aprobadas.
- [x] **A3 — Preparación:** [F03](/Users/danizal/getvocify/.worktrees/vocify-v1/docs/superpowers/plans/2026-09-22-vocify-v1/09-f03-preparacion.md) queda en formato mínimo, aprobado el 22 sep 2026. Las cuatro filas fijas se retiran.
- [x] **A4 — Resultado y score:** [F09](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/11-f09-scoring.md) separa el resultado real del `value` numérico y precisa el caso de un paso del proceso frente a un resultado externo; añade comprobación de invariancia ante cambios de resultado CRM.
- [x] **A5 — Objeciones por superficie:** [F10](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/10-f10-objeciones-y-notas.md) contiene la tabla de captura/revisión/equipo y sus relaciones con [F11](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/13-f11-brief-posterior.md)/[F12](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/14-f12-asistencia-live.md)/[F15](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/16-f15-equipo.md), respetando la restricción de asistencia nueva solo para meetings.
- [x] **A6 — Overlay:** [F12](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/14-f12-asistencia-live.md) reutiliza ventana, renderer, show/hide e IPC existentes; incorpora sugerencia respaldada, progreso del checklist, tamaño y limpieza, sin duplicar la tarjeta en la principal.
- [x] **A7 — Priorización vacía:** [F04](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/06-f04-priorizacion.md) especifica copy y acción para cero candidatos y los distingue de onboarding, conexión ausente y lectura parcial; añadido al DoD.
- [x] **A8 — Salida de tarjeta:** [F06](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/08-f06-acciones-y-cola.md) define altura medida, opacidad bajo reducción de movimiento, restitución/deshacer, errores, foco y comprobación explícita.
- [x] **A9 — Chat:** [F07](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/05-f07-ask-vocify.md) define panel y burbujas, espera real con `202` + polling, recuperación de turno, indicador de voz, temporizador y estado de transcripción editable.
- [x] **A10 — Onboarding playbook:** [F08](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/04-f08-playbooks.md) incluye aviso proactivo de Settings, checklist manual, permisos, borradores/importación y estado por tipología.
- [x] **A11 — Brief:** [F11](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/13-f11-brief-posterior.md) enumera `pending`, `partial`, `ready`, `skipped`, `unavailable` y `failed`, con copy, acciones y transiciones.
- [x] **A12 — Informe:** [F13](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/15-f13-reporting.md) define página diaria/semanal, tabla de métricas, gráfico semanal, equivalencia de email/campana y estados vacío/parcial.
- [x] **A13 — Meeting booked:** [F14](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/12-f14-meeting-booked.md) fija detección asíncrona posterior en revisión; explicita que no genera aviso en vivo ni escritura antes de aprobación.
- [x] **A14 — Equipo:** [F15](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/16-f15-equipo.md) define barras, tablas, filtros y drill-down de actividad, adherencia, objeciones, competidores y win-loss; sin ranking de comerciales.
- [x] **B1 — Sesiones aisladas:** §5 define las 16 entregas, paquete de contexto, subagente por entrega, informe, revisión y condiciones para habilitar la siguiente.
- [x] **B2 — Bloqueos:** §5 contiene protocolo completo, registro en commit/PR, avance independiente, preparación de siguiente entrega, suspensión explícita y reanudación sin fingir cierre.
- [x] **B3 — Casos sin datos/parciales:** [F04](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/06-f04-priorizacion.md)/[F05](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/07-f05-hoy.md)/[F09](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/11-f09-scoring.md)/[F15](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/16-f15-equipo.md) amplían el tratamiento; la matriz de §5 exige el mismo estándar a las 16 entregas.
- [x] **B3 — Hallazgos durante ejecución:** el ciclo de §5 obliga a detectar, diseñar, probar y resolver edge cases nuevos antes de regresiones/cierre, o registrarlos como bloqueo de producto con su criterio pendiente.
- [x] **B4 — Testing conservado:** tabla de pruebas por área, comandos y evaluación de IA conservados; los nuevos criterios UX se añaden en sus features sin debilitar los existentes.
- [x] **B5 — Migraciones conservadas:** §3.6 mantiene exactamente las 13 migraciones 037–049, su contenido y la regla de no eliminar datos al desactivar features.
- [x] **B6 — TDD + SOLID:** elevados a restricción global y revisión obligatoria de cierre en §5.

## 7. Resumen en lenguaje sencillo

Primero aseguraremos que las reuniones grabadas desde el ordenador llegan completas y pueden revisarse después, con una transcripción fluida que no parpadee al confirmar palabras. También prepararemos el instalador con marca y el recorrido de descarga; la distribución firmada queda condicionada a confirmar la cuenta y el canal de publicación. A continuación aparecerá el seguimiento listo para abrir en el correo, aprovechando la base compartida ya construida.

Después organizaremos la información que Vocify extrae de cada conversación y permitiremos que cada empresa cargue su proceso comercial. Esa base servirá para preguntar a Vocify, saber a quién merece la pena llamar y encontrar cada día una lista breve de acciones con su motivo.

La preparación previa queda propuesta para que la valides más adelante: su lugar principal sería la extensión, sobre el contacto de HubSpot justo antes de llamar, incluso cuando todavía no hay conversaciones registradas. El resto puede avanzar sin depender de esa decisión.

Luego añadiremos las notas durante la conversación, la clasificación de objeciones y la evaluación de cómo se siguió el proceso, distinguiendo una buena ejecución del simple hecho de conseguir una reunión. Las reuniones acordadas aparecerán después para revisar fecha y hora antes de trasladarlas al CRM.

Con esos resultados disponibles, construiremos el resumen posterior, con estados claros cuando siga procesándose o falten datos, y la ayuda opcional durante meetings en la ventana flotante que el desktop ya tiene. Por último llegarán informes legibles y una vista de equipo con tablas, gráficos y acceso a sus evidencias, utilizando información real que las entregas anteriores ya habrán generado.

Cada entrega la ejecutará una sesión dedicada, con pruebas y revisión antes de avanzar. Si falta una decisión, quedará registrada y se completará lo que sí pueda hacerse; ninguna espera dejará el trabajo abandonado ni convertirá una parte pendiente en una feature supuestamente terminada.
