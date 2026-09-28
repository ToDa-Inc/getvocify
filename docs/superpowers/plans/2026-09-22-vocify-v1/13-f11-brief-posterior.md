# F11 — Brief post-interacción configurable: plan ejecutable

> **Ejecución futura:** usar `executing-plans` dentro del subagente dedicado a esta entrega; la coordinación secuencial usa `subagent-driven-development`. Este documento es planificación, no una implementación ni una autorización para desplegar. Ninguna casilla de ejecución está completada.

**Objetivo:** Ofrecer un brief corto posterior con estados honestos y preferencia de cuándo destacarlo.

**Arquitectura:** Agregador de resultados existentes; job recuperable, sin segunda lectura de transcript ni LLM. Disponibilidad y elegibilidad son conceptos distintos.

**Stack:** FastAPI/Python, Supabase/PostgreSQL, React 18/TypeScript y módulos JS compartidos; Electron/extensión cuando figuren entre las superficies de esta entrega.

**Posición:** 13 de 16. **Estado:** planificada; no iniciada.

**Navegación:** [plan maestro](/Users/danizal/getvocify/proposed_plan.md) · [contratos](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-contracts.md) · [integración y gates](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-integration-and-gates.md)

**Fuentes de esta entrega:** P: [Prompt técnico](/Users/danizal/getvocify/docs/TECHNICAL_PLANNING_PROMPT_VOCIFY_V1.md) · A: [Análisis de producto](/Users/danizal/getvocify/docs/PRODUCT_PLANNING_ANALYSIS_2026-09-21.md).

## Entrada, salida y frontera de responsabilidad

| Tipo | Contrato de esta entrega |
|---|---|
| Recibe | C14 ScoreView; C13 patrones; C15 meeting proposal; C01 evidencia/audio; C05 jobs. |
| Produce | C16 PostInteractionBrief, preferencias y GET /memos/{id}/brief. |
| Dependencias de código | [F09](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/11-f09-scoring.md), [F10](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/10-f10-objeciones-y-notas.md), [F14](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/12-f14-meeting-booked.md), [F0-F0.1](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/03-f0-f0.1-inteligencia-y-jobs.md) |
| Migración propia | 047_post_interaction_briefs.sql |
| No le corresponde | No evalúa scoring ni espera audio para mostrar cita; preferencia no bloquea procesamiento. |

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

## Feature: F11 — Brief post-interacción configurable

**Fuente:** A §4.6; P §5.1.4.  

**Prioridad:** V1.

### En una frase

El comercial puede revisar qué salió bien y qué mejorar después de la conversación, cuando le venga bien.

### Por qué (first principles)

El feedback tiene valor, pero no debe interrumpir una secuencia de llamadas ni retrasar la actualización del CRM.

### Qué ya existe (auditoría)

- Resumen, scoring, objeciones y meeting booked.

- Trabajos recuperables de F0.

- Gap real: presentación conjunta y preferencia de disponibilidad.

### Backend

- Migración 047: `memos.coaching_brief` y preferencias individuales.

- Crear `/Users/danizal/getvocify/backend/app/services/coaching/briefs.py`.

- Agregar resultados existentes: una fortaleza, una mejora y hasta tres evidencias.

- No hacer una segunda lectura del transcript.

- No es necesaria otra llamada al LLM para V1: reutilizar los textos del scoring y plantillas.

- `GET /api/v1/memos/{id}/brief`.

- `GET/PUT /api/v1/me/coaching-preferences`.

- Preferencia: disponibilidad al terminar, diferida o al final del día.

- Valor inicial: disponible al terminar, sin abrir ventanas ni interrumpir.

- La preferencia cambia cuándo se destaca; el procesamiento sigue en segundo plano.

- Si un resultado está incompleto, indicarlo y completar la misma revisión al finalizar.

- El contrato de `GET /api/v1/memos/{id}/brief` incluye `status`, `reason`, `input_revision`, `sections` y disponibilidad de audio/evidencias. Los estados de presentación siguientes se derivan de elegibilidad, jobs y resultados persistidos; no requieren una cola nueva ni cambian la migración 047.

**SOLID:** brief agrega; scoring evalúa; preferencias deciden disponibilidad.

### Frontend / Dashboard

- Ampliación del bloque de coaching en revisión.

- `usePostInteractionBrief`.

- Acceso posterior desde el historial.

- Si hay audio y tiempos, «Escuchar momento» abre el fragmento.

- Si no existen, mostrar la cita sin botón de reproducción ficticio.

#### Estados visuales del brief — A11

El contenedor de `/Users/danizal/getvocify/src/components/dashboard/memos/PostInteractionBrief.tsx`, conectado a `usePostInteractionBrief`, conserva el mismo espacio durante la carga y distingue:

| Estado API/UI | Condición | Presentación y salida |
|---|---|---|
| `pending` — Pendiente | Elegible, esperando extracción/scoring o trabajo reclamado. | «Preparando tu resumen». Skeleton del bloque final. Actualizar por el job persistido, sin bloquear aprobación ni la llamada siguiente. |
| `partial` — Parcial | Hay secciones válidas, falta una fuente o evaluación. | Mostrar esas secciones y «El análisis aún está incompleto», con qué falta. No inventar una fortaleza/mejora para completar el diseño. |
| `ready` — Listo | Resultados de la revisión vigente disponibles. | Una fortaleza, una mejora y hasta tres evidencias. Audio solo si el fragmento existe; detalles bajo demanda. |
| `skipped` — Omitido | Buzón/no respuesta o interacción sin conversación elegible. | «No hay conversación suficiente para generar coaching». Sin spinner ni reintento automático condenado a fallar; el memo y sus datos siguen accesibles. |
| `unavailable` — No disponible | Falta un requisito, como playbook aplicable, o las fuentes no permiten evaluar. | Explicar el motivo y la acción posible: configurar proceso con permisos, revisar captura o conservar la cita disponible. No mostrar una tarjeta vacía ni una nota cero. |
| `failed` — Error recuperable | El trabajo agotó el intento o falló una lectura. | «No pudimos preparar el resumen». Reintento idempotente de la revisión vigente; conservar los resultados válidos previos como tales, nunca presentarlos como actuales. |

`pending → partial → ready` es una progresión posible, no obligatoria. Una revisión nueva invalida el resultado anterior para esa vista; las respuestas tardías no lo restauran. `skipped` se mantiene mientras no cambie la elegibilidad. Un fallo de scoring puede dar un brief parcial de objeciones, pero no una conclusión de coaching fabricada.

La preferencia «al terminar / diferido / fin del día» determina cuándo destacar el acceso; no convierte un resultado listo en pendiente ni oculta el motivo de inelegibilidad al consultar el historial. Sin audio se conserva el texto: «Audio no disponible para este momento».

### Criterio de aceptación (Definition of Done)

- [ ] La llamada siguiente puede empezar mientras se procesa el brief.

- [ ] Cambiar la preferencia modifica cuándo se destaca.

- [ ] Un reinicio del trabajador no deja el brief pendiente indefinidamente.

- [ ] No se muestran conclusiones de una revisión antigua.

- [ ] Cada mejora incluye evidencia.

- [ ] El contenido principal es breve y utilizable.

- [ ] Se verifican los seis estados visuales y sus acciones. Buzón/no respuesta termina en `skipped`; nunca queda cargando indefinidamente.

- [ ] Un resultado parcial muestra solo secciones respaldadas; un retry o revisión nueva no presenta como actual una conclusión antigua. Un brief sin audio permite leer la cita sin reproducción ficticia.

### Riesgos / edge cases conocidos

Scoring fallido, grabaciones antiguas sin audio y datos corregidos después. El estado parcial debe ser visible y no bloquear otros resultados.

## Mapa de archivos y responsabilidades

| Acción futura | Ruta | Responsabilidad |
|---|---|
| Crear | `/Users/danizal/getvocify/backend/app/services/coaching/briefs.py` | Agregación y elegibilidad. |
| Modificar producido F09 | `/Users/danizal/getvocify/backend/app/api/coaching.py` | Brief/preferencias. |
| Crear | `/Users/danizal/getvocify/backend/migrations/047_post_interaction_briefs.sql` | JSON y preferencias. |
| Crear | `/Users/danizal/getvocify/backend/tests/coaching/test_briefs.py` | Estados/revisiones. |
| Crear | `/Users/danizal/getvocify/src/features/coaching/hooks/usePostInteractionBrief.ts` | Polling/consulta de revisión. |
| Crear | `/Users/danizal/getvocify/src/components/dashboard/memos/PostInteractionBrief.tsx` | Seis estados visuales. |
| Modificar | `/Users/danizal/getvocify/src/pages/dashboard/MemoDetail.tsx` | Coaching ampliable. |
| Modificar | `/Users/danizal/getvocify/src/pages/dashboard/settings/SettingsLayout.tsx` | Preferencias de destaque. |

Los archivos marcados «Crear» todavía no existen por esta planificación. Los marcados «Modificar» pueden ser producidos por una dependencia; su procedencia debe quedar indicada. Los tests y fixtures se crean en ejecución, nunca se confunden con datos de producción.

## Tareas secuenciales con ciclo TDD

Cada tarea termina con evidencia revisable. Los ejemplos de contrato y prueba fijan entradas/salidas futuras; no se han ejecutado ahora. Dividir los pasos de implementación en cambios pequeños dentro del mismo ciclo rojo → verde → revisión. No iniciar otra feature para esquivar un fallo.

### F11.01 — Derivar elegibilidad y estado sin conclusiones ficticias

**Archivos:** coaching/briefs.py; tests/coaching/test_briefs.py.

**Interfaz y propiedad:** C16 pending/partial/ready/skipped/unavailable/failed. aggregate_brief lee solo resultados de input_revision vigente.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"status":"partial","reason":"score_pending","input_revision":"rev-4","sections":[{"kind":"objections","evidence_refs":["ev-1"]}],"audio_available":false}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Buzón/no respuesta | skipped terminal sin spinner. |
| Score ausente, objeciones listas | partial con secciones reales. |
| Sin playbook | unavailable razón clara; no consejo genérico. |
| Job error | failed, no indefinite pending. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/coaching/test_briefs.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Definir precedencia de elegibilidad y estados C16; conservar secciones verificables aunque falte score.

- [ ] Elegir una fortaleza/una mejora y hastatres evidencias ya producidas; no fabricar texto para llenar layout.

- [ ] Validar revisión de todas las fuentes; no combinar score viejo y patrones nuevos.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/coaching/test_briefs.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Los seis estados tienen causa y transición comprobables.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F11.01`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F11.02 — Persistir y programar preferencia sin retrasar captura

**Archivos:** migration047, coaching API, worker handlers; tests/coaching/test_brief_preferences.py nuevo.

**Interfaz y propiedad:** C16 highlight_mode immediate/deferred/end_of_day. deferred usa delay_minutes (inicial 30); end_of_day hora local (inicial 18:00), ambos configurables. El procesamiento es independiente.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"highlight_mode":"deferred","delay_minutes":30,"timezone":"Europe/Madrid","available_status":"ready"}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Cambiar preferencia con brief ready | No vuelve a pending ni se borra. |
| Worker reinicia | Reclama trabajo y publica solo vigente. |
| Brief antiguo termina tarde | No sobrescribe revisión nueva. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/coaching/test_brief_preferences.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Añadir preferencias validadas y campos de brief sin nueva cola.

- [ ] Encolar agregación al actualizar score/patrones/meeting de misma revisión; dedupe con jobs existentes.

- [ ] Calcular momento de destaque sin lanzar modal ni bloquear siguiente llamada.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/coaching/test_brief_preferences.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Destaque y procesamiento separados; recuperación funciona.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F11.02`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F11.03 — Representar estados y navegar a evidencia real

**Archivos:** PostInteractionBrief.tsx; usePostInteractionBrief; MemoDetail y preferencias.

**Interfaz y propiedad:** C16; cita sin audio sigue legible, botón reproducir solo con fragmento válido.

**Ejemplo concreto de contrato o prueba a incorporar:**

```text
pending -> partial -> ready
inelegible -> skipped
requisito ausente -> unavailable
trabajo fallido -> failed -> retry de revisión vigente
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Parcial -> listo | Misma tarjeta/revisión, sin salto de layout. |
| Sin audio antiguo | Cita y texto Audio no disponible. |
| Fallo/retry | Conserva secciones válidas como parciales, no actuales ficticias. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `npm run build` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Construir tabla de estados A11 en UI, usando coverage/razones del servidor.

- [ ] Integrar acceso desde historial y preferencias; no ventana intrusiva al terminar.

- [ ] Probar reproducción vinculada al offset C01 y actualización stale.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `npm run build` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Reticle verifica cada estado y acceso a fuente; próxima captura puede empezar durante pending.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F11.03`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

## Verificación integrada y criterios de salida adicionales

Finalizar conversación, iniciar otra mientras brief procesa, abrir historial y leer contenido. Cambiar preferencia. Simular fallo score/audio ausente y comprobar parcialidad sin inventar conclusiones.

### Regresiones y comandos al cerrar

- `cd backend && .venv/bin/python -m pytest tests/coaching/test_briefs.py tests/coaching/test_brief_preferences.py -q`
- `npm run build`

Ejecutar los comandos desde `/Users/danizal/getvocify`, salvo el `cd` explícito. Un directorio de pruebas indicado como nuevo solo estará disponible después de sus tareas; que hoy no exista no autoriza a omitirlo al ejecutar. Las pruebas de IA usan datos reales autorizados y anonimizados; los ejemplos sintéticos de este plan sirven solo para contratos y tests deterministas.

### Qué vuelve al coordinador

- [ ] Informe de `F11` con tarea/criterio → resultado → prueba o veredicto → commit, migración aplicada y contrato entregado.

- [ ] Comparación de interfaces producidas con `00-contracts.md`; ninguna divergencia silenciosa de campos, estados, permisos o semántica de `null`.

- [ ] Revisión SOLID y limpieza de listeners/jobs/efectos; los servicios no duplican interpretación que corresponde a extracción.

- [ ] Evidencia de todos los estados de UI especificados. En web, `reticle_act_and_wait` o `reticle_assert` con consecuencia explícita; en desktop/extensión, además el recorrido nativo. `unknown` y `no-fault` no cierran.

- [ ] Bloqueos y edge cases nuevos en `docs/superpowers/deliveries/F11/report.md` y en el commit/PR. No marcar completa mientras haya criterios pendientes; una suspensión debe nombrar las dependencias no afectadas.

## Handoff a la siguiente entrega

F13 reutiliza fortalezas/mejoras/evidencia ya calculadas. No dispara otra ronda LLM para escribir un informe ni usa destaque como fecha de interacción.
