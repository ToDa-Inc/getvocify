# F14 — Detección y traslado de meeting booked: plan ejecutable

> **Ejecución futura:** usar `executing-plans` dentro del subagente dedicado a esta entrega; la coordinación secuencial usa `subagent-driven-development`. Este documento es planificación, no una implementación ni una autorización para desplegar. Ninguna casilla de ejecución está completada.

**Objetivo:** Convertir acuerdo de reunión en propuesta revisable y una escritura CRM idempotente.

**Arquitectura:** F0 detecta hechos; F14 resuelve tiempo, expone propuesta y adapta aprobación/proveedores. La revisión es asíncrona posterior, no un evento del overlay.

**Stack:** FastAPI/Python, Supabase/PostgreSQL, React 18/TypeScript y módulos JS compartidos; Electron/extensión cuando figuren entre las superficies de esta entrega.

**Posición:** 12 de 16. **Estado:** planificada; no iniciada.

**Navegación:** [plan maestro](/Users/danizal/getvocify/proposed_plan.md) · [contratos](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-contracts.md) · [integración y gates](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-integration-and-gates.md)

**Fuentes de esta entrega:** P: [Prompt técnico](/Users/danizal/getvocify/docs/TECHNICAL_PLANNING_PROMPT_VOCIFY_V1.md) · A: [Análisis de producto](/Users/danizal/getvocify/docs/PRODUCT_PLANNING_ANALYSIS_2026-09-21.md).

## Entrada, salida y frontera de responsabilidad

| Tipo | Contrato de esta entrega |
|---|---|
| Recibe | C04 meeting/evidencia; C01 inicio/tiempos; approval preview y proveedores existentes. |
| Produce | C15 MeetingProposal y operaciones CRM auditadas; KPI de acuerdo separado de close. |
| Dependencias de código | [F0-F0.1](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/03-f0-f0.1-inteligencia-y-jobs.md), [F07](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/05-f07-ask-vocify.md) |
| Migración propia | 046_meeting_proposals.sql |
| No le corresponde | No calendario/invitaciones, stage sin mapeo explícito ni detección streaming; no bonus de scoring. |

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

## Feature: F14 — Detección y traslado de meeting booked

**Fuente:** A §5; P §5.1.4; pipeline de aprobación existente.  

**Prioridad:** V1.

### En una frase

Vocify detecta una reunión acordada, muestra la fecha y hora para revisión y permite trasladar esa información al CRM.

### Por qué (first principles)

Evita perder un acuerdo verbal y ofrece al responsable una métrica real. Una reunión acordada no equivale a una venta cerrada ni a una invitación enviada.

### Qué ya existe (auditoría)

- Jev, resolución parcial de fechas, propuestas, aprobación y auditoría CRM.

- Gap real: acuerdo mutuo, instante exacto y operación específica.

### Backend

- F0 extrae propuestas y confirmaciones; Jev devuelve `agreed`, `not_agreed` o `unknown`.

- Reutilizar resolución de fechas, añadiendo hora, zona y detección de ambigüedad.

- «A las cinco» sin contexto suficiente no se convierte automáticamente en 17:00.

- Conservar la última hora confirmada por ambas partes.

- Migración 046:

  - `meeting_proposals`: memo, evidencia, acuerdo, fecha/hora, zona, precisión, revisión, decisión y resultado CRM.

  - Ampliar restricciones de `crm_updates` para el tipo de operación necesario.

- Incorporar la propuesta al preview y al payload de aprobación existentes.

- La aprobación permite aceptar, corregir u omitir la propuesta.

- Fechas incompletas, identidad ambigua o zona no resuelta requieren revisión.

- Proveedor HubSpot: registrar actividad de reunión asociada al contacto/deal. Proveedor Pipedrive: actividad de tipo meeting.

- No crear invitaciones de calendario.

- No mover una etapa salvo que exista un mapeo explícito configurado por el administrador.

- Registrar identificador remoto y reconciliar antes de repetir una escritura cuyo resultado se desconozca.

La API de reuniones de HubSpot permite registrar estas actividades con inicio y asociaciones; no debe confundirse ese registro con enviar una invitación. [Documentación](https://developers.hubspot.com/docs/api-reference/legacy/crm/activities/meetings/guide).

**SOLID:** detección separada de decisión y escritura; cada proveedor traduce el mismo acuerdo aprobado.

### Frontend / Dashboard

- Bloque compartido dentro de la revisión existente.

- Fecha/hora editables y opción de omitir.

- Estados separados: «Detectada», «Pendiente de revisar», «Guardada en CRM».

- Copy: «Reunión acordada: martes 29, 17:00».

- No añadir un calendario propio.

#### Momento de detección y relación con el overlay — A13

**Decisión V1:** «Reunión detectada» aparece **después de la interacción, de forma asíncrona en su revisión**. No se emite un aviso de meeting booked en el overlay durante la conversación. La existencia de la ventana flotante permite técnicamente esa ampliación, pero no garantiza un acuerdo estable antes de que termine la conversación: la hora puede corregirse y la propuesta necesita revisión.

F14 consume la extracción final de F0 y actualiza el bloque compartido de revisión; si el comercial ya salió, encuentra el estado al volver al historial. No añade un canal de detección streaming ni una notificación flotante. F12 conserva el overlay para ayuda/checklist de la reunión actual; no interpreta su propio `grounded=true` como confirmación de una reunión futura.

| Resultado de extracción | Estado de la revisión |
|---|---|
| Todavía procesando | «Comprobando próximos pasos», sin fecha provisional presentada como acuerdo. |
| No hubo acuerdo | No mostrar una propuesta accionable; en el detalle puede constar «No se detectó una reunión acordada». |
| Acuerdo con datos completos | «Reunión detectada» con fecha, hora, zona y evidencia; se guarda en CRM solo después de aceptar. |
| Acuerdo o fecha ambiguos | «Revisa los datos de la reunión», con campos pendientes identificados y evidencia. No habilitar una escritura con valores inventados. |
| Escritura aprobada | «Guardada en CRM» únicamente al confirmar el resultado remoto; fallo o resultado incierto conservan su estado diferenciado. |

Esta decisión cierra A13 dentro del alcance V1; cambiarla a detección en vivo requiere revisar el contrato y las pruebas de confirmación temporal, no simplemente añadir texto al overlay.

### Criterio de aceptación (Definition of Done)

- [x] «Podríamos vernos» no produce un acuerdo confirmado.

- [x] Cambiar de 16:00 a 17:00 durante la conversación conserva 17:00.

- [x] Una fecha sin hora no recibe las 09:00 por defecto.

- [x] Zona horaria y cambios de horario se prueban expresamente.

- [x] Repetir aprobación no crea dos actividades.

- [x] Corregir una propuesta actualiza su decisión sin duplicar el KPI.

- [x] No se genera ningún evento de venta ganada a partir de este dato.

- [x] Durante el meeting no aparece «Reunión detectada» en el overlay; después de completar extracción sí aparece en la revisión cuando hay evidencia, sin escribir aún en CRM.

- [x] Ausencia de acuerdo, extracción pendiente y acuerdo con fecha incompleta producen estados distintos; reabrir la revisión recupera la misma propuesta y decisión.

### Riesgos / edge cases conocidos

Reprogramaciones, varios encuentros mencionados y reconocimiento incorrecto de números. Se conserva la evidencia del acuerdo y se muestra incertidumbre cuando exista.

## Mapa de archivos y responsabilidades

| Acción futura | Ruta | Responsabilidad |
|---|---|
| Crear | `/Users/danizal/getvocify/backend/app/services/meetings/proposals.py` | Propuesta desde acuerdo/evidencia. |
| Crear | `/Users/danizal/getvocify/backend/app/services/meetings/time_resolution.py` | Fecha/hora/zona/ambigüedad. |
| Crear | `/Users/danizal/getvocify/backend/migrations/046_meeting_proposals.sql` | Propuesta/decisión y crm_updates. |
| Modificar | `/Users/danizal/getvocify/backend/app/models/approval.py` | Bloque reunión en preview/payload. |
| Modificar | `/Users/danizal/getvocify/backend/app/services/memo_approval.py` | Aceptar/corregir/omitir y operación única. |
| Modificar | `/Users/danizal/getvocify/backend/app/services/crm_providers/protocols.py` | Capacidad de registrar reunión. |
| Modificar | `/Users/danizal/getvocify/backend/app/services/crm_providers/hubspot_provider.py` | Meeting activity. |
| Modificar | `/Users/danizal/getvocify/backend/app/services/crm_providers/pipedrive_provider.py` | Activity meeting. |
| Crear | `/Users/danizal/getvocify/backend/tests/meetings/test_proposals.py` | Acuerdo/fechas. |
| Crear | `/Users/danizal/getvocify/backend/tests/meetings/test_writes.py` | Idempotencia/reconciliación. |
| Crear | `/Users/danizal/getvocify/shared/ui/components/meeting-proposal.js` | Vista compartida de revisión. |
| Crear | `/Users/danizal/getvocify/shared/ui/components/v-meeting-proposal.js` | Elemento con edición explícita. |

Los archivos marcados «Crear» todavía no existen por esta planificación. Los marcados «Modificar» pueden ser producidos por una dependencia; su procedencia debe quedar indicada. Los tests y fixtures se crean en ejecución, nunca se confunden con datos de producción.

## Tareas secuenciales con ciclo TDD

Cada tarea termina con evidencia revisable. Los ejemplos de contrato y prueba fijan entradas/salidas futuras; no se han ejecutado ahora. Dividir los pasos de implementación en cambios pequeños dentro del mismo ciclo rojo → verde → revisión. No iniciar otra feature para esquivar un fallo.

### F14.01 — Resolver acuerdo y tiempo sin completar huecos

**Archivos:** meetings/proposals.py, time_resolution.py; tests/meetings/test_proposals.py.

**Interfaz y propiedad:** C15 agreed/not_agreed/unknown; precision exact/date_only/ambiguous/unknown. Última hora confirmada por ambos.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"proposal_id":"meet-1","agreement":"agreed","starts_at":null,"timezone":"Europe/Madrid","precision":"ambiguous","decision":"pending","crm_status":"not_requested","evidence_refs":["ev-5"]}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Podríamos vernos | No acuerdo confirmado. |
| 16:00 corregido a 17:00 confirmado | 17:00 con evidencia de corrección. |
| Las cinco sin contexto | Ambiguous, no 17:00 por defecto. |
| DST hora duplicada | Pide revisión de zona/offset. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/meetings/test_proposals.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Consumir meeting F0 y evidencia, sin otra extracción paralela en UI.

- [ ] Resolver relativo a inicio real/zona conocida; no usar upload time ni defaults09:00.

- [ ] Persistir propuesta por memo/revisión, conservando incertidumbre y fuente.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/meetings/test_proposals.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Pruebas temporales exactas y ambiguas; sin fecha inventada.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F14.01`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F14.02 — Extender aprobación y escribir una vez en CRM

**Archivos:** memo_approval.py; models/approval.py; providers; migration046; tests/meetings/test_writes.py.

**Interfaz y propiedad:** C15 aceptar/corregir/omitir ligado a proposal_id/input_revision. register_meeting recibe solo propuesta aprobada.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"proposal_id":"meet-1","input_revision":"rev-3","decision":"accept","starts_at":"2026-09-29T15:00:00Z","timezone":"Europe/Madrid"}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Repetir aprobación | Una actividad remota. |
| Timeout después de crear remoto | Estado uncertain y reconciliación antes de retry. |
| Sin stage mapping | Actividad creada, ninguna etapa cambiada. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/meetings/test_writes.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Añadir propuesta al preview y payload existentes sin romper aprobaciones legacy.

- [ ] Validar corrección explícita y target/fecha/zona antes de llamada provider.

- [ ] Persistir operation key, remote ID y estado; vincular acuerdos a un solo KPI aunque se corrija propuesta.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/meetings/test_writes.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Pruebas equivalentes HubSpot/Pipedrive y ninguna escritura sin aprobación válida.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F14.02`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F14.03 — Mostrar revisión posterior en tres superficies

**Archivos:** meeting-proposal render/element; MemoDetail/extension review/desktop review; test shared/ui/meeting-proposal.test.js nuevo.

**Interfaz y propiedad:** C15 estados pending/needs_review/accepted/omitted y crm status se muestran separados. No overlay meeting_booked.

**Ejemplo concreto de contrato o prueba a incorporar:**

```text
detectada -> pendiente de revisar -> aprobada -> guardada en CRM
                         -> omitida
aprobada -> resultado incierto -> reconciliar
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Extracción pendiente | Comprobando próximos pasos sin fecha provisional falsa. |
| No agreement | Sin CTA para guardar reunión. |
| Error CRM | No dice guardada; conserva revisión/propuesta. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `node --test shared/ui/meeting-proposal.test.js` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Implementar bloque shared con fecha/hora/zona editables y evidencia, acción omitir.

- [ ] Conectar aprobación actual; no abrir ventanas ni enviar invitación.

- [ ] Verificar que durante conversación el overlay no muestra reunión detectada y posterior revisión sí.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `node --test shared/ui/meeting-proposal.test.js` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Reticle y host nativo distinguen acuerdo, aprobación y resultado CRM.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F14.03`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

## Verificación integrada y criterios de salida adicionales

Meeting con dos horas mencionadas, final de 17:00; revisión muestra la final con zona y evidencia. Corregir y aprobar dos veces; solo una actividad remota. Simular timeout y comprobar reconciliación. No aparece aviso durante la conversación.

### Regresiones y comandos al cerrar

- `cd backend && .venv/bin/python -m pytest tests/meetings -q`
- `node --test shared/ui/meeting-proposal.test.js`
- `npm run build`
- `make check-generated`

Ejecutar los comandos desde `/Users/danizal/getvocify`, salvo el `cd` explícito. Un directorio de pruebas indicado como nuevo solo estará disponible después de sus tareas; que hoy no exista no autoriza a omitirlo al ejecutar. Las pruebas de IA usan datos reales autorizados y anonimizados; los ejemplos sintéticos de este plan sirven solo para contratos y tests deterministas.

### Qué vuelve al coordinador

- [ ] Informe de `F14` con tarea/criterio → resultado → prueba o veredicto → commit, migración aplicada y contrato entregado.

- [ ] Comparación de interfaces producidas con `00-contracts.md`; ninguna divergencia silenciosa de campos, estados, permisos o semántica de `null`.

- [ ] Revisión SOLID y limpieza de listeners/jobs/efectos; los servicios no duplican interpretación que corresponde a extracción.

- [ ] Evidencia de todos los estados de UI especificados. En web, `reticle_act_and_wait` o `reticle_assert` con consecuencia explícita; en desktop/extensión, además el recorrido nativo. `unknown` y `no-fault` no cierran.

- [ ] Bloqueos y edge cases nuevos en `docs/superpowers/deliveries/F14/report.md` y en el commit/PR. No marcar completa mientras haya criterios pendientes; una suspensión debe nombrar las dependencias no afectadas.

## Handoff a la siguiente entrega

F11 muestra la propuesta/resultado vigente; F13 cuenta acuerdos confirmados sin confundir escritura con venta. F15 observa resultados CRM por otro contrato independiente.
