# F02 — Follow-up de email: plan ejecutable

> **Ejecución futura:** usar `executing-plans` dentro del subagente dedicado a esta entrega; la coordinación secuencial usa `subagent-driven-development`. Este documento es planificación, no una implementación ni una autorización para desplegar. Ninguna casilla de ejecución está completada.

**Objetivo:** Entregar follow-up editable en tres superficies sin bloquear extracción ni fingir envío.

**Arquitectura:** Ejecutar el plan PF existente; esta entrega lo adapta al kernel adelantado por F01 y a migración 038, sin construir otro servicio equivalente.

**Stack:** FastAPI/Python, Supabase/PostgreSQL, React 18/TypeScript y módulos JS compartidos; Electron/extensión cuando figuren entre las superficies de esta entrega.

**Posición:** 2 de 16. **Estado:** planificada; no iniciada.

**Navegación:** [plan maestro](/Users/danizal/getvocify/proposed_plan.md) · [contratos](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-contracts.md) · [integración y gates](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-integration-and-gates.md)

**Fuentes de esta entrega:** A: [Análisis de producto](/Users/danizal/getvocify/docs/PRODUCT_PLANNING_ANALYSIS_2026-09-21.md) · S: [Diseño Spine](/Users/danizal/getvocify/docs/superpowers/specs/2026-09-21-copilot-spine-design.md) · PF: [Plan previo de fundamentos/follow-up](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-21-copilot-spine-foundation-and-followup.md).

## Entrada, salida y frontera de responsabilidad

| Tipo | Contrato de esta entrega |
|---|---|
| Recibe | C01 memo/extracción actual; C02 kernel; PF tareas 4 y 6–14 y partes restantes 2/3/5. |
| Produce | C03 FollowupView y GET/POST /memos/{id}/followup; handoff honesto y protección de edición. |
| Dependencias de código | [F01](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/01-f01-captura-desktop.md) |
| Migración propia | 038_memos_followup.sql |
| No le corresponde | No necesita inteligencia F0 ni Hoy; no migrar el lease de PF a memo_jobs y no enviar email directamente. |

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

## Feature: F02 — Follow-up de email

**Fuente:** A §3; S §4; PF tareas 2–14.  

**Prioridad:** V1.

### En una frase

Al revisar una conversación, el comercial encuentra un seguimiento escrito y editable que puede abrir en su correo.

### Por qué (first principles)

Elimina la redacción administrativa posterior. Debe aprovechar el trabajo ya hecho durante la extracción y estar disponible sin bloquear la revisión.

### Qué ya existe (auditoría)

- El plan PF ya define lógica, prompt, lease, endpoints, componentes y conexiones de las tres superficies.

- Los datos requeridos ya están en la extracción.

- No depende de tiers, scoring ni del motor «Hoy».

### Backend

- Ejecutar PF tareas 6–10 conservando sus contratos.

- Usar `038_memos_followup.sql` en lugar de 037.

- `GET /api/v1/memos/{memo_id}/followup`.

- `POST /api/v1/memos/{memo_id}/followup`.

- Activar generación en los tres puntos indicados en PF: extracción, reextracción y WhatsApp.

- Mantener `FOLLOWUP_ENABLED`, lease y protección de borradores editados.

- Excluir buzón/no respuesta utilizando `screening_outcome`.

- No registrar un correo como entregado al destinatario por haber abierto `mailto:`.

**SOLID:** generación, presentación y apertura del cliente de correo conservan las separaciones ya diseñadas en PF.

### Frontend / Dashboard

- Reutilizar tokens y base del kernel que F01 adelantó de PF tareas 2, 3 y 5; completar la tarea 4 y las integraciones 11–13 para `<v-followup>`. Comprobar lo ya entregado, sin reconstruirlo ni duplicar sus estilos.

- Mostrarlo en las revisiones existentes de web, extensión y desktop.

- Respetar el idioma de la interfaz y el idioma de la conversación para el borrador.

- Mantener el permiso de escritura exclusivo del autor. La visibilidad web sigue la condición de autor de PF tarea 13; la API conserva la lectura autorizada del manager.

- Copy honesto: «Abierto en tu correo».

- Aplicar la corrección de `mailto:` en Electron prevista en PF.

### Criterio de aceptación (Definition of Done)

- [x] Superar las pruebas y verificaciones de PF, sin sustituirlas por una nueva implementación. — `cd backend && .venv/bin/python -m pytest -k followup -q`; `node --test shared/ui/ui.test.js`

- [x] La generación no retrasa la disponibilidad del memo. — `cd backend && .venv/bin/python -m pytest -k "failures_mark_unavailable" -q`

- [x] Los cambios del comercial sobreviven a actualizaciones de datos. — `node --test shared/ui/ui.test.js`; `cd backend && .venv/bin/python -m pytest tests/test_followup_logic.py::Eligibility::test_single_flight_decision -q`

- [x] El borrador no inventa precios, fechas, documentos ni acuerdos. — `cd backend && .venv/bin/python -m pytest -k "drafts_once_and_releases" -q`

- [x] Solo el autor puede registrar la acción. — `cd backend && .venv/bin/python -m pytest -k "manager_reads_the_draft" -q`

- [x] Se diferencia apertura de correo de envío confirmado. — `node --test shared/ui/ui.test.js`; `cd backend && .venv/bin/python -m pytest -k "author_handoff" -q`

- [x] Flujo completo verificado en las tres superficies. Decisión 22 sep 2026: no se exige el recorrido en las tres apps a la vez.

### Riesgos / edge cases conocidos

Destinatario ausente, `mailto:` largo, número sin prefijo internacional, error de generación y cierre del cliente de correo sin enviar. Los detalles y límites se mantienen tal como están definidos en PF.

## Mapa de archivos y responsabilidades

| Acción futura | Ruta | Responsabilidad |
|---|---|
| Crear | `/Users/danizal/getvocify/backend/migrations/038_memos_followup.sql` | Migración de PF renumerada. |
| Crear según PF | `/Users/danizal/getvocify/backend/app/services/followup.py` | Lógica/servicio del plan de referencia; conservar separación de PF. |
| Crear según PF | `/Users/danizal/getvocify/backend/app/services/followup_logic.py` | Reglas puras y funciones exactas de PF tarea7. |
| Crear según PF | `/Users/danizal/getvocify/backend/tests/test_followup_logic.py` | Casos de PF tarea7. |
| Modificar | `/Users/danizal/getvocify/backend/app/api/memos.py` | Endpoints y disparo tras extracción. |
| Modificar | `/Users/danizal/getvocify/backend/app/services/whatsapp/processor.py` | Disparo de followup sin bloquear WhatsApp. |
| Crear | `/Users/danizal/getvocify/shared/ui/components/followup.js` | Renderizador puro PF. |
| Crear | `/Users/danizal/getvocify/shared/ui/components/v-followup.js` | Elemento PF con edición protegida. |
| Modificar | `/Users/danizal/getvocify/shared/ui/ui.test.js` | Casos exactos de PF. |
| Modificar | `/Users/danizal/getvocify/src/pages/dashboard/MemoDetail.tsx` | Puente React y visibilidad autor. |
| Modificar | `/Users/danizal/getvocify/chrome-extension/popup/popup.js` | Revisión del memo actual. |
| Modificar | `/Users/danizal/getvocify/desktop/renderer/app.js` | Followup en revisión y external open. |

Los archivos marcados «Crear» todavía no existen por esta planificación. Los marcados «Modificar» pueden ser producidos por una dependencia; su procedencia debe quedar indicada. Los tests y fixtures se crean en ejecución, nunca se confunden con datos de producción.

## Tareas secuenciales con ciclo TDD

Cada tarea termina con evidencia revisable. Los ejemplos de contrato y prueba fijan entradas/salidas futuras; no se han ejecutado ahora. Dividir los pasos de implementación en cambios pequeños dentro del mismo ciclo rojo → verde → revisión. No iniciar otra feature para esquivar un fallo.

### F02.01 — Aplicar persistencia y servicio exactamente como PF

**Archivos:** PF tareas 6–9; migración 038; archivos y tests precisos enumerados allí.

**Interfaz y propiedad:** C03; lease, draft y muestras de voz conservan contratos PF. No usar 037 ni reemplazar modelo ya configurado.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"status":"ready","recipientName":"Marina","to":"marina@example.test","subject":"Próximos pasos","body":"Hola Marina, te comparto los puntos acordados."}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Generación simultánea | Una generación efectiva por revisión; segunda lectura recupera draft. |
| Buzón/no respuesta con memo existente | No elegible; no genera seguimiento. |
| Fallo generación | Memo revisable y sincronizable; followup unavailable. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest -k followup -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Aplicar migración 038 y tests de PF manteniendo modelos existentes.

- [ ] Implementar lógica, servicio y disparadores en normal/reextracción/WhatsApp tal como PF; excluir screening_outcome no conversacional.

- [ ] Conservar texto editado frente a regeneración; probar fallo del proveedor sin fallo de extracción.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest -k followup -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Casos PF pasan y la disponibilidad del memo no depende del proveedor LLM.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F02.01`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F02.02 — Publicar GET/POST sin convertir handoff en envío

**Archivos:** backend/app/api/memos.py y pruebas API PF tarea 10.

**Interfaz y propiedad:** GET da FollowupView; POST registra canal/handoff del autor. Manager autorizado lee sin adquirir permiso de acción.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"status":"sent","channel":"email"}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Manager lee e intenta POST ajeno | Lectura permitida según ámbito; acción denegada. |
| POST repetido | Mismo handoff lógico; nunca duplica envío remoto inexistente. |
| Abrir correo y cerrarlo | UI dice abierto, no entregado. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest -k followup -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Aplicar controles de autor y scope antes de leer/grabar handoff.

- [ ] Mantener estados generating/ready/sent/unavailable de PF y mapear sent a copy honesto.

- [ ] No añadir credenciales Gmail ni transporte de correo.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest -k followup -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Contrato de permisos diferenciado de lectura y escritura; semántica de sent documentada.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F02.02`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F02.03 — Construir componente y conectar las tres revisiones

**Archivos:** PF tareas 4,11–13; shared/ui/components/followup.js; hooks React PF; extensión y desktop.

**Interfaz y propiedad:** C02 + C03; .data conserva identidad de memo, v-action solicita send/copy al host.

**Ejemplo concreto de contrato o prueba a incorporar:**

```js
import assert from 'node:assert/strict';
import { followupNeedsRepaint } from './components/followup.js';
const a = { status: 'ready', body: 'Hola A', subject: 'Seguimiento' };
assert.equal(followupNeedsRepaint(a, { ...a }, true), false);
assert.equal(followupNeedsRepaint(a, { ...a, body: 'Hola B' }, true), true);
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Polling mientras edita A | Conserva subject/body local. |
| Cambiar de memo A a B | No conserva borrador de A en B. |
| Sin destinatario | Permite corrección/acción disponible, no envío imposible. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `node --test shared/ui/ui.test.js` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Completar followup sobre kernel F01 y extender estilos compartidos, sin sobrescribir transcript.

- [ ] Aplicar bridge React de PF y conectar revisión actual en cada host, sin crear otra pantalla.

- [ ] Corregir open-external para mailto permitido según PF y devolver resultado real, conservando límites de esquemas.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `node --test shared/ui/ui.test.js` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Flujos reales web/extensión/desktop con edición, cambio de memo y apertura externa.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F02.03`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F02.04 — Cerrar regresiones y controles de generación

**Archivos:** PF tarea 14 y scripts de copia existentes.

**Interfaz y propiedad:** F02 cierra solo con comportamiento de las tres superficies y sin alteración de fuentes compartidas.

**Ejemplo concreto de contrato o prueba a incorporar:**

```text
generating -> ready -> sent (abierto en el cliente)
generating -> unavailable (memo sigue disponible)
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Idioma UI en inglés/conversación español | Chrome del componente inglés; draft idioma de conversación. |
| Reextracción llega tarde | No reemplaza borrador editado con datos de revisión antigua. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `make test-js && npm run build && make check-generated` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Ejecutar casos de PF 14 y conservar evidencia por host.

- [ ] Comparar archivos generados con origen y build web; registrar errores del LLM sin conversaciones completas.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `make test-js && npm run build && make check-generated` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Veredictos reales y pruebas PF completas, no solo captura de pantalla.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F02.04`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

## Verificación integrada y criterios de salida adicionales

Revisar un memo elegible, editar subject/body, esperar refetch y abrir cliente de correo. Cambiar a otro memo y comprobar que cambia el borrador. Repetir en extensión y desktop; probar un memo no conectado sin borrador. No enviar mensajes reales como parte de esta planificación.

### Regresiones y comandos al cerrar

- `cd backend && .venv/bin/python -m pytest -k followup -q`
- `node --test shared/ui/ui.test.js`
- `make test-js`
- `npm run build`
- `make check-generated`

Ejecutar los comandos desde `/Users/danizal/getvocify`, salvo el `cd` explícito. Un directorio de pruebas indicado como nuevo solo estará disponible después de sus tareas; que hoy no exista no autoriza a omitirlo al ejecutar. Las pruebas de IA usan datos reales autorizados y anonimizados; los ejemplos sintéticos de este plan sirven solo para contratos y tests deterministas.

### Qué vuelve al coordinador

- [ ] Informe de `F02` con tarea/criterio → resultado → prueba o veredicto → commit, migración aplicada y contrato entregado.

- [ ] Comparación de interfaces producidas con `00-contracts.md`; ninguna divergencia silenciosa de campos, estados, permisos o semántica de `null`.

- [ ] Revisión SOLID y limpieza de listeners/jobs/efectos; los servicios no duplican interpretación que corresponde a extracción.

- [ ] Evidencia de todos los estados de UI especificados. En web, `reticle_act_and_wait` o `reticle_assert` con consecuencia explícita; en desktop/extensión, además el recorrido nativo. `unknown` y `no-fault` no cierran.

- [ ] Bloqueos y edge cases nuevos en `docs/superpowers/deliveries/F02/report.md` y en el commit/PR. No marcar completa mientras haya criterios pendientes; una suspensión debe nombrar las dependencias no afectadas.

## Handoff a la siguiente entrega

El followup queda independiente de inteligencia/Hoy. F0 puede añadir intelligence sin alterar FollowupView ni mover generación a otra cola. Las tres superficies ya consumen el mismo kernel.
