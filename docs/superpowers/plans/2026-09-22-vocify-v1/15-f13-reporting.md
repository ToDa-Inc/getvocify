# F13 — Reporting diario/semanal y campana: plan ejecutable

> **Ejecución futura:** usar `executing-plans` dentro del subagente dedicado a esta entrega; la coordinación secuencial usa `subagent-driven-development`. Este documento es planificación, no una implementación ni una autorización para desplegar. Ninguna casilla de ejecución está completada.

**Objetivo:** Persistir un informe personal por periodo y distribuirlo por email/campana con datos consistentes.

**Arquitectura:** Agregador produce instantánea; scheduler elige periodos locales; delivery envía con idempotencia; web/email leen mismos datos. El gráfico es representación, no cálculo paralelo.

**Stack:** FastAPI/Python, Supabase/PostgreSQL, React 18/TypeScript y módulos JS compartidos; Electron/extensión cuando figuren entre las superficies de esta entrega.

**Posición:** 15 de 16. **Estado:** planificada; no iniciada.

**Navegación:** [plan maestro](/Users/danizal/getvocify/proposed_plan.md) · [contratos](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-contracts.md) · [integración y gates](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-integration-and-gates.md)

**Fuentes de esta entrega:** A: [Análisis de producto](/Users/danizal/getvocify/docs/PRODUCT_PLANNING_ANALYSIS_2026-09-21.md).

## Entrada, salida y frontera de responsabilidad

| Tipo | Contrato de esta entrega |
|---|---|
| Recibe | C01 actividad, C14 métricas, C13 objeciones, C15 meetings, C16 brief; Resend existente. |
| Produce | C18 ReportSnapshot/Delivery/Notification y preferencias; layout diario/semanal. |
| Dependencias de código | [F11](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/13-f11-brief-posterior.md), [F07](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/05-f07-ask-vocify.md) |
| Migración propia | 048_reports_notifications.sql |
| No le corresponde | No esperar F15 para definir cierres: F13 implementa lectura mínima read_deal_outcomes de C08 para su periodo; F15 añade snapshots históricos de la migración 049. Sin coverage, cierres no disponibles. |

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

## Feature: F13 — Reporting diario/semanal y campana

**Fuente:** A §4.10 y §8; patrón de notificaciones de SignalCore.  

**Prioridad:** V1.

### En una frase

El comercial recibe un resumen breve de su actividad y de los puntos útiles para mejorar, por email y dentro de Vocify.

### Por qué (first principles)

Hace visible el trabajo realizado sin obligar a revisar cada conversación. Comparte la misma información de coaching, sin generar otro análisis paralelo.

### Qué ya existe (auditoría)

- Cliente Resend.

- Datos de actividad, scoring, objeciones, meetings y brief.

- Patrón de campana con contador, listado y estados en [SignalCore](/Users/danizal/signalcore/signalcore-frontend/components/layout/you-notifications.tsx:21).

- Gap real: programación, informes persistidos y entrega.

### Backend

- Migración 048:

  - `report_preferences`: usuario, frecuencia, hora, zona e idiomas.

  - `reports`: destinatario, ámbito, periodo, datos, versión y fecha.

  - `report_deliveries`: canal, estado, intentos, clave idempotente e ID remoto.

  - `notifications`: destinatario, tipo, texto, enlace y `read_at`.

- Crear `/Users/danizal/getvocify/backend/app/services/reporting/`.

- Agregar por periodo local:

  - Intentos y llamadas conectadas, diferenciados.

  - Meetings acordados.

  - Objeciones frecuentes.

  - Adherencia con cobertura.

  - Una fortaleza y una mejora respaldadas.

- Cierres solo desde estados CRM observados, no desde la conversación.

- Email y campana apuntan al mismo informe.

- Preferencias iniciales propuestas de implementación: diario a las 18:00 y semanal el viernes a las 18:00, activables por el usuario.

- Endpoints:

  - `GET/PUT /api/v1/me/report-preferences`.

  - `GET /api/v1/reports`.

  - `GET /api/v1/reports/{id}`.

  - `GET /api/v1/notifications`.

  - `PATCH /api/v1/notifications/{id}`.

- Ampliar `ResendClient.send_email` con clave idempotente opcional, conservando llamadas actuales.

- Mantener registro propio duradero de entrega: la deduplicación de Resend conserva sus claves durante 24 horas. [Documentación de Resend](https://resend.com/changelog/idempotency-keys).

**SOLID:** agregación, programación y transporte independientes; el email no recalcula métricas.

### Frontend / Dashboard

- Campana en `DashboardLayout` con popover; consulta al abrir y periódicamente mientras la aplicación está activa.

- `useNotifications` y `useReports`.

- Página de lectura del informe desde el enlace, sin otro panel principal de navegación.

- Preferencias dentro de Settings.

- Copy: «Hoy: 8 llamadas conectadas y 2 reuniones acordadas».

#### Layout de informe — A12

**Decisión V1:** página de lectura con resumen, tabla de métricas y evidencias; el informe semanal añade un gráfico de actividad diaria. El diario no usa un gráfico para representar un único día. No se crea un constructor de informes ni una nueva navegación principal.

**Archivos previstos:** `/Users/danizal/getvocify/src/pages/dashboard/ReportPage.tsx`, `/Users/danizal/getvocify/src/features/reporting/components/ReportSummary.tsx`, `ReportMetricsTable.tsx` y `ReportActivityChart.tsx` dentro de ese directorio de componentes. Reutilizar los componentes existentes `/Users/danizal/getvocify/src/components/ui/table.tsx` y `chart.tsx` y la dependencia `recharts` ya instalada.

| Orden de lectura | Contenido y representación |
|---|---|
| 1. Cabecera | «Tu resumen del día» o «Tu semana», periodo exacto, zona horaria, fecha de generación y cobertura. La URL `/dashboard/reports/:id` abre la instantánea persistida, no un informe distinto recalculado al leer. |
| 2. Resumen breve | Hasta dos frases con hechos del periodo y las cifras que los sostienen. Sin una valoración si no hay muestra suficiente. |
| 3. Métricas | Tabla de dos columnas (métrica / valor con cobertura): intentos, conversaciones conectadas, reuniones acordadas, cierres CRM observados y adherencia con numerador/denominador. Sin ceros para fuentes no disponibles. |
| 4. Evolución semanal | Barras por día para conversaciones conectadas y reuniones acordadas, con etiquetas y leyenda. Tabla de los mismos valores accesible junto al gráfico; los días sin cobertura son huecos identificados, no barras cero. No superponer score o porcentajes en el mismo eje. |
| 5. Coaching útil | Una fortaleza y una mejora con enlace a sus interacciones/evidencias. Debajo, objeciones más frecuentes en tabla corta: categoría, frecuencia y resolución observada. Sin recomendaciones genéricas para rellenar espacio. |
| 6. Accesos finales | «Ver interacciones del periodo» y «Configurar mis informes». Las fechas y el filtro se conservan al abrir el historial. |

En móvil, las secciones se apilan; las tablas conservan etiquetas y valores legibles. Email utiliza resumen y tabla compatibles con correo, más «Ver informe»; no depende de un gráfico interactivo. Email, campana y página consumen la misma instantánea y revisión de datos.

| Estado | Tratamiento |
|---|---|
| Cargando | Reservar cabecera y tabla, sin números transitorios. |
| Periodo sin actividad, cobertura completa | «No hay actividad registrada en este periodo». Mostrar ceros solo en métricas de conteo verificadas; adherencia sin denominador aparece «No evaluable». No generar fortaleza/mejora. |
| Fuente parcial o desconectada | «Informe parcial», fecha de última lectura y métricas disponibles. Cierres no disponibles se muestran como tal; no se interpretan como cero ventas. |
| Error / informe no accesible | Reintento de lectura para error recuperable; denegación o informe inexistente sin revelar cifras ni destinatarios de otro ámbito. |

### Criterio de aceptación (Definition of Done)

- [x] Email y campana muestran los mismos números.

- [x] Cada periodo produce un único informe por destinatario y ámbito.

- [x] Reintentar un envío no duplica notificaciones.

- [x] Cambios horarios no duplican ni omiten un periodo.

- [x] Un comercial no recibe métricas privadas de compañeros.

- [x] Un fallo de email no elimina el informe de la campana.

- [x] El resumen evita párrafos genéricos y enlaza a las conversaciones relevantes.

- [x] La página diaria usa el layout definido; la semanal añade barras y tabla equivalentes. Email y página muestran la misma instantánea, periodo y denominadores. `node --experimental-strip-types --test src/lib/report-snapshot.test.ts`; `cd backend && .venv/bin/python -m pytest tests/reporting/test_presentation.py -q`

- [x] Un periodo vacío no produce coaching inventado; cobertura parcial no se convierte en barras cero ni en cero cierres. Las tablas permiten comprender los datos sin color, hover ni gráfico.

### Riesgos / edge cases conocidos

Ausencia de Resend, entrega incierta, falta de zona horaria y días sin actividad. Un informe sin datos lo indica; no genera una evaluación de rendimiento inventada.

**Dependencia resuelta:** F13 entrega la lectura mínima de outcomes CRM para su snapshot de la migración 048; F15 añade historia observada de la migración 049. Si no se puede establecer cierre y fecha del periodo, la cifra es no disponible. No se espera a F15 ni se inventa retrospectiva.

## Mapa de archivos y responsabilidades

| Acción futura | Ruta | Responsabilidad |
|---|---|
| Crear | `/Users/danizal/getvocify/backend/app/services/reporting/aggregate.py` | Snapshot por periodo/ámbito. |
| Crear | `/Users/danizal/getvocify/backend/app/services/reporting/scheduler.py` | Periodos y preferencias. |
| Crear | `/Users/danizal/getvocify/backend/app/services/reporting/delivery.py` | Email/campana reintentables. |
| Crear | `/Users/danizal/getvocify/backend/app/api/reports.py` | Lecturas y preferencias. |
| Crear | `/Users/danizal/getvocify/backend/app/api/notifications.py` | Campana y read_at. |
| Modificar | `/Users/danizal/getvocify/backend/app/integrations/resend_client.py` | Idempotency key opcional. |
| Modificar | `/Users/danizal/getvocify/backend/app/services/crm_providers/protocols.py` | Lectura de resultados CRM C08. |
| Crear | `/Users/danizal/getvocify/backend/migrations/048_reports_notifications.sql` | Informes/entregas/notificaciones. |
| Crear | `/Users/danizal/getvocify/backend/tests/reporting/test_aggregate.py` | Conteos y denominadores. |
| Crear | `/Users/danizal/getvocify/backend/tests/reporting/test_delivery.py` | Reintento/permisos. |
| Crear | `/Users/danizal/getvocify/src/pages/dashboard/ReportPage.tsx` | Lectura snapshot. |
| Crear | `/Users/danizal/getvocify/src/features/reporting/components/ReportMetricsTable.tsx` | Valores/cobertura. |
| Crear | `/Users/danizal/getvocify/src/features/reporting/components/ReportActivityChart.tsx` | Semanal y tabla equivalente. |
| Modificar | `/Users/danizal/getvocify/src/components/dashboard/DashboardLayout.tsx` | Campana. |

Los archivos marcados «Crear» todavía no existen por esta planificación. Los marcados «Modificar» pueden ser producidos por una dependencia; su procedencia debe quedar indicada. Los tests y fixtures se crean en ejecución, nunca se confunden con datos de producción.

## Tareas secuenciales con ciclo TDD

Cada tarea termina con evidencia revisable. Los ejemplos de contrato y prueba fijan entradas/salidas futuras; no se han ejecutado ahora. Dividir los pasos de implementación en cambios pequeños dentro del mismo ciclo rojo → verde → revisión. No iniciar otra feature para esquivar un fallo.

### F13.01 — Construir instantánea con periodo y fuentes coherentes

**Archivos:** reporting/aggregate.py; tests/reporting/test_aggregate.py; providers read_deal_outcomes.

**Interfaz y propiedad:** C18 snapshot inmutable por revision; métricas de C14 sumadas. Fecha de captura gobierna actividad, no fecha job.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"scope":"self","period_start":"2026-09-21T22:00:00Z","period_end":"2026-09-22T22:00:00Z","timezone":"Europe/Madrid","metrics":{"connected_calls":0,"meetings_agreed":0,"deals_won":null,"adherence":null},"coverage":{"crm_outcomes":"unavailable"}}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Buzón/intent/conversación | Intentos y conectadas separados. |
| Sin resultados CRM accesibles | Cierres null/cobertura no disponible, no0. |
| Periodos sin actividad completos | Conteos0, adherencia null y sin coaching inventado. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/reporting/test_aggregate.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Agregar métricas y seleccionar ejemplos ya respaldados, sin nueva evaluación LLM.

- [ ] Leer resultado CRM mínimo para el informe personal por proveedor y periodo; guardar cobertura en snapshot.

- [ ] Separar won/lost de meeting.agreed; no reconstruir historia de owner si no existe.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/reporting/test_aggregate.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Email/UI recibirán mismo JSON; ninguna dependencia circular con F15.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F13.01`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F13.02 — Programar y entregar con idempotencia duradera

**Archivos:** migration048; scheduler.py/delivery.py; ResendClient; tests/reporting/test_delivery.py.

**Interfaz y propiedad:** C18 unique recipient/scope/period/type; delivery dedupe propia, no depende solo TTL Resend.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"report_id":"report-1","revision":1,"channel":"email","delivery_status":"pending","idempotency_key":"report-1:r1:email"}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Dos workers y DST | Un informe/periodo y una notificación. |
| Email falla | Campana/informe conservados. |
| Permiso retirado antes envío | No entrega informe ajeno/inapropiado. |
| Timeout remoto | Reconciliar y no duplicar a ciegas. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/reporting/test_delivery.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Persistir preferencias opt-in y periodos half-open en zona explícita.

- [ ] Crear snapshot/notificación y estados de entrega transaccionales; añadir clave opcional a cliente Resend sin romper callers actuales.

- [ ] Programar reintentos limitados y conservar snapshot original; corregir datos produce nueva revisión explícita, no email diferente con mismo ID.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/reporting/test_delivery.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Carreras y error delivery no duplican informe ni eliminan datos.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F13.02`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F13.03 — Servir informes y construir layout diario/semanal

**Archivos:** reports/notifications routers, ReportPage, tabla/gráfico y DashboardLayout.

**Interfaz y propiedad:** C18 GET reports/:id devuelve snapshot, no recálculo. PATCH notification read_at idempotente y scoped.

**Ejemplo concreto de contrato o prueba a incorporar:**

```text
Campana -> /dashboard/reports/report-1
Email -> /dashboard/reports/report-1
GET -> revisión persistida 1, nunca recomputada al abrir
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Email y campana abren mismo ID | Mismos números/cobertura. |
| Semana partial | Huecos no dibujados como cero; tabla equivalente. |
| Usuario ajeno | Denegado sin cifras ni destinatarios. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `npm run build` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Registrar rutas/API y campana consultada al abrir/intervalo activo; limpiar polling al logout.

- [ ] Implementar layout A12 con resumen/tabla/coaching y gráfico solo semanal; móvil legible.

- [ ] Verificar empty/partial/error y enlaces a evidencia que mantienen periodo/filtro.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `npm run build` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Reticle abre campana->informe y verifica snapshot, estado leído y denegación.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F13.03`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F13.04 — Semanal, preferencias y campana con lo que hizo Vocify (decisión 2026-09-26)

**Motivo:** revisión reunión-vs-código. (1) Solo se genera el diario personal: el semanal de A §4.10 y de esta spec no existe. (2) La campana es un enlace al primer informe sin leer, no un popover con listado y estado, y no dice qué hizo Vocify ni por qué (A §4.10: «ahí se puede indicar cuál es la actividad que se realizó, porqué»). (3) No hay `report_preferences` ni `GET/PUT /me/report-preferences`, así que nada es «activable por el usuario».

**Flags** (por empresa con `feature_flags.is_enabled`, global en `config.py`, apagados por defecto):

- `REPORTING_WEEKLY_ENABLED`: genera y envía el semanal personal y expone la preferencia `weekly`.
- `NOTIFICATIONS_ACTIVITY_ENABLED`: `GET /notifications` añade `activity` (acciones de Vocify). Apagado, la respuesta no trae esa clave y la campana no muestra la sección.
- El informe de equipo tiene su flag en F15.05.

**Semanal personal:**

- Periodo: semana laboral local `[lunes 00:00, sábado 00:00)` en la zona del destinatario. Zona: `brief_preferences.timezone` (fuente existente), `Europe/Madrid` si falta. La clave única de 048 incluye `report_type`, así que el diario del lunes y el semanal no colisionan.
- Se genera la primera vez que el tick corre con hora local ≥ viernes 18:00 y antes del lunes siguiente; sábado y domingo recuperan un viernes perdido. Se crea una sola vez y no se reescribe (C18): lo que ocurra después de `generated_at` no entra, y el snapshot guarda `generated_at`.
- Semana sin actividad capturada: no hay informe ni email, igual que el diario.
- Snapshot: `build_snapshot` (el mismo agregador del diario) + `series` por día lunes–viernes `{date, connected_calls, meetings_agreed, covered}`. Un día que empieza después de `generated_at` lleva `covered: false` y valores `null`: la página lo pinta como hueco, no como barra cero. + `objections`: hasta tres categorías con `objection_counts` (el mismo cálculo del panel de equipo) sobre `interaction_patterns` de las conversaciones del periodo; si esa lectura falla, `objections: null` y `coverage.objections: "unavailable"`.
- Sin LLM. La frase de resumen es determinista y sigue el copy de la spec: «Esta semana: 12 llamadas conectadas y 3 reuniones acordadas.» El diario pasa a abrir con «Hoy: …» con la misma regla.
- Email: asunto «Tu semana en Vocify», esa frase, la tabla de métricas, objeciones y «Ver informe». Sin gráfico.
- Página: cabecera «Tu semana» con periodo, zona y fecha de generación; una tabla por día (conversaciones y reuniones) con una barra fina por fila, así el gráfico y su equivalente accesible son el mismo elemento y no se añade librería de gráficos; un día no cubierto dice «No incluido» sin barra. Objeciones en tabla corta.

**Preferencias (migración 053, `report_preferences`):** `user_id`, `daily_enabled`, `weekly_enabled`, `team_enabled` (todos `true` por defecto) y `updated_at`. La hora (18:00) y el día (viernes) son fijos en V1: no se guardan campos que nada lee. Idioma: español, como el email diario existente (abierto).

- `GET/PUT /api/v1/me/report-preferences` devuelve solo las claves que aplican a esa persona: `daily` siempre; `weekly` con `REPORTING_WEEKLY_ENABLED`; `team` con `REPORTING_TEAM_ENABLED` y rol owner/admin. Un PUT con una clave que no aplica devuelve 422.
- Preferencia apagada: ese informe no se genera ni se envía (tampoco aparece en la campana). El diario existente pasa a respetar `daily_enabled`.
- UI: interruptores compactos en Settings › Resúmenes, bajo el resaltado del brief. Sin entrada nueva de navegación.

**Campana:**

- Popover en el mismo sitio, en lugar del enlace directo. Consulta al abrir y cada 60 s mientras la pestaña está visible (React Query no refresca en segundo plano). Al cerrar sesión el layout se desmonta y la recarga a `/login` limpia la caché: no queda intervalo vivo.
- «Informes»: las diez notificaciones de informe más recientes, leídas y sin leer, con título por tipo («Tu resumen del día», «Tu semana», «Tu equipo esta semana») y fecha del periodo. Abrir marca `read_at` y navega a `/dashboard/reports/:id`. El contador son los informes sin leer.
- «Vocify hizo» (solo con `NOTIFICATIONS_ACTIVITY_ENABLED`): se deriva al leer de dos registros que ya existen, sin copiarlos a otra tabla:
  - `crm_updates` con `status = 'success'` del propio usuario (auditoría reservar→ejecutar→confirmar de HubSpot, Pipedrive y Salesforce), agrupadas por memo: «CRM actualizado: deal, contacto y tareas» (tipos de recurso, sin recuento: una tarea reintentada no debe contar dos veces) y el porqué «Por tu conversación con {contacto}», enlazando a `/dashboard/memos/:id`.
  - `meeting_writes` con `stage_changed = true`: «Deal movido a la etapa de reunión agendada» y «Reunión acordada con {contacto}». `meeting_writes` no guardaba fecha: 053 añade `created_at` sin rellenar las filas antiguas; una fila sin fecha no se muestra (no se inventa cuándo ocurrió).
  - Últimos 7 días, máximo 8, más recientes primero. Solo filas del propio usuario y de memos de su empresa. No suman al contador: no tienen `read_at` porque no piden acción. Si la lectura falla, `activity: null` y la sección no aparece; nunca se presenta como «no hizo nada».
  - Los fallos de CRM no se listan aquí: ya se ven en la nota.

**Casos que deben fallar antes de implementar:**

| Caso | Resultado exigido |
|---|---|
| Tick el viernes 18:05 y otra vez el sábado | Un semanal y una notificación. |
| Lunes con diario y semanal | Dos informes distintos. |
| Semana sin actividad | Sin informe. |
| Día posterior a la generación | `covered: false`, no cero. |
| Viernes 17:59 local | No se genera. |
| Flag semanal apagado | Nada generado; preferencias sin `weekly`. |
| Preferencia semanal apagada | No se genera ni se envía. |
| Email semanal falla | Informe y notificación intactos; el reintento usa la misma clave. |
| Actividad con flag apagado | Sin clave `activity`. |
| `crm_updates` de otro usuario o fallidas | No aparecen. |
| `meeting_writes` sin fecha | No aparece. |
| Lectura de actividad falla | `activity: null`. |

**Fuera de alcance / abierto:** hora y día configurables; idioma del email; `GET /reports` (listado) sigue sin usarse; el diario existente reescribe su snapshot en cada tick de la tarde aunque ya se enviara (choca con C18, no se toca aquí).

## Verificación integrada y criterios de salida adicionales

Generar informe de un periodo local con actividad de prueba, abrir por campana y enlace email sin enviar correos reales no autorizados. Fallar envío, reintentar y verificar no duplicación. Ver periodo vacío y semanal parcial.

### Regresiones y comandos al cerrar

- `cd backend && .venv/bin/python -m pytest tests/reporting -q`
- `npm run build`
- `make test-js`

Ejecutar los comandos desde `/Users/danizal/getvocify`, salvo el `cd` explícito. Un directorio de pruebas indicado como nuevo solo estará disponible después de sus tareas; que hoy no exista no autoriza a omitirlo al ejecutar. Las pruebas de IA usan datos reales autorizados y anonimizados; los ejemplos sintéticos de este plan sirven solo para contratos y tests deterministas.

### Qué vuelve al coordinador

- [ ] Informe de `F13` con tarea/criterio → resultado → prueba o veredicto → commit, migración aplicada y contrato entregado.

- [ ] Comparación de interfaces producidas con `00-contracts.md`; ninguna divergencia silenciosa de campos, estados, permisos o semántica de `null`.

- [ ] Revisión SOLID y limpieza de listeners/jobs/efectos; los servicios no duplican interpretación que corresponde a extracción.

- [ ] Evidencia de todos los estados de UI especificados. En web, `reticle_act_and_wait` o `reticle_assert` con consecuencia explícita; en desktop/extensión, además el recorrido nativo. `unknown` y `no-fault` no cierran.

- [ ] Bloqueos y edge cases nuevos en `docs/superpowers/deliveries/F13/report.md` y en el commit/PR. No marcar completa mientras haya criterios pendientes; una suspensión debe nombrar las dependencias no afectadas.

## Handoff a la siguiente entrega

F15 reutiliza aggregate con scope de equipo y mismo formato de reportes; añade snapshot histórico de outcomes sin cambiar significado del informe personal ya enviado.
