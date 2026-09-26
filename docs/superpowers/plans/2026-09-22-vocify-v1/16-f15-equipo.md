# F15 — Dashboard de equipo y manager chat: plan ejecutable

> **Ejecución futura:** usar `executing-plans` dentro del subagente dedicado a esta entrega; la coordinación secuencial usa `subagent-driven-development`. Este documento es planificación, no una implementación ni una autorización para desplegar. Ninguna casilla de ejecución está completada.

**Objetivo:** Agregar actividad/proceso/resultados de equipo con evidencia, atribución explícita y permisos owner/admin.

**Arquitectura:** Agregaciones sobre datos generados; snapshot CRM conserva fecha/moneda/owner. Web, manager chat e informes consumen la misma consulta scoped, sin ranking.

**Stack:** FastAPI/Python, Supabase/PostgreSQL, React 18/TypeScript y módulos JS compartidos; Electron/extensión cuando figuren entre las superficies de esta entrega.

**Posición:** 16 de 16. **Estado:** planificada; no iniciada.

**Navegación:** [plan maestro](/Users/danizal/getvocify/proposed_plan.md) · [contratos](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-contracts.md) · [integración y gates](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-integration-and-gates.md)

**Fuentes de esta entrega:** P: [Prompt técnico](/Users/danizal/getvocify/docs/TECHNICAL_PLANNING_PROMPT_VOCIFY_V1.md) · A: [Análisis de producto](/Users/danizal/getvocify/docs/PRODUCT_PLANNING_ANALYSIS_2026-09-21.md).

## Entrada, salida y frontera de responsabilidad

| Tipo | Contrato de esta entrega |
|---|---|
| Recibe | C14 conteos ponderables, C13 patrones, C15 meetings, C18 informes, C08 outcomes y roles. |
| Produce | C19 TeamOverview/Objections/Competitors/Outcomes; snapshots de la migración 049; herramientas de lectura para Ask. |
| Dependencias de código | [F13](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/15-f13-reporting.md), [F09](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/11-f09-scoring.md), [F10](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/10-f10-objeciones-y-notas.md), [F14](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/12-f14-meeting-booked.md), [F07](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/05-f07-ask-vocify.md) |
| Migración propia | 049_team_outcomes.sql |
| No le corresponde | No inferir ventas desde meetings, causas desde correlación, rendimiento de datos vacíos ni crédito multitoque. Sin leaderboard. |

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

## Feature: F15 — Dashboard de equipo y manager chat

**Fuente:** A §7.1–7.4; P §5.1.4.  

**Prioridad:** V1.

### En una frase

El responsable ve qué está ocurriendo en su equipo, qué objeciones se repiten y cuánto se sigue el proceso comercial.

### Por qué (first principles)

La visibilidad debe salir del trabajo ya capturado. Construir esta pantalla antes de generar los datos llevaría a métricas incompletas o ficticias.

### Qué ya existe (auditoría)

- Roles owner/admin, actividad de empresa y filtro por autor.

- Gestión de miembros en Settings.

- Resultados de las funcionalidades anteriores.

- Gap real: agregación de rendimiento y herramientas de lectura con ámbito de equipo.

### Backend

- Crear `/Users/danizal/getvocify/backend/app/services/team_insights/`.

- Migración 049: instantáneas de deals observados con conexión, estado abierto/ganado/perdido, importe, moneda, responsable, fechas y razón CRM cuando exista.

- No inferir pago, facturación ni causa de pérdida desde `meeting_booked`.

- Lecturas de CRM a través de proveedores; recuperar cambios en cada actualización programada y bajo demanda.

- Endpoints:

  - `GET /api/v1/team/overview`.

  - `GET /api/v1/team/objections`.

  - `GET /api/v1/team/competitors`.

  - `GET /api/v1/team/outcomes`.

- Filtros compartidos: periodo, comercial y tipología.

- Adherencia de equipo: suma de pasos cumplidos / suma de pasos aplicables evaluados. Mostrar cobertura y tamaño de muestra.

- No promediar porcentajes individuales sin ponderar sus denominadores.

- Panel de objeciones: categoría, frecuencia, resolución observada y conversaciones de ejemplo.

- Competidores: menciones y afirmaciones citadas; no análisis de mercado.

- Win-loss: asociación entre hechos observados y resultados CRM. No presentar correlación como causa demostrada.

- Extender las herramientas del mismo Ask Vocify para consultar estas agregaciones.

- Reutilizar informes F13 con ámbito de equipo; comprobar permisos de nuevo al generar y entregar.

#### Atribución y datos incompletos — B3

- Clave de unicidad de resultado: empresa + conexión CRM + ID de deal. Un deal asociado a varios contactos o interacciones cuenta una sola vez en el total; las asociaciones sirven para navegar a evidencia, no para multiplicar ventas.
- La actividad se atribuye al autor de la interacción; el resultado comercial se atribuye al responsable principal único del deal que devuelve el proveedor para la instantánea usada. Mostrar explícitamente esta diferencia al ampliar la métrica. No atribuir un cierre a cada persona que habló con el contacto.
- Si hay varios responsables sin un principal inequívoco, o el principal no está mapeado a Vocify, conservar el deal en «Sin atribución resuelta». Cuenta una vez en el total de equipo autorizado, pero no en el subtotal de ningún comercial. Owner/admin puede revisar el mapeo; un member no obtiene visibilidad adicional por esa categoría.
- Los subtotales por comercial más «Sin atribución resuelta» deben reconciliar con el total para el mismo periodo, moneda y cobertura. No repartir crédito en porcentajes ni añadir atribución multitoque sin una decisión de producto.
- Un cambio de dueño no reescribe silenciosamente un informe persistido. Guardar responsable, momento observado y fecha CRM disponible; sin historia fiable no reconstruir quién era el propietario en una fecha anterior. Mostrar la limitación al filtrar un periodo histórico.
- Empresa nueva sin interacciones ni resultados: estado de onboarding, sin rendimiento simulado. Empresa con actividad pero sin playbook: mostrar actividad/resultados y «Adherencia no disponible: falta proceso publicado». Sin pasos evaluables, adherencia `null`, no 0 %.
- Lecturas CRM parciales, permisos insuficientes o sincronización atrasada: conservar datos observados con cobertura y fecha. No mezclar un numerador actualizado con un denominador de otra revisión; no generar win-loss concluyente con resultados desconocidos.

**SOLID:** agregaciones sobre datos ya existentes; chat y email consumen las mismas métricas; proveedores solo aportan resultados CRM.

### Frontend / Dashboard

- Vista `/dashboard/team`, visible a owner/admin.

- Mantener la gestión de miembros en `/dashboard/settings/team`.

- Módulo `/Users/danizal/getvocify/src/features/team-insights/`.

- Primera pantalla: actividad, meetings, calidad y adherencia.

- Objeciones, competidores y ejemplos se amplían bajo demanda.

- Filtro de comercial sin leaderboard.

- Chat reutilizado con ámbito de equipo autorizado.

- Copy: «La cualificación se completó en 18 de 24 pasos evaluables».

#### Tratamiento visual de agregaciones — A14

**Decisión V1:** resumen numérico, barras horizontales para frecuencias/proporciones y tablas para valores exactos y evidencia. No usar una tabla comparativa de puntuaciones de comerciales ni gráficos de ranking. Reutilizar `/Users/danizal/getvocify/src/components/ui/chart.tsx`, `table.tsx` y `recharts` existentes, sin introducir otra librería de visualización.

**Archivos previstos:** `/Users/danizal/getvocify/src/pages/dashboard/TeamInsightsPage.tsx`; componentes `TeamOverview.tsx`, `ObjectionBreakdown.tsx`, `AdherenceBreakdown.tsx` y `OutcomeBreakdown.tsx` bajo `/Users/danizal/getvocify/src/features/team-insights/components/`. Hooks de lectura en el mismo módulo de feature; cálculos y denominadores llegan del backend.

| Bloque | Vista inicial | Detalle al ampliar |
|---|---|---|
| Filtros compartidos | Periodo, tipología y comercial, por defecto equipo completo; comerciales por nombre, no ordenados por rendimiento. | Mantener el mismo alcance en todas las consultas, ejemplos y acceso al chat. |
| Actividad y resultados | Cifras separadas de intentos, conversaciones conectadas, meetings acordados y cierres CRM. Fecha y cobertura visibles. | Tabla por día y lista de interacciones/registros que forman el dato; distinguir fuente de actividad de fuente CRM. |
| Adherencia | Barra horizontal de cumplidos frente a incumplidos entre pasos evaluables; texto «18 de 24». Cobertura y desconocidos visibles aparte, no tratados como incumplimientos. | Tabla por paso del playbook: cumplidos, evaluables, no aplicables, desconocidos y acceso a evidencia. El filtro de comercial permite estudiar una persona sin convertirlo en ranking. |
| Objeciones | Barras horizontales por categoría, ordenadas por frecuencia, con recuento y muestra. | Tabla por categoría con resueltas, abiertas y desconocidas; resolución conocida con denominador explícito y conversaciones de ejemplo. Para estudiar quién las supera se usa el filtro de comercial y las respuestas observadas. |
| Competidores | Tabla de menciones: nombre, número de interacciones y última mención observada. | Afirmaciones citadas y enlaces a conversaciones; no inferir cuotas de mercado ni causas de pérdida. |
| Win-loss | Barra de ganados/perdidos entre deals con resultado conocido; abiertos y sin resultado se muestran como recuentos separados. Importe separado por moneda. | Tabla de deals con resultado, responsable o «Sin atribución resuelta», fuente, fecha y razón CRM si existe. `won / (won + lost)` solo cuando el denominador sea positivo y la cobertura permita describirlo; no llamar cerrado a un meeting. |

Los gráficos muestran valores y leyendas, y tienen tabla equivalente accesible; no depender exclusivamente de color o tooltip. Un filtro sin resultados muestra «No hay datos para estos filtros» y «Restablecer filtros». Una empresa nueva muestra «El panel se completará con las interacciones de tu equipo», con acceso a configuración/primera captura según permisos. Una fuente parcial añade un aviso junto al bloque afectado y conserva los otros bloques válidos.

Cuando el periodo carece de tamaño suficiente para conclusiones, mostrar recuentos y cobertura sin atribuir eficacia: los ejemplos son evidencia para revisar, no una afirmación causal de que una respuesta aumenta cierres. Mantener esta advertencia concreta junto al dato, sin llenar la página de avisos genéricos.

### Criterio de aceptación (Definition of Done)

- [x] Cada métrica se puede rastrear a interacciones o registros CRM.

- [x] Las llamadas conectadas no incluyen buzones ni simples intentos.

- [x] Meeting booked no incrementa ventas ganadas.

- [x] Adherencia y cobertura coinciden con sus datos de origen.

- [x] Un miembro obtiene rechazo aunque invoque directamente los endpoints.

- [x] El manager chat no puede ampliar su ámbito por instrucciones del usuario.

- [x] Los reportes programados reutilizan la misma agregación.

- [x] Con pocas muestras se muestra la limitación y se evita una conclusión categórica.

- [x] No aparecen scorecards comparativas, leaderboards ni widgets generados por chat.

- [ ] Cada bloque usa el tratamiento visual definido y tabla accesible equivalente; filtros, gráficos, detalle y chat comparten alcance y cobertura.

- [x] Un deal con múltiples contactos/responsables cuenta una vez en el total; si no hay responsable principal inequívoco queda sin atribución individual. Subtotales más «Sin atribución resuelta» reconciliados con el total.

- [x] Empresa nueva, filtros vacíos, playbook ausente y lectura CRM parcial se distinguen visualmente; no muestran tasas cero ficticias ni conclusiones win-loss sin denominador.

### Riesgos / edge cases conocidos

Responsables CRM sin mapear, monedas diferentes, deals reabiertos y periodos con pocos datos. No sumar importes de monedas distintas como si fueran comparables.

## Mapa de archivos y responsabilidades

| Acción futura | Ruta | Responsabilidad |
|---|---|
| Crear | `/Users/danizal/getvocify/backend/app/services/team_insights/outcomes.py` | Snapshots/dedupe/atribución. |
| Crear | `/Users/danizal/getvocify/backend/app/services/team_insights/aggregate.py` | Métricas por filtros. |
| Crear | `/Users/danizal/getvocify/backend/app/api/team_insights.py` | Cuatro endpoints scoped. |
| Modificar | `/Users/danizal/getvocify/backend/app/services/crm_copilot/tools.py` | Lecturas autorizadas equipo. |
| Crear | `/Users/danizal/getvocify/backend/migrations/049_team_outcomes.sql` | Historia observada CRM. |
| Crear | `/Users/danizal/getvocify/backend/tests/team_insights/test_outcomes.py` | Owners/monedas/dedupe. |
| Crear | `/Users/danizal/getvocify/backend/tests/team_insights/test_permissions.py` | API/chat/report boundaries. |
| Crear | `/Users/danizal/getvocify/src/pages/dashboard/TeamInsightsPage.tsx` | Vista equipo. |
| Crear | `/Users/danizal/getvocify/src/features/team-insights/components/TeamOverview.tsx` | Resumen/filtros. |
| Crear | `/Users/danizal/getvocify/src/features/team-insights/components/ObjectionBreakdown.tsx` | Barras/tabla/evidencia. |
| Crear | `/Users/danizal/getvocify/src/features/team-insights/components/AdherenceBreakdown.tsx` | Ratio y cobertura. |
| Crear | `/Users/danizal/getvocify/src/features/team-insights/components/OutcomeBreakdown.tsx` | Win-loss sin doble conteo. |

Los archivos marcados «Crear» todavía no existen por esta planificación. Los marcados «Modificar» pueden ser producidos por una dependencia; su procedencia debe quedar indicada. Los tests y fixtures se crean en ejecución, nunca se confunden con datos de producción.

## Tareas secuenciales con ciclo TDD

Cada tarea termina con evidencia revisable. Los ejemplos de contrato y prueba fijan entradas/salidas futuras; no se han ejecutado ahora. Dividir los pasos de implementación en cambios pequeños dentro del mismo ciclo rojo → verde → revisión. No iniciar otra feature para esquivar un fallo.

### F15.01 — Observar outcomes sin duplicar ventas ni responsables

**Archivos:** outcomes.py, migration049, tests/team_insights/test_outcomes.py.

**Interfaz y propiedad:** C19 clave company/connection/deal; responsable principal único o unassigned; moneda/fecha/observed_at separados.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"connection_id":"crm-A","deal_id":"deal-7","status":"won","owner_user_id":null,"attribution":"unresolved","amount":"1200.00","currency":"EUR","observed_at":"2026-09-22T12:00:00Z"}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Deal con tres contactos y dos responsables no principal | Una venta de equipo, ninguna doble atribución individual. |
| Cambio owner o reabierto | Nueva observación sin reescribir informe persistido. |
| EUR y USD | No sumarlos como mismo importe. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/team_insights/test_outcomes.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Reutilizar lectura provider F13 y persistir instantáneas idempotentes de cada observación.

- [ ] Resolver owner principal por contrato CRM; si ambiguo conservar bucket sin atribución.

- [ ] Distinguir evento fecha CRM de fecha observación; sin historia no inventar estado previo.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/team_insights/test_outcomes.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Totales de equipo = subtotales+sin atribución para misma cobertura/moneda.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F15.01`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F15.02 — Calcular métricas y proteger todas las lecturas

**Archivos:** aggregate.py; api/team_insights.py; test_permissions.py y test_aggregate.py nuevo.

**Interfaz y propiedad:** C19 filtros periodo/comercial/tipología; role owner/admin. Adherencia suma met / suma applicable.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"met_steps":2,"applicable_steps":10,"adherence":0.2,"unknown_steps":0}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Rep A1/1, B1/9 | Equipo2/10, no promedio55.6%. |
| Member fuerza endpoint/ID | Denegado sin datos. |
| Sin playbook o muestra | Null/cobertura, no rendimiento inventado. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/team_insights/test_permissions.py tests/team_insights/test_aggregate.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Agregar con revisión y filtros comunes; unir outcomes por identidad completa sin multiplicación por joins.

- [ ] Implementar objeciones por categoría/resolución y competidores como menciones citadas.

- [ ] Aplicar permisos en servicio y RLS, no solo ocultar página; reportes revalidan al generar y entregar.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/team_insights/test_permissions.py tests/team_insights/test_aggregate.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Métricas trazables al detalle y aislamiento en todos los caminos.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F15.02`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F15.03 — Construir visualizaciones y drilldown sin ranking

**Archivos:** TeamInsightsPage y4componentes, App.tsx; reusar chart/table existentes.

**Interfaz y propiedad:** C19 una selección de filtros para todos bloques; gráficos y tabla misma serie backend.

**Ejemplo concreto de contrato o prueba a incorporar:**

```text
Equipo -> filtros comunes -> dato agregado -> tabla exacta -> fuente
Sin datos != cero rendimiento
Sin owner inequívoco -> Sin atribución resuelta
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Filtro comercial | Nombre elegido, no ranking por score. |
| Owner unresolved | Visible en detalle equipo, no sumado a cada rep. |
| No datos/partial | Onboarding/filtro vacío y warning junto a bloque específico. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `npm run build` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Implementar layout A14 con barras horizontales/valores/tablas y cobertura visible.

- [ ] Enlazar evidencia y resultados con mismos filtros; no usar hover/color como única lectura.

- [ ] Verificar responsive/keyboard/contraste y que Settings team siga gestionando miembros por separado.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `npm run build` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Reticle recorre filtros->métrica->evidencia y cero/tasa desconocida.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F15.03`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F15.04 — Conectar manager chat y reporte de equipo a la misma agregación

**Archivos:** crm_copilot/tools.py; reporting/aggregate.py/delivery.py; tests/team_insights/test_channels.py nuevo.

**Interfaz y propiedad:** C19 servicio scoped único; chat no acepta company_id libre ni amplía permisos por instrucciones del usuario.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"scope":"team","filters":{"sales_motion_key":"discovery","user_id":null},"aggregation_source":"team_insights.aggregate"}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Pregunta equivalente al panel | Mismos filtros/números y fuentes. |
| Prompt pide otra empresa | Denegado por servicio. |
| Admin pierde rol antes envío | Reporte equipo no entregado. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/team_insights/test_channels.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Añadir herramientas discretas de lectura de overview/objeciones/competidores/outcomes.

- [ ] Reutilizar C18 con scope team y permisos reevaluados; no segundo agregador ni cálculos del LLM.

- [ ] Ejecutar recorrido de misma pregunta en panel/chat/reporte y comparar snapshots/periodos.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/team_insights/test_channels.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Tres canales coherentes, ningún atajo de permisos.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F15.04`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F15.05 — Informe de equipo por email para owner/admin (decisión 2026-09-26)

**Motivo:** F15.04 pide reutilizar C18 con `scope: team`; no existía. A §7.2 y §8: reportes programados al manager con analíticas de equipo, email como canal principal y campana como secundario.

**Flag:** `REPORTING_TEAM_ENABLED`, por empresa con `feature_flags.is_enabled`, apagado por defecto. Apagado: no se genera ni se envía, la campana no lista informes de equipo y las preferencias no traen `team`.

**Destinatarios:** miembros activos con rol owner o admin en el momento de generar, con `report_preferences.team_enabled` (por defecto `true`). Un informe por destinatario con la clave única de 048 (`user_id` = destinatario, `scope = 'team'`, `report_type = 'weekly'`).

**Frecuencia:** semanal, mismo periodo y hora que el semanal personal de F13.04 (lunes–viernes, a partir del viernes 18:00 en la zona del destinatario). No hay diario de equipo en V1: el panel ya cubre el día y un segundo email diario al manager es ruido. Queda como decisión de producto abierta.

**Datos, sin segundo agregador:** `team_adherence` (lo mismo que sirve `GET /team/adherence`) con el periodo de la semana y sin filtros de comercial ni tipología: intentos, conversaciones conectadas, reuniones acordadas, adherencia `met_steps / applicable_steps` con muestra y objeciones por categoría. La serie diaria usa `activity_counts` día a día, la misma función. Sin LLM: la frase es «Tu equipo esta semana: N llamadas conectadas y M reuniones acordadas.»

- Cierres CRM: la lectura de outcomes del panel no está acotada al periodo, así que el informe los muestra como «No disponible» con `coverage.crm_outcomes: "unavailable"`. No se presentan cierres de la semana que no se pueden fechar.
- Sin ranking: las cifras del equipo no llevan desglose por comercial. La única excepción es la adherencia por semana (corrección de abajo), detrás de su propio flag, por orden alfabético y nunca ordenada por nota.
- Semana sin actividad del equipo: sin informe.

**Permisos, reevaluados tres veces:** (1) al generar, con el rol actual de `company_members` y `assert_team_reader`; (2) justo antes de enviar, se relee `company_members`: si ya no es owner/admin activo de esa empresa, no se envía y no se guarda entrega; (3) al leer `GET /reports/{id}`, un informe de equipo exige ser el destinatario y owner/admin actual de la misma empresa; si no, 404 sin cifras ni destinatarios. La campana tampoco lo lista si el rol ya no es owner/admin.

**Email:** asunto «Tu equipo esta semana», la frase, tabla (adherencia como «18 de 24 pasos»), hasta tres objeciones y «Ver informe».

**Casos que deben fallar antes de implementar:**

| Caso | Resultado exigido |
|---|---|
| Misma semana en panel e informe | Mismos intentos, conectadas, reuniones, adherencia y objeciones. |
| Member | Ni se genera para él ni lo lee por ID (404). |
| Admin pierde el rol entre generar y enviar | No se envía. |
| Admin de otra empresa abre el ID | 404. |
| Flag apagado | Nada generado; campana sin informes de equipo. |
| `team_enabled` apagado | Sin informe para esa persona. |
| Sin playbook | Adherencia `null`, «No disponible». |
| Snapshot | Sin claves por comercial, salvo `adherence_trend` con el flag de evolución; nunca `user_id`. |

### Addendum — evolución de adherencia por comercial (decisión 2026-09-26)

**Motivo:** A §7.4 marca la adherencia al playbook «y su evolución en el tiempo» como una de las conclusiones más fuertes para el manager: es la cifra que el head of sales reporta hacia arriba. `GET /team/adherence` solo da la semana en curso; no había forma de ver si un comercial mejora o empeora. Decisión del founder: solo owner/admin, evolución semanal por comercial dentro de Equipo. El comercial no ve notas ni scores (`PLAN_INTEGRACION.md` §5).

**Flag:** `TEAM_ADHERENCE_TREND_ENABLED`, por empresa con `feature_flags.is_enabled`, apagado por defecto. Se evalúa en cada petición con la empresa de la membresía, antes que el rol. Apagado: `GET /team/adherence/trend` responde 404 igual que una ruta inexistente y la UI no pinta nada nuevo. Quien consuma la agregación fuera del endpoint (informe de equipo) debe comprobar el mismo flag.

**Agregación (sin LLM, sin migración):** `team_insights/adherence_trend.py: adherence_trend(supabase, company_id, *, role, weeks=8, now=None, user_id=None, motion=None, tz_name="Europe/Madrid")`. Lee memos y `memo_scores`; no escribe nada.

- **Semana:** lunes–domingo local. No existe zona horaria de empresa en BD; se usa Europe/Madrid, igual que el resto de Equipo (`madrid_week_bounds`). `tz_name` queda como parámetro para cuando exista.
- **Ventana:** las últimas 8 semanas, contando la semana en curso (marcada `in_progress`). `weeks` admite 1–12.
- **Instante de la conversación:** `capture_started_at`, si no `created_at` del memo. Es cuándo trabajó el comercial; una re-puntuación posterior no mueve la conversación de semana. (El bloque de la semana en curso usa la fecha del score; en el borde de la semana ambos pueden diferir en una conversación.)
- **Qué es una conversación:** un memo del comercial en la ventana, salvo `screening_outcome` buzón/sin respuesta y memos `failed`. Mismo ámbito de empresa que `/team/adherence` (miembros activos; memos antiguos sin `company_id` de miembros cuentan).
- **Score vigente:** por memo, la fila de `memo_scores` con mayor `revision_seq`. Una conversación cuenta una vez aunque se haya puntuado varias.
- **Cobertura, contada aparte y nunca como 0:** `scored` (score `ready`/`partial`), `without_playbook` (score `unavailable` o motivo `missing_playbook`) y `without_score` (sin fila, pendiente o fallido). `interactions = scored + without_playbook + without_score`.
- **Adherencia:** la de F09/C14: se suman `met/missed/unknown/not_applicable` de los scores y se aplica `compute_adherence`. `met_steps / applicable_steps`, `null` sin denominador; `unknown` va a cobertura, no es incumplido. El equipo suma conteos, no promedia porcentajes de comerciales.
- **Proceso, no resultado:** `crm_outcome`, meeting acordado o deal ganado no entran. Una llamada fácil con reunión no sube la serie.
- **Estado por semana:** `gap` (ninguna conversación: hueco, no 0 %), `unscored` (conversaciones sin pasos evaluables: se dice cuántas y por qué) y `scored`. `sample_limited` con 1–4 conversaciones puntuadas.
- **Versión de playbook:** cada conversación se mide contra la `playbook_version_id` con que se puntuó. `playbook_version_ids` lista las de la semana; `new_playbook_version` marca la primera semana en que una tipología aparece con una versión distinta a la usada antes en la ventana.
- **Orden:** fila de equipo (solo sin filtro de comercial) y comerciales en orden alfabético (`load_team_reps`). Nunca por adherencia, sin «mejor/peor».
- **Filtros:** `user_id` y `motion`, los mismos del panel. Un `user_id` que no es miembro activo de la empresa no devuelve filas.
- **Lectura fallida** de memos o scores: `coverage: "unavailable"` sin cifras. Memos paginados de 1000 en 1000; scores por lotes de 200 IDs.

```json
{"coverage":"complete","timezone":"Europe/Madrid","weeks":[{"week_start":"2026-09-21","week_end":"2026-09-27","in_progress":true}],"team":{"weeks":[{"week_start":"2026-09-21","state":"scored","interactions":3,"scored":2,"without_playbook":1,"without_score":0,"met_steps":2,"applicable_steps":10,"unknown_steps":0,"not_applicable_steps":0,"adherence":0.2,"coverage":1.0,"sample_limited":true,"playbook_version_ids":["pv-1"],"new_playbook_version":false}]},"reps":[{"user_id":"u-a","name":"Ana","weeks":[]}]}
```

**Endpoint:** `GET /api/v1/team/adherence/trend?weeks=&user_id=&motion=`. Rol leído de `company_members` en cada petición (`get_membership`); member → 403 sin cifras.

**UI:** dentro de la tarjeta de Adherencia existente, bajo la cifra de la semana: «Últimas 8 semanas», una fila por serie (Equipo primero, luego comerciales por nombre) con 8 barras mínimas de altura = adherencia, hueco punteado para `gap`, marca neutra para `unscored`, y el último «N de M» en texto. «Ver detalle» (`<details>`) abre la tabla equivalente: semana × serie con «N de M», «Sin conversaciones» o «Sin puntuar (K)», y «Proceso actualizado» donde cambia la versión. Una línea de muestra limitada si alguna semana la tiene. Carga: nada (reservar altura haría saltar la tarjeta en toda empresa con el flag apagado, que es el valor por defecto); error o `coverage: unavailable`: una línea «No se pudo cargar la evolución»; ventana sin conversaciones: «Sin conversaciones en estas semanas». Flag apagado (404): nada. Sin pantalla nueva.

**Casos que deben fallar antes de implementar:**

| Caso | Resultado exigido |
|---|---|
| Flag apagado | 404 como ruta inexistente; la UI no pinta nada. |
| Member con flag encendido | 403 sin cifras. |
| Semana sin conversaciones | `state: gap`, adherencia `null`, no 0 %. |
| Conversaciones sin playbook publicado | `without_playbook` contado, adherencia `null`, `state: unscored`. |
| Conversación sin score (pendiente/fallido/sin fila) | `without_score`, no incumplido. |
| Solo `unknown` | Adherencia `null`, cobertura 0, no 0 %. |
| A 1/1 y B 1/9 la misma semana | Equipo 2/10, no 55,6 %. |
| Misma conversación puntuada dos veces | Cuenta una vez con la revisión de mayor `revision_seq`. |
| Versión de playbook cambia en la ventana | Cada conversación con su versión; `new_playbook_version` en la semana del cambio. |
| Misma evidencia, resultado CRM distinto | Misma adherencia. |
| Buzón / sin respuesta / memo fallido | Fuera de todo recuento. |
| Domingo 23:30 y lunes 00:30 locales (con cambio de hora) | Semanas distintas según Europe/Madrid. |
| Semana en curso | Incluida y `in_progress`. |
| 1–4 conversaciones puntuadas | `sample_limited`. |
| Lectura de memos o scores falla | `coverage: unavailable`, sin cifras. |
| Más de 1000 conversaciones en la ventana | Todas contadas. |
| Filtro de comercial / `user_id` ajeno | Solo su fila y sin fila de equipo / ninguna fila. |
| Orden | Equipo, luego alfabético; nunca por adherencia. |
| Comercial sin conversaciones en 8 semanas | Fila con 8 huecos. |

**Corrección a F15.05 (decisión del founder, 2026-09-26):** el informe de equipo semanal lleva la adherencia por semana por comercial. Solo si `TEAM_ADHERENCE_TREND_ENABLED` está encendido para la empresa, además de `REPORTING_TEAM_ENABLED`. Últimas 4 semanas, con la fila Equipo primero y los comerciales por orden alfabético. Celdas «9 de 12», «—» si es un hueco, «Sin puntuar», y un «*» con nota si hay menos de 5 puntuadas. El snapshot guarda nombres, nunca `user_id`. Email y página muestran la misma tabla. Si la lectura falla o no está completa, el informe sale sin ese bloque.

**Fuera de alcance / decisiones abiertas:** zona horaria por empresa; umbral de muestra distinto de 5; que el vacío «No hay datos para estos filtros» de la semana en curso oculte también la evolución de un comercial sin actividad esta semana.

## Verificación integrada y criterios de salida adicionales

Owner abre equipo, filtra periodo/tipología y ve actividad, adherencia, objeciones y outcomes. Amplía un dato hasta fuente; pregunta mismo dato al chat y genera reporte. Member no accede por URL/API/chat. Probar deal múltiples responsables y monedas.

### Regresiones y comandos al cerrar

- `cd backend && .venv/bin/python -m pytest tests/team_insights tests/reporting -q`
- `npm run build`
- `make test-js`

Ejecutar los comandos desde `/Users/danizal/getvocify`, salvo el `cd` explícito. Un directorio de pruebas indicado como nuevo solo estará disponible después de sus tareas; que hoy no exista no autoriza a omitirlo al ejecutar. Las pruebas de IA usan datos reales autorizados y anonimizados; los ejemplos sintéticos de este plan sirven solo para contratos y tests deterministas.

### Qué vuelve al coordinador

- [ ] Informe de `F15` con tarea/criterio → resultado → prueba o veredicto → commit, migración aplicada y contrato entregado.

- [ ] Comparación de interfaces producidas con `00-contracts.md`; ninguna divergencia silenciosa de campos, estados, permisos o semántica de `null`.

- [ ] Revisión SOLID y limpieza de listeners/jobs/efectos; los servicios no duplican interpretación que corresponde a extracción.

- [ ] Evidencia de todos los estados de UI especificados. En web, `reticle_act_and_wait` o `reticle_assert` con consecuencia explícita; en desktop/extensión, además el recorrido nativo. `unknown` y `no-fault` no cierran.

- [ ] Bloqueos y edge cases nuevos en `docs/superpowers/deliveries/F15/report.md` y en el commit/PR. No marcar completa mientras haya criterios pendientes; una suspensión debe nombrar las dependencias no afectadas.

## Handoff a la siguiente entrega

Cierre V1: integrar gates end-to-end y revisar todas las entregas suspendidas. El panel de equipo no convierte F03 o distribución pendiente en completadas; mantener su estado y evidencia por separado.
