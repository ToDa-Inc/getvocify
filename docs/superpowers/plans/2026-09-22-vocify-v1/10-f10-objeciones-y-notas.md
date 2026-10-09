# F10 — Clasificación de objeciones y notas en tiempo real: plan ejecutable

> **Ejecución futura:** usar `executing-plans` dentro del subagente dedicado a esta entrega; la coordinación secuencial usa `subagent-driven-development`. Este documento es planificación, no una implementación ni una autorización para desplegar. Ninguna casilla de ejecución está completada.

**Objetivo:** Conservar anotaciones humanas y hechos estructurados de objeción/respuesta con tiempo y procedencia.

**Arquitectura:** Captura guarda notas; extracción interpreta combinando fuentes diferenciadas; patterns persiste hechos. Review, live y equipo son consumidores distintos.

**Stack:** FastAPI/Python, Supabase/PostgreSQL, React 18/TypeScript y módulos JS compartidos; Electron/extensión cuando figuren entre las superficies de esta entrega.

**Posición:** 10 de 16. **Estado:** planificada; no iniciada.

**Navegación:** [plan maestro](/Users/danizal/getvocify/proposed_plan.md) · [contratos](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-contracts.md) · [integración y gates](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-integration-and-gates.md)

**Fuentes de esta entrega:** A: [Análisis de producto](/Users/danizal/getvocify/docs/PRODUCT_PLANNING_ANALYSIS_2026-09-21.md) · S: [Diseño Spine](/Users/danizal/getvocify/docs/superpowers/specs/2026-09-21-copilot-spine-design.md) · I: [Integración de superficies](/Users/danizal/getvocify/docs/features/PLAN_INTEGRACION.md).

## Entrada, salida y frontera de responsabilidad

| Tipo | Contrato de esta entrega |
|---|---|
| Recibe | C01 reloj/captura; C04 EvidenceRef/objections; C05 revisión/jobs. |
| Produce | C13 Annotation/InteractionPattern; endpoints de notas y revisión; hechos consumibles por scoring/brief/equipo. |
| Dependencias de código | [F01](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/01-f01-captura-desktop.md), [F0-F0.1](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/03-f0-f0.1-inteligencia-y-jobs.md) |
| Migración propia | 044_interaction_annotations_patterns.sql |
| No le corresponde | No construir F12 live ni F15 agregación aquí; no inferir tono/emoción y no etiquetar eficacia por existir. |

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

## Feature: F10 — Clasificación de objeciones y notas en tiempo real

**Fuente:** A §4.5; S §5.2; I §3.6 y §3.8.  

**Prioridad:** V1.

### En una frase

Vocify distingue las objeciones relevantes y permite al comercial anotar un matiz durante la conversación para interpretarla correctamente después.

### Por qué (first principles)

Una transcripción puede perder intención o contexto. La nota humana cubre ese hueco sin prometer reconocimiento de emociones.

### Qué ya existe (auditoría)

- `objections[]` como texto.

- Taxonomía: `price`, `timing`, `authority`, `competitor`, `status_quo`, `trust`, `other`.

- F01 aporta reloj y evidencia temporal; F0 define salida estructurada.

- Gap real: notas durante captura y hechos de objeción/respuesta persistidos.

### Backend

- Migración 044:

  - `interaction_annotations`: empresa, autor, captura/memo, texto, `offset_ms`, turno opcional, revisión y fechas.

  - `interaction_patterns`: empresa, memo, evidencia, categoría, respuesta observada, resolución y referencias al resultado.

- Nota creada antes de tener memo: conservarla con `client_capture_id`; asociarla al completar la captura.

- `PUT /api/v1/memos/{id}/annotations/{annotation_id}`.

- `GET /api/v1/memos/{id}/annotations`.

- La extracción contextual considera transcripción y notas distinguiendo sus autores.

- Jev clasifica categoría y objeción/obstáculo sobre esa evidencia.

- Almacenar resolución como `resolved`, `open` o `unknown`.

- Registrar menciones y afirmaciones de competidores desde F0 para F15.

- No etiquetar un patrón como eficaz por existir. Su resultado debe venir de meeting confirmado o estado real CRM.

**SOLID:** notas almacenan aportaciones humanas; extracción interpreta; clasificador acota; patrones conservan hechos.

### Frontend / Dashboard

- Campo discreto «Añadir nota» en la captura desktop y en las superficies de llamada que ya muestran captura activa.

- Guardado local inmediato y sincronización idempotente.

- En revisión, notas situadas en su momento y claramente atribuidas al comercial.

- `useInteractionAnnotations` en web.

- Copy: «02:14 · Lo dijo con ironía».

- No confundir estas notas con feedback del manager ni añadir un editor de coaching completo.

#### Qué se ve dónde — A5

| Superficie | Cuándo es relevante | Qué se muestra y quién lo entrega |
|---|---|---|
| Desktop / extensión durante una captura compatible | En el momento, para registrar contexto y responder | F10 aporta «Añadir nota» y la evidencia de la objeción actual cuando exista. La sugerencia opcional respaldada y checklist de meetings pertenecen a F12; desktop los muestra en el overlay. La extensión conserva su captura/asistencia actual: esta tabla no habilita coaching nuevo de cold calls ni exige construir una captura de meetings nueva. |
| Dashboard, revisión de una interacción pasada | Después, para aprender | Lista de objeciones de esa interacción con categoría, cita, respuesta observada y estado «Resuelta / Abierta / Sin determinar». F11 las integra en el brief; ampliar abre evidencia y notas en su momento. |
| Dashboard, panel de equipo | Ver patrones del conjunto | F15 agrega frecuencia por categoría, resolución observada y ejemplos; el filtro por comercial permite estudiar quién las maneja sin crear un ranking. La etiqueta «resuelta» no equivale a atribuirle una venta. |

Estas vistas consumen los mismos hechos de `interaction_patterns`, con alcance y momento distintos; no crean tres analizadores ni vuelven a clasificar en el cliente. Antes de entregar F11/F12/F15 solo se habilitan los controles y datos realmente disponibles en F10.

**Archivos previstos de presentación:** `/Users/danizal/getvocify/src/components/dashboard/memos/InteractionObjections.tsx` para revisión y `/Users/danizal/getvocify/src/features/coaching/hooks/useInteractionAnnotations.ts` para notas; las integraciones de captura usan el renderer desktop importado y `/Users/danizal/getvocify/chrome-extension/popup/popup.js`.

Sin objeciones detectadas y con análisis completo: «No se detectaron objeciones en esta interacción». Si la extracción está pendiente o parcial, mostrar ese estado en lugar de la afirmación anterior. Sin respuesta atribuible, mantener resolución `unknown` y «No hay evidencia suficiente para determinar cómo se resolvió»; no inventar una contestación del comercial.

### Criterio de aceptación (Definition of Done)

- [x] La nota sobrevive a desconexión y cierre de captura.

- [x] El tiempo corresponde al reloj de la interacción. Decisión 22 sep 2026: la nota no necesita un instante exacto del audio.

- [x] No se atribuye una anotación a palabras del prospecto.

- [x] Clasificación usa exclusivamente la taxonomía acordada.

- [x] «Ahora estoy conduciendo» puede clasificarse como obstáculo, sin convertirlo en objeción comercial por defecto.

- [x] «Qué barato» con una nota de ironía se evalúa considerando esa nota.

- [x] No se añade análisis de tono ni emociones.

- [x] La revisión muestra categoría, respuesta y resolución con su evidencia; la ausencia de objeciones se distingue de un análisis incompleto y no produce métricas ficticias de éxito.

- [x] Las tres vistas respetan su alcance: F10 persiste hechos, F11 resume, F12 asiste en meetings y F15 agrega sin reanalizar ni ampliar coaching de cold calls.

### Riesgos / edge cases conocidos

Notas sin transcripción próxima, audio sin tiempos y reordenación de texto tras corrección. El offset original permanece; no se fabrica un turno exacto cuando no puede vincularse.

## Mapa de archivos y responsabilidades

| Acción futura | Ruta | Responsabilidad |
|---|---|
| Crear | `/Users/danizal/getvocify/backend/app/models/annotations.py` | Nota humana y referencias. |
| Crear | `/Users/danizal/getvocify/backend/app/services/annotations.py` | Persistencia/versionado de notas. |
| Crear | `/Users/danizal/getvocify/backend/app/services/intelligence/patterns.py` | Proyección de hechos por revisión. |
| Crear | `/Users/danizal/getvocify/backend/app/api/annotations.py` | GET/PUT notas. |
| Modificar | `/Users/danizal/getvocify/backend/app/services/extraction.py` | Notas como fuente distinta. |
| Crear | `/Users/danizal/getvocify/backend/migrations/044_interaction_annotations_patterns.sql` | Anotaciones y patrones. |
| Crear | `/Users/danizal/getvocify/backend/tests/intelligence/test_annotations.py` | Tiempo/autor/idempotencia. |
| Crear | `/Users/danizal/getvocify/backend/tests/intelligence/test_patterns.py` | Categoría/resolución/evidencia. |
| Crear | `/Users/danizal/getvocify/src/components/dashboard/memos/InteractionObjections.tsx` | Revisión posterior. |
| Crear | `/Users/danizal/getvocify/src/features/coaching/hooks/useInteractionAnnotations.ts` | Lectura/mutación. |
| Modificar | `/Users/danizal/getvocify/desktop/renderer/app.js` | Añadir nota durante captura. |
| Modificar | `/Users/danizal/getvocify/chrome-extension/popup/popup.js` | Notas en captura existente. |

Los archivos marcados «Crear» todavía no existen por esta planificación. Los marcados «Modificar» pueden ser producidos por una dependencia; su procedencia debe quedar indicada. Los tests y fixtures se crean en ejecución, nunca se confunden con datos de producción.

## Tareas secuenciales con ciclo TDD

Cada tarea termina con evidencia revisable. Los ejemplos de contrato y prueba fijan entradas/salidas futuras; no se han ejecutado ahora. Dividir los pasos de implementación en cambios pequeños dentro del mismo ciclo rojo → verde → revisión. No iniciar otra feature para esquivar un fallo.

### F10.01 — Guardar notas idempotentes antes y después de tener memo

**Archivos:** annotations.py router/service/model; migration044; tests/intelligence/test_annotations.py.

**Interfaz y propiedad:** C13 annotation_id cliente, client_capture_id/memo_id, offset_ms monotónico y autor servidor.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"annotation_id":"note-1","client_capture_id":"cap-local-1","text":"Lo dijo con ironía","offset_ms":134000,"revision":1}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Offline antes de memo asignado | Nota local y replay una vez al resolver capture_id. |
| Reintento misma annotation_id | Misma nota, no dos interpretaciones. |
| Nota editada concurrentemente | Revisión condicional, no pérdida silenciosa. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/intelligence/test_annotations.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Conservar nota local inmediatamente y vincularla a captura; sync cuando C01 devuelve memo reservado.

- [ ] Usar PUT idempotente y versionado de texto; mantener offset original al corregir transcript.

- [ ] Validar permisos/tiempo no negativo y registrar provenance=human_note.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/intelligence/test_annotations.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Cierre/desconexión no pierden nota; otro autor no puede mutar.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F10.01`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F10.02 — Clasificar y persistir patrones sin duplicar análisis

**Archivos:** extraction.py, intelligence/patterns.py, tests/intelligence/test_patterns.py.

**Interfaz y propiedad:** C13 category: price/timing/authority/competitor/status_quo/trust/other; kind objection/obstacle/unknown; resolution resolved/open/unknown.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"pattern_id":"pat-1","category":"price","kind":"objection","resolution":"unknown","response":null,"evidence_refs":["ev-1","note-1"],"input_revision":"rev-2"}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Conduciendo sin objeción comercial | Obstacle, no fallo de venta. |
| Ironía anotada | Considera nota pero no atribuye palabras al prospecto. |
| Reextracción corrige resolved | Proyección vigente sustituye anterior, sin doble frecuencia. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/intelligence/test_patterns.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Incorporar nota revisionada a entrada de extracción y evidence con source type correcto.

- [ ] Usar clasificaciones F0/Jev; persistir hechos solo de revisión vigente con IDs/evidencia.

- [ ] Invalidar consumidores por revisión y mantener unknown cuando no hay respuesta atribuible.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/intelligence/test_patterns.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Hechos conservan fuente y no afirman eficacia causal.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F10.02`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F10.03 — Conectar notas y revisión con las tres vistas delimitadas

**Archivos:** InteractionObjections.tsx, hook, desktop/extension capture.

**Interfaz y propiedad:** F10 habilita nota y revisión; live usa F12 y agregado F15 cuando existan, según tabla A5.

**Ejemplo concreto de contrato o prueba a incorporar:**

```text
F10: nota + hechos de una interacción
F11: resumen posterior de esos hechos
F12: ayuda durante meeting
F15: frecuencias y ejemplos del equipo
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Sin objeciones completo | No se detectaron objeciones. |
| Análisis parcial | No afirmar ausencia; conservar evidencia válida. |
| Nota sin turno localizable | Offset y autor, no falsa reproducción. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `npm run build` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Añadir campo discreto de nota y estado guardado/sincronizando/error.

- [ ] Renderizar objeción/categoría/respuesta/resolución con detalle de fuente en revisión.

- [ ] Vincular audio solo si C01 permite reproducir tramo; no crear editor de feedback manager.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `npm run build` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Captura->nota offline->revisión muestra misma nota en tiempo correcto.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F10.03`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

## Verificación integrada y criterios de salida adicionales

Añadir nota durante reunión, cortar red y recuperar. En revisión leer objeción/respuesta con evidencia y cita humana diferenciada. Reextraer corrigiendo interpretación; scoring/Hoy no consumen proyección vieja.

### Regresiones y comandos al cerrar

- `cd backend && .venv/bin/python -m pytest tests/intelligence/test_annotations.py tests/intelligence/test_patterns.py -q`
- `npm run build`
- `make test-js`

Ejecutar los comandos desde `/Users/danizal/getvocify`, salvo el `cd` explícito. Un directorio de pruebas indicado como nuevo solo estará disponible después de sus tareas; que hoy no exista no autoriza a omitirlo al ejecutar. Las pruebas de IA usan datos reales autorizados y anonimizados; los ejemplos sintéticos de este plan sirven solo para contratos y tests deterministas.

### Qué vuelve al coordinador

- [ ] Informe de `F10` con tarea/criterio → resultado → prueba o veredicto → commit, migración aplicada y contrato entregado.

- [ ] Comparación de interfaces producidas con `00-contracts.md`; ninguna divergencia silenciosa de campos, estados, permisos o semántica de `null`.

- [ ] Revisión SOLID y limpieza de listeners/jobs/efectos; los servicios no duplican interpretación que corresponde a extracción.

- [ ] Evidencia de todos los estados de UI especificados. En web, `reticle_act_and_wait` o `reticle_assert` con consecuencia explícita; en desktop/extensión, además el recorrido nativo. `unknown` y `no-fault` no cierran.

- [ ] Bloqueos y edge cases nuevos en `docs/superpowers/deliveries/F10/report.md` y en el commit/PR. No marcar completa mientras haya criterios pendientes; una suspensión debe nombrar las dependencias no afectadas.

## Handoff a la siguiente entrega

F09 recibe patrones/evidencia contextualizados por revisión. F05 sigue leyendo C04; F10 mejora la proyección de hechos sin cambiar clave de señal ni duplicar extracción.
