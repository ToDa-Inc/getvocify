# F09 — Scoring sencillo y configurable: plan ejecutable

> **Ejecución futura:** usar `executing-plans` dentro del subagente dedicado a esta entrega; la coordinación secuencial usa `subagent-driven-development`. Este documento es planificación, no una implementación ni una autorización para desplegar. Ninguna casilla de ejecución está completada.

**Objetivo:** Evaluar proceso con evidencia, nota secundaria y adherencia matemáticamente explícita.

**Arquitectura:** LLM evalúa criterios contextualizados; Python calcula adherencia/cobertura. El score fija versiones y no incorpora bonus por resultado CRM.

**Stack:** FastAPI/Python, Supabase/PostgreSQL, React 18/TypeScript y módulos JS compartidos; Electron/extensión cuando figuren entre las superficies de esta entrega.

**Posición:** 11 de 16. **Estado:** planificada; no iniciada.

**Navegación:** [plan maestro](/Users/danizal/getvocify/proposed_plan.md) · [contratos](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-contracts.md) · [integración y gates](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-integration-and-gates.md)

**Fuentes de esta entrega:** A: [Análisis de producto](/Users/danizal/getvocify/docs/PRODUCT_PLANNING_ANALYSIS_2026-09-21.md) · D: [Estructura inteligente](/Users/danizal/getvocify/docs/features/ESTRUCTURA_INTELIGENTE.md).

## Entrada, salida y frontera de responsabilidad

| Tipo | Contrato de esta entrega |
|---|---|
| Recibe | C04 inteligencia/evidencia; C06 snapshot playbook; C13 objeciones/notas; C05 jobs. |
| Produce | C14 ScoreView, memos.score y GET /memos/{id}/score. |
| Dependencias de código | [F08](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/04-f08-playbooks.md), [F10](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/10-f10-objeciones-y-notas.md), [F0-F0.1](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/03-f0-f0.1-inteligencia-y-jobs.md) |
| Migración propia | 045_memo_scores.sql |
| No le corresponde | No consulta CRM ni transcript crudo; no nuevo playbook ni nuevos resultados de negocio. F14 no condiciona score. |

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

## Feature: F09 — Scoring sencillo y configurable

**Fuente:** A §4.1 y §4.4; D §3.3; decisión de adherencia de esta sesión.  

**Prioridad:** V1.

### En una frase

El comercial recibe una explicación de qué hizo bien y qué faltó respecto al proceso de su empresa, con una puntuación secundaria.

### Por qué (first principles)

El score sirve de referencia, no de verdad absoluta. Debe medir ejecución del proceso sin premiar automáticamente una llamada fácil.

### Qué ya existe (auditoría)

- Playbook versionado, inteligencia y objeciones contextualizadas.

- `LLMClient` y trabajos recuperables.

- Gap real: evaluación, almacenamiento y presentación.

### Backend

- Migración 045: añadir `memos.score` JSONB.

- Crear `/Users/danizal/getvocify/backend/app/services/coaching/scoring.py`.

- Entrada: inteligencia tipada, criterios y versión del playbook.

- Salida:

  - `value`: 0–10 o `null`.

  - `criteria`: `met`, `missed`, `not_applicable` o `unknown`, con evidencia.

  - `strengths`, `improvements`.

  - `applicable_steps`, `met_steps`, `coverage`.

  - Versiones de modelo, prompt, playbook e input.

- Prompt versionado; `SCORING_MODEL` usa por defecto la configuración de extracción.

- Evaluar contenido contextual con LLM; calcular adherencia en Python.

- Adherencia = pasos cumplidos / pasos aplicables conocidos. Los desconocidos se reflejan en cobertura; no cuentan como incumplimiento ni desaparecen sin indicarlo.

- Si no hay pasos evaluables, devolver `null`, no 0 %.

- Las objeciones no presentes no penalizan ni conceden puntos por haber sido «superadas».

- `GET /api/v1/memos/{id}/score`.

- El job no bloquea extracción ni aprobación.

- Cambiar el playbook no reescribe puntuaciones históricas automáticamente.

#### Resultado real y puntuación — A4

**Decisión de este plan para V1:** el resultado real **no añade ni resta puntos a `value: 0–10`**. El número evalúa la ejecución de los criterios del playbook con la evidencia disponible; la adherencia conserva su cálculo independiente de pasos cumplidos / pasos aplicables. Agendar una reunión, avanzar un deal o ganarlo se muestra como contexto cualitativo y como métrica de resultado en F13/F15, nunca como un bonus automático de la nota.

Una llamada fácil con meeting acordado no gana puntos por ese resultado; una objeción correctamente trabajada conserva su valoración aunque el deal no avance. Sí puede evaluarse un comportamiento del playbook como «propuso y confirmó un siguiente paso» cuando tiene evidencia; no es lo mismo que premiar que el CRM cambie después de etapa. Si se quiere ponderar resultados numéricamente en una versión futura, exige una decisión explícita y una nueva versión de la rúbrica.

El scoring no empieza a consultar el CRM por esta aclaración. F11/F13/F15 unen el score con el resultado observado y su fuente; un resultado CRM tardío actualiza ese contexto, sin recalcular la nota histórica. El prompt de F09 debe impedir que `meeting.agreed` u otros campos de resultado se usen como premio implícito al generar `value`.

#### Datos ausentes, criterios ambiguos y cobertura — B3

- Sin versión publicada para la tipología: no ejecutar una evaluación genérica; devolver `value=null` con motivo `missing_playbook`. Un borrador de F08 no sustituye a la versión publicada.
- Sin conversación evaluable o sin pasos aplicables conocidos: `value=null`, adherencia `null` y motivo concreto. Un contacto nuevo sin interacciones no tiene un score «inicial» de cero.
- Con transcripción parcial, mostrar qué criterios pudieron evaluarse y cuáles quedaron `unknown`. Si la evidencia no permite sostener una nota global, `value=null` aunque existan observaciones parciales; no completar criterios por analogía con otras llamadas.
- Si dos reglas del playbook se contradicen o la tipología no está resuelta, no elegir silenciosamente una interpretación. Marcar los criterios afectados como `unknown`, registrar las entradas conflictivas y devolver `value=null` mientras afecten a la rúbrica global. Owner/admin recibe acceso para revisar el playbook; member recibe la explicación sin controles de configuración.
- Diferenciar `not_applicable` (exclusión justificada por la conversación/rúbrica) de `unknown` (no se sabe). Mostrar recuentos de evaluables, no aplicables y desconocidos para que la cobertura no oculte incertidumbre. No publicar porcentajes sin denominador.

**SOLID:** evaluación cualitativa separada del cálculo determinista de métricas; sin acceder directamente al transcript ni al CRM.

### Frontend / Dashboard

- Componente de coaching dentro de la revisión.

- `useMemoScore` consulta mientras el trabajo está pendiente.

- Primero una fortaleza y una mejora; puntuación y criterios al ampliar.

- Copy: «Explicaste el valor, pero quedó sin responder la duda de precio».

- El manager configura qué es una buena interacción en el playbook existente.

El bloque usa estados explícitos: «Evaluando la interacción», «Falta configurar el proceso», «No hay evidencia suficiente para puntuar», «Proceso ambiguo: revisa los criterios», resultado parcial y resultado listo. En parcial se conservan observaciones respaldadas y se muestra la cobertura; en listo, primero fortaleza/mejora y después la nota ampliable. El resultado comercial, si está disponible, lleva su propia etiqueta y fecha; no se mezcla visualmente con el valor del score.

### Criterio de aceptación (Definition of Done)

- [ ] Cada observación tiene evidencia.

- [ ] Una llamada fácil no gana por defecto frente a una objeción bien trabajada.

- [ ] Sin playbook aparece «Falta configurar el proceso», no una nota genérica.

- [ ] Sin evidencia suficiente no se muestra un cero ficticio.

- [ ] La adherencia coincide con sus numerador y denominador.

- [ ] Se evalúa con al menos 20 conversaciones anotadas por el equipo, incluyendo los casos anteriores.

- [ ] El texto principal contiene acciones concretas y evita consejos genéricos.

- [ ] Con idéntica evidencia y rúbrica, cambiar solo el resultado externo del deal no cambia `value` ni adherencia; la evaluación de IA incluye el par «meeting conseguido fácilmente / objeción bien trabajada» sin premio automático por agenda.

- [ ] Empresa sin playbook, conversación sin datos, playbook contradictorio y transcripción parcial producen estados distintos. Ninguno inventa nota cero, criterios cumplidos ni denominadores.

- [ ] Un resultado CRM posterior actualiza el contexto de reporting sin sobrescribir el score ni su versión de playbook.

### Riesgos / edge cases conocidos

Conversaciones parciales, playbook ambiguo y cambios de tipología. La puntuación siempre conserva el marco y la cobertura con los que se calculó.

## Mapa de archivos y responsabilidades

| Acción futura | Ruta | Responsabilidad |
|---|---|
| Crear | `/Users/danizal/getvocify/backend/app/services/coaching/scoring.py` | Evaluación y ensamblado. |
| Crear | `/Users/danizal/getvocify/backend/app/services/coaching/metrics.py` | Cálculo determinista de adherencia/cobertura. |
| Crear | `/Users/danizal/getvocify/backend/app/prompts/scoring_v1.md` | Rúbrica versionada sin premio de resultado. |
| Crear | `/Users/danizal/getvocify/backend/app/api/coaching.py` | GET score; F11 añadirá brief. |
| Crear | `/Users/danizal/getvocify/backend/migrations/045_memo_scores.sql` | score JSONB. |
| Crear | `/Users/danizal/getvocify/backend/tests/coaching/test_scoring.py` | Evidencia y elegibilidad. |
| Crear | `/Users/danizal/getvocify/backend/tests/coaching/test_metrics.py` | Denominadores. |
| Crear | `/Users/danizal/getvocify/src/features/coaching/hooks/useMemoScore.ts` | Polling job y revisión. |
| Crear | `/Users/danizal/getvocify/src/components/dashboard/memos/CoachingScore.tsx` | Fortaleza/mejora antes del número. |

Los archivos marcados «Crear» todavía no existen por esta planificación. Los marcados «Modificar» pueden ser producidos por una dependencia; su procedencia debe quedar indicada. Los tests y fixtures se crean en ejecución, nunca se confunden con datos de producción.

## Tareas secuenciales con ciclo TDD

Cada tarea termina con evidencia revisable. Los ejemplos de contrato y prueba fijan entradas/salidas futuras; no se han ejecutado ahora. Dividir los pasos de implementación en cambios pequeños dentro del mismo ciclo rojo → verde → revisión. No iniciar otra feature para esquivar un fallo.

### F09.01 — Calcular adherencia y cobertura sin ceros ficticios

**Archivos:** coaching/metrics.py y tests/coaching/test_metrics.py.

**Interfaz y propiedad:** C14 compute_adherence(statuses): met_steps, applicable_steps, unknown_steps, coverage y adherence; unknown separado de missed.

**Ejemplo concreto de contrato o prueba a incorporar:**

```python
from app.services.coaching.metrics import compute_adherence

def test_unknown_is_not_a_failure():
    m = compute_adherence(["met", "missed", "unknown", "not_applicable"])
    assert m["met_steps"] == 1
    assert m["applicable_steps"] == 2
    assert m["unknown_steps"] == 1
    assert m["adherence"] == 0.5
    assert m["coverage"] == 2 / 3
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| met,missed,unknown,not_applicable | Adherence1/2; coverage2/3; unknown1. |
| Todo unknown o ningún evaluable | Adherence null; value no se inventa. |
| Combinar equipos | Sumar numeradores/denominadores, no media simple de porcentajes. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/coaching/test_metrics.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Implementar función pura con conteos conocidos y cobertura definida en C14.

- [ ] Validar estados de criterio; mantener not_applicable justificado por rúbrica/evidencia.

- [ ] Añadir tests de zero denominator y agregación desigual.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/coaching/test_metrics.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Cálculos reproducibles independientes del LLM.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F09.01`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F09.02 — Evaluar snapshot y persistir revisión vigente

**Archivos:** scoring.py, prompt/scoring_v1.md, migration045, tests/coaching/test_scoring.py.

**Interfaz y propiedad:** C14 criteria por step_id/version; value0..10 o null. Output cita evidence_refs disponibles, no inventa.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"status":"partial","value":null,"reason":"ambiguous_playbook","met_steps":1,"applicable_steps":2,"unknown_steps":1,"coverage":0.6666666667,"playbook_version_id":"pv-2","input_revision":"rev-2"}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Playbook ausente/ambiguo | Motivo explícito y value null. |
| Misma evidencia, outcome CRM distinto | Value/adherence iguales; no bonus automático. |
| Respuesta LLM cita inexistente | No publicar conclusión como válida. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/coaching/test_scoring.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Construir prompt desde criterios y evidencia F0/F10; no dar al consumidor una segunda lectura íntegra de transcript.

- [ ] Validar output/evidence/step IDs y aplicar métricas puras; si ambigüedad afecta rúbrica global, value null.

- [ ] Registrar kind score en worker y guardar con run_id/input_revision/playbook_version/model/prompt; cambiar playbook no recalcula historia automáticamente.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/coaching/test_scoring.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Stale write rechazado y casos IA críticos trazables a versiones.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F09.02`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F09.03 — Presentar coaching útil y validar calidad con datos autorizados

**Archivos:** api/coaching.py; CoachingScore.tsx; useMemoScore.ts; dataset/evaluación de dominio en tests/coaching.

**Interfaz y propiedad:** Estados de A4/B3; fortaleza/mejora primero, criterios/nota al ampliar; cliente no recalcula score.

**Ejemplo concreto de contrato o prueba a incorporar:**

```text
Fortaleza -> Mejora -> Ver criterios/nota
Sin evidencia suficiente -> sin puntuación
Resultado comercial -> contexto separado, no bonus
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Sin proceso | Falta configurar el proceso, CTA según rol. |
| Partial | Observaciones respaldadas y cobertura, sin cero. |
| 20 conversaciones anotadas | Incluye fácil, objeción trabajada, ambigua y sin evidencia. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `npm run build` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Servir vista con permisos de memo y polling solo mientras job pueda progresar.

- [ ] Implementar estados completos y enlaces a evidencia, sin mezclar outcome con número.

- [ ] Ejecutar evaluación versionada y revisión humana de 20 casos como mínimo; un fallo factual bloquea habilitar scoring.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `npm run build` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Veredicto UI y evaluación IA documentada sin inventar dataset ni declararlo disponible.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F09.03`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

## Verificación integrada y criterios de salida adicionales

Ver score de conversación respaldada, ampliar criterios/denominadores y abrir evidencia. Probar sin playbook y parcial. Actualizar outcome externo del deal sin cambiar evidencia: score histórico permanece igual.

### Regresiones y comandos al cerrar

- `cd backend && .venv/bin/python -m pytest tests/coaching/test_metrics.py tests/coaching/test_scoring.py -q`
- `npm run build`

Ejecutar los comandos desde `/Users/danizal/getvocify`, salvo el `cd` explícito. Un directorio de pruebas indicado como nuevo solo estará disponible después de sus tareas; que hoy no exista no autoriza a omitirlo al ejecutar. Las pruebas de IA usan datos reales autorizados y anonimizados; los ejemplos sintéticos de este plan sirven solo para contratos y tests deterministas.

### Qué vuelve al coordinador

- [ ] Informe de `F09` con tarea/criterio → resultado → prueba o veredicto → commit, migración aplicada y contrato entregado.

- [ ] Comparación de interfaces producidas con `00-contracts.md`; ninguna divergencia silenciosa de campos, estados, permisos o semántica de `null`.

- [ ] Revisión SOLID y limpieza de listeners/jobs/efectos; los servicios no duplican interpretación que corresponde a extracción.

- [ ] Evidencia de todos los estados de UI especificados. En web, `reticle_act_and_wait` o `reticle_assert` con consecuencia explícita; en desktop/extensión, además el recorrido nativo. `unknown` y `no-fault` no cierran.

- [ ] Bloqueos y edge cases nuevos en `docs/superpowers/deliveries/F09/report.md` y en el commit/PR. No marcar completa mientras haya criterios pendientes; una suspensión debe nombrar las dependencias no afectadas.

## Handoff a la siguiente entrega

F11 agrega fortalezas/mejoras sin reanalizar. F13/F15 usan met_steps/applicable_steps/unknown_steps; no recomputan note ni promedian porcentajes sin ponderar.
