# F04 — Priorización de contactos: plan ejecutable

> **Ejecución futura:** usar `executing-plans` dentro del subagente dedicado a esta entrega; la coordinación secuencial usa `subagent-driven-development`. Este documento es planificación, no una implementación ni una autorización para desplegar. Ninguna casilla de ejecución está completada.

**Objetivo:** Producir candidatos con motivo y cobertura, priorizando pain confirmado sin inventar contactos nunca llamados.

**Arquitectura:** Proveedor lee contexto; priority.py calcula reglas puras; UI representa ranking y estados vacíos. Ningún LLM decide el orden.

**Stack:** FastAPI/Python, Supabase/PostgreSQL, React 18/TypeScript y módulos JS compartidos; Electron/extensión cuando figuren entre las superficies de esta entrega.

**Posición:** 6 de 16. **Estado:** planificada; no iniciada.

**Navegación:** [plan maestro](/Users/danizal/getvocify/proposed_plan.md) · [contratos](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-contracts.md) · [integración y gates](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-integration-and-gates.md)

**Fuentes de esta entrega:** A: [Análisis de producto](/Users/danizal/getvocify/docs/PRODUCT_PLANNING_ANALYSIS_2026-09-21.md) · S: [Diseño Spine](/Users/danizal/getvocify/docs/superpowers/specs/2026-09-21-copilot-spine-design.md) · E: [Experiencia de producto](/Users/danizal/getvocify/docs/EXPERIENCIA_PRODUCTO.md).

## Entrada, salida y frontera de responsabilidad

| Tipo | Contrato de esta entrega |
|---|---|
| Recibe | C04 pain/commitments/meeting agreement; C08 contactos, tareas, historial y estado CRM. |
| Produce | C09 PriorityCandidate y GET /contact-priorities; caché con cobertura y mapeo de responsables. |
| Dependencias de código | [F0-F0.1](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/03-f0-f0.1-inteligencia-y-jobs.md), [F07](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/05-f07-ask-vocify.md) |
| Migración propia | 042_contact_priority_context.sql |
| No le corresponde | No persistir señales accionables (F05), resolver tarjetas (F06) ni esperar propuesta CRM de F14: F0 ya aporta meeting.agreed. |

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

## Feature: F04 — Priorización de contactos

**Fuente:** A §3.1; S §5; E §1.  

**Prioridad:** V1.

### En una frase

Vocify coloca primero los contactos con una razón clara para retomar la conversación y después los que aún no tienen llamadas registradas.

### Por qué (first principles)

Reduce el tiempo dedicado a decidir a quién llamar. La prioridad debe poder explicarse con información comercial, sin presentar un número opaco.

### Qué ya existe (auditoría)

- Pain points, conversaciones capturadas y estado CRM.

- F0 aporta evidencia, interés y acuerdos.

- Gap real: lista de candidatos completa, responsabilidad por comercial y reglas de prioridad.

### Backend

- Crear `/Users/danizal/getvocify/backend/app/services/hoy/priority.py`.

- Entrada: contactos accesibles, conversaciones, acuerdos de reunión, tareas y estado CRM.

- Salida: candidatos con `tier`, motivo, evidencia y momento de actualización.

- Reglas:

  - Tier 1: pain confirmado en una conversación reciente y sin reunión ya acordada ni deal cerrado.

  - Tier 2: sin llamadas registradas tras consultar las fuentes disponibles.

  - Los demás candidatos quedan detrás; no se inventa pain o interés.

- Valor inicial configurable de recencia: **14 días**. Es un parámetro de V1, no un hecho extraído del análisis.

- Una llamada futura expresamente acordada se muestra con su momento; no se invita a llamar antes.

- Si el historial está incompleto, no clasificar como «nunca llamado».

- Migración 042: caché por empresa/conexión/contacto, última lectura, cobertura de fuentes y mapeo de responsables.

- `GET /api/v1/contact-priorities`, paginado.

- Leer estado cerrado real desde el CRM; no inferirlo desde `meeting_booked`.

**SOLID:** priorización es una función separada del feed; proveedores obtienen datos; el cliente solo muestra el resultado.

### Frontend / Dashboard

- Sección inicial de candidatos en el inicio, posteriormente integrada en «Hoy».

- `useContactPriorities`.

- Una razón visible y una acción principal; no mostrar «Tier 1» como información protagonista.

- Copy: «Confirmó el problema de seguimiento. Quedó pendiente cuadrar la demo».

- El historial de `ActivityPanel` queda debajo o plegado.

#### Sin candidatos y cobertura parcial — A7 / B3

El bloque de prioridades dentro de `/Users/danizal/getvocify/src/pages/dashboard/DashboardHome.tsx` interpreta tanto `items` como la cobertura de fuentes. `useContactPriorities` no convierte error, carga o falta de asignación en una lista vacía válida.

| Situación | Mensaje y acción |
|---|---|
| Lectura completa, sin candidatos que requieran acción | «No hay contactos prioritarios ahora. Buen momento para prospectar». Acción «Abrir contactos en CRM». Al integrarse en F05, evitar mostrar además un segundo vacío redundante. |
| Empresa nueva, sin contactos asignados | «Todavía no hay contactos asignados para priorizar». Owner/admin: acceso al mapeo de responsables; member: «Revisa tu asignación con el administrador». No ofrecer una lista ficticia. |
| CRM sin conectar | «Conecta tu CRM para ver a quién contactar». Acción de configuración solo para quien tenga permisos. |
| Cobertura parcial o lectura fallida | Mostrar candidatos ya confirmados, fecha de actualización y «Falta parte del historial». Ofrecer reintento; si no hay ninguno confirmado, explicar que no se puede completar la lista. No usar el copy de lista vacía. |

Un contacto nuevo puede entrar en el grupo sin llamadas solo tras completar las lecturas disponibles; ausencia de memos Vocify por sí sola no demuestra ausencia de llamadas. Si hay varios deals, conservar el vínculo de cada motivo con su deal; no ocultar una oportunidad abierta porque otro deal del contacto esté cerrado. Una asignación ambigua se retiene fuera de la lista personal hasta resolverla, sin exponer registros de otro comercial.

### Criterio de aceptación (Definition of Done)

- [ ] Pain confirmado reciente precede a contacto sin llamadas registradas.

- [ ] Una reunión ya acordada evita proponer otra llamada de captación.

- [ ] Un deal cerrado no aparece como oportunidad activa.

- [ ] Cada comercial recibe candidatos dentro de su asignación.

- [ ] Información incompleta se distingue de ausencia de llamadas.

- [ ] Cambiar un dato fuente cambia la prioridad de manera explicable.

- [ ] Cero candidatos con cobertura completa muestra el copy y la acción definidos; onboarding sin contactos y error CRM tienen estados distintos.

- [ ] Un historial parcial no produce «nunca llamado». Con varios deals, el motivo remite al deal correcto y no duplica una misma acción.

### Riesgos / edge cases conocidos

Contactos duplicados, múltiples deals, responsables sin mapear y actividades externas no accesibles. La identidad incluye la conexión CRM, no solo el ID del contacto.

## Mapa de archivos y responsabilidades

| Acción futura | Ruta | Responsabilidad |
|---|---|
| Crear | `/Users/danizal/getvocify/backend/app/services/hoy/priority.py` | Reglas puras de candidato. |
| Crear | `/Users/danizal/getvocify/backend/app/services/hoy/context.py` | Lecturas/cache por tenant/conexión/contacto. |
| Crear | `/Users/danizal/getvocify/backend/app/api/contact_priorities.py` | Endpoint paginado. |
| Crear | `/Users/danizal/getvocify/backend/tests/hoy/test_priority.py` | Ranking, ausencia y parcialidad. |
| Crear | `/Users/danizal/getvocify/backend/migrations/042_contact_priority_context.sql` | Cache y owner mappings. |
| Crear | `/Users/danizal/getvocify/src/features/today/hooks/useContactPriorities.ts` | Consulta scoped. |
| Crear | `/Users/danizal/getvocify/src/features/today/components/ContactPriorities.tsx` | Motivo/acción y estados. |
| Modificar | `/Users/danizal/getvocify/src/pages/dashboard/DashboardHome.tsx` | Primer acceso a candidatos. |

Los archivos marcados «Crear» todavía no existen por esta planificación. Los marcados «Modificar» pueden ser producidos por una dependencia; su procedencia debe quedar indicada. Los tests y fixtures se crean en ejecución, nunca se confunden con datos de producción.

## Tareas secuenciales con ciclo TDD

Cada tarea termina con evidencia revisable. Los ejemplos de contrato y prueba fijan entradas/salidas futuras; no se han ejecutado ahora. Dividir los pasos de implementación en cambios pequeños dentro del mismo ciclo rojo → verde → revisión. No iniciar otra feature para esquivar un fallo.

### F04.01 — Completar candidatos y asignación sin falsos vacíos

**Archivos:** hoy/context.py, protocolos/providers C08, migration042, tests/hoy/test_priority_context.py nuevo.

**Interfaz y propiedad:** C08 list_assigned_contacts + context; cursor y cobertura independientes del número de items.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"connection_id":"crm-A","contact_id":"42","coverage":"partial","history_complete":false,"owner_user_id":null}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Página CRM incompleta | No clasifica nunca llamado. |
| Owner ambiguo | No muestra candidato en lista personal ajena. |
| Dos conexiones con mismo contact_id | Dos identidades separadas. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/hoy/test_priority_context.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Añadir lectura paginada de asignados a ambos proveedores y cache con observed_at/coverage.

- [ ] Mapear responsables con selección admin si email no es inequívoco; no resolver por parecido de nombre.

- [ ] Invalidar cache por nueva interacción/cambio CRM y mantener fecha visible si la fuente falla.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/hoy/test_priority_context.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Listado completo distinguido de partial/forbidden y aislamiento preservado.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F04.01`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F04.02 — Implementar ranking explicable y contrato C09

**Archivos:** hoy/priority.py, tests/hoy/test_priority.py.

**Interfaz y propiedad:** rank_candidates(candidates, now, recent_days=14) conserva identidad y orden estable; tier queda secundario en UI.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"id":"crm-A:42:deal-7","connection_id":"crm-A","contact_id":"42","deal_id":"deal-7","tier":1,"reason":"Confirmó el problema; falta acordar el siguiente paso","evidence_refs":["ev-1"],"coverage":"complete"}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Pain reciente sin meeting | Tier1 antes de contacto sin llamadas. |
| Meeting agreed F0, aún sin F14 | No recomienda otra llamada de captación. |
| Deal cerrado y otro abierto | Evalúa motivo/deal abierto sin mezclar ni duplicar acción. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/hoy/test_priority.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Calcular elegibilidad con evidencia y ventana de 14 días; explícito futuro acordado no invita antes.

- [ ] Solo asignar tier sin llamadas si las fuentes necesarias terminaron correctamente.

- [ ] Emitir reason y evidence_refs por reglas/plantillas, no texto generado genérico.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/hoy/test_priority.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Casos de ranking y reunión ya acordada pasan sin backend F14.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F04.02`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F04.03 — Servir candidatos y representar vacío/parcial

**Archivos:** api/contact_priorities.py; useContactPriorities.ts; ContactPriorities.tsx; DashboardHome.tsx.

**Interfaz y propiedad:** GET /contact-priorities scoped; no usar una respuesta404/403 como items=[].

**Ejemplo concreto de contrato o prueba a incorporar:**

```text
complete + [] -> No hay contactos prioritarios ahora
partial + [] -> Falta parte del historial
no_crm -> Conecta tu CRM
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Cero candidatos completos | Copy A7 y Abrir contactos en CRM. |
| Nueva empresa/no CRM | Onboarding específico y acción por rol. |
| Refetch fallido con datos previos | Conserva candidatos con cobertura/antigüedad. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `npm run build` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Registrar router y validar filtros/paginación; compartir keys por usuario/empresa/conexión.

- [ ] Mostrar motivo y una acción principal; mantener ActivityPanel como historial.

- [ ] Verificar estados A7 y que siguiente F05 pueda integrar componente sin dos vacíos redundantes.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `npm run build` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Reticle distingue lista vacía de fallo y navega al contacto correcto.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F04.03`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

## Verificación integrada y criterios de salida adicionales

Empresa de prueba con contacto pain confirmado, uno sin llamadas y uno con meeting acordado; verificar orden y exclusión. Forzar permiso de actividad parcial y comprobar que no se afirma nunca llamado. Probar vacío completo.

### Regresiones y comandos al cerrar

- `cd backend && .venv/bin/python -m pytest tests/hoy/test_priority.py tests/hoy/test_priority_context.py -q`
- `npm run build`

Ejecutar los comandos desde `/Users/danizal/getvocify`, salvo el `cd` explícito. Un directorio de pruebas indicado como nuevo solo estará disponible después de sus tareas; que hoy no exista no autoriza a omitirlo al ejecutar. Las pruebas de IA usan datos reales autorizados y anonimizados; los ejemplos sintéticos de este plan sirven solo para contratos y tests deterministas.

### Qué vuelve al coordinador

- [ ] Informe de `F04` con tarea/criterio → resultado → prueba o veredicto → commit, migración aplicada y contrato entregado.

- [ ] Comparación de interfaces producidas con `00-contracts.md`; ninguna divergencia silenciosa de campos, estados, permisos o semántica de `null`.

- [ ] Revisión SOLID y limpieza de listeners/jobs/efectos; los servicios no duplican interpretación que corresponde a extracción.

- [ ] Evidencia de todos los estados de UI especificados. En web, `reticle_act_and_wait` o `reticle_assert` con consecuencia explícita; en desktop/extensión, además el recorrido nativo. `unknown` y `no-fault` no cierran.

- [ ] Bloqueos y edge cases nuevos en `docs/superpowers/deliveries/F04/report.md` y en el commit/PR. No marcar completa mientras haya criterios pendientes; una suspensión debe nombrar las dependencias no afectadas.

## Handoff a la siguiente entrega

F05 recibe candidatos y lecturas con cobertura. Ranking y persistencia de señales son responsabilidades distintas; no reemplazar rank_cards de S por tier ni crear un job duplicado de contexto.
