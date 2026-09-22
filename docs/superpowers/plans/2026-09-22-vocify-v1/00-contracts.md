# Vocify V1 — Contratos compartidos y propiedad

[Plan maestro](/Users/danizal/getvocify/proposed_plan.md) · [Índice de entregas](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/README.md)

**Estado:** diseño propuesto para implementación, no interfaces ya desplegadas. Estos contratos concretan los planes separados. Ningún consumidor puede redefinir un campo para resolver su feature en aislamiento.

**Entrada de lectura:** el subagente recibe las secciones Cxx que consume/produce, más las invariantes comunes; no necesita todo el catálogo. Una modificación de contrato se hace primero aquí, después en productor y consumidores afectados, con prueba de compatibilidad. El coordinador registra la revisión y el motivo antes de habilitar el cambio.

## Invariantes de integración

- Servidor deriva usuario/empresa de sesión. Todo objeto externo incluye conexión y tipo de objeto. IDs de fixtures de este documento son ejemplos de test, no formatos de ID reales ni datos para producción.
- Los JSON nuevos usan `snake_case`. Componentes/reducers JS existentes conservan sus nombres y tienen adaptadores explícitos; no renombrar silenciosamente SSE beta o FollowupView de PF.
- Instantes persistidos: ISO 8601 con offset, normalizados a UTC; zona comercial como identificador IANA. Un día local no es un instante: usar periodo `[start, end)` calculado en esa zona. `offset_ms` se mide desde inicio de captura, no desde upload.
- Desconocido es `null` o estado `unknown`, según el campo; no es `false`, cero ni lista vacía válida. `items=[]` solo demuestra ausencia si la cobertura requerida es completa.
- Todo resultado derivado registra `input_revision`; todo snapshot de proceso registra `playbook_version_id`. No usar `updated_at` como sustituto de revisión ni mezclar fuentes de revisiones incompatibles.
- `input_revision` identifica las entradas que realmente consume un resultado. Se calcula en servidor con serialización canónica: esquema, revisión de extracción/notas, identidad resuelta y, para consumidores que lo requieran, versión de playbook. Una lectura de resultado CRM posterior no cambia la revisión de ejecución del scoring.
- Cada endpoint sigue los errores existentes de auth. Para capacidades nuevas: `401` sin sesión; `403` sin permiso de operación; `404` objeto ausente/no visible cuando así lo aplica el helper de acceso; `409` revisión/estado incompatible; `422` entrada inválida. Error de proveedor no se traduce a éxito con datos vacíos.
- Idempotencia tiene clave duradera y resultado persistido; desactivar una feature no elimina sus datos. Un timeout después de una escritura externa se reconcilia antes de repetirla.
- Las firmas de funciones nuevas aquí fijan responsabilidad, no obligan a crear clases por cada tabla. Mantener reglas puras y efectos en adaptadores, sin repositorios/frameworks genéricos que no necesite el flujo.

## Matriz de propietarios

| Contrato | Productor responsable | Consumidores principales |
|---|---|---|
| C01 Captura, identidad y tiempo | F01 | F0, F10, F12, F14 y reproducción |
| C02 Kernel UI y distribución | F01 base; F02 follow-up | Todas las superficies nuevas |
| C03 FollowupView | F02 | Revisión web/extensión/desktop |
| C04 Inteligencia y EvidenceRef | F0/F0.1; F10 enriquece fuentes | F04, F05, F09, F10, F12, F14 |
| C05 Jobs y fencing de revisión | F0/F0.1 | Playbooks, Hoy, score, brief y recuperación |
| C06 PlaybookSnapshot | F08 | F03, F09, F12 |
| C07 Turnos/operaciones Ask | F07 | Panel web, voz y manager chat |
| C08 Lecturas/capacidades CRM | F07 base; F04 lista/caché; F13 outcomes | Priorización, Hoy, reporting, equipo |
| C09 PriorityCandidate | F04 | Home y F05 |
| C10 Touch/Signal/Card/TodayView | F05 | F06, F03, reporting |
| C11 Acción/deshacer/cola | F06 | Web/extensión/desktop |
| C12 PreparationBrief | F03, condicionado | Contacto extensión y secundarios |
| C13 Annotation/Pattern | F10 | F09, F11, F15 |
| C14 ScoreView y métricas | F09 | F11, F13, F15 |
| C15 MeetingProposal | F14 | Revisión, F11, F13, F15 |
| C16 PostInteractionBrief | F11 | Revisión, historial, F13 |
| C17 Asistencia y overlay | F12 | Desktop meeting y adaptación beta |
| C18 ReportSnapshot/Delivery | F13 | Email, campana, página, F15 |
| C19 TeamInsight/OutcomeSnapshot | F15 | Panel, manager chat, reportes equipo |

## C01 — Captura y referencia temporal

`POST /api/v1/captures` recibe `client_capture_id`, `started_at`, `interaction_kind` y metadatos disponibles. Devuelve `capture_id`, `memo_id`, estado de captura y capacidad de recuperación. **`capture_id` identifica el memo reservado en servidor; no se crea una segunda entidad Interaction.** `client_capture_id` permite recuperación local anterior a la respuesta y unicidad por autor; la empresa original queda persistida e inmutable.

El estado de captura `recording/upload_pending/processing/complete/failed` pertenece al contexto de captura; no se añade a ciegas al enum actual de `memos.status`. F01 adapta ese estado a los estados de pipeline existentes y documenta el mapeo en su migración/servicio.

`PUT /captures/{capture_id}/audio` es idempotente por contenido/versión y conserva almacenamiento privado. `POST /captures/{capture_id}/complete` finaliza revisión de entrada una vez. Un reintento idéntico devuelve el mismo resultado; un contenido incompatible no pisa la extracción vigente sin revisión nueva.

```json
{"capture_id":"memo-1","client_capture_id":"cap-local-1","started_at":"2026-09-22T08:00:00Z","interaction_kind":"meeting","sales_motion_key":null,"playbook_version_id":null,"transcript_complete":false,"audio_status":"partial","turns":[{"id":"turn-1","speaker_role":"rep","start_ms":0,"end_ms":1200,"text":"Buenos días","is_final":true}]}
```

`source_type` conserva compatibilidad con orígenes existentes; `interaction_kind` separa llamada/meeting/visita/nota y `sales_motion_key` es tipología como dato. F01 reserva metadatos opcionales; F08/F12 fijan el snapshot del playbook cuando esa capacidad exista. Memos antiguos sin estos datos siguen siendo legibles.

## C02 — Kernel compartido

Origen: `shared/ui/`; tokens en `shared/tokens/tokens.json`. Generadores: `scripts/build-tokens.mjs` y `scripts/sync-shared.mjs`. Copias en extensión/desktop son derivadas y llevan `--check`; nunca fuentes editables. Web importa origen con el alias de PF.

El contrato del elemento sigue PF: `.data = view`, render puro, evento `v-action` para intención. Los hosts hacen red, audio, navegación, permisos y escritura; los componentes no leen tokens de auth ni consultan CRM.

F01 entrega base y `<v-transcript>`; F02 añade `<v-followup>` y compose. F06 añade tarjetas/cola; F03 añade brief solo si se aprueba; F14 añade propuesta; F12 añade ayuda. Cada feature extiende el CSS/tokens existentes, no crea otro sistema de diseño.

Estado de transcript: `revision`, `turns[]` con IDs estables e `interim` nullable. `reconcileTranscript(previous,incoming)` ignora revisiones antiguas y reconcilia provisional confirmado sin duplicarlo. No transforma la transcripción persistida para lograr una animación.

Todo el kernel hereda S §2.3/§7: espacio de carga reservado, altura medida cuando cambia, movimiento reducido solo opacidad, texto ≥4.5:1, foco visible de 2 px, botones ≥36 px y live regions discretas. Idioma de UI por `lang`; contenido generado según conversación.

## C03 — FollowupView preservado

Contrato íntegro de PF tareas4/10: `status=generating|ready|sent|unavailable`, `recipientName`, `to`, `phone`, `subject`, `body`, `channel` cuando procedan. Se mantienen los nombres del contrato existente del plan, aunque no sean snake_case. Endpoints GET/POST `/memos/{id}/followup`.

`sent` significa handoff al cliente; UI «Abierto en tu correo». Lectura manager autorizada no otorga escritura del autor. El elemento conserva ediciones durante polling del mismo memo y las descarta al cambiar identidad. El lease de PF no se migra a C05 por obligación.

## C04 — IntelligenceV1 y evidencia

`MemoExtraction.intelligence` es opcional. Cuando exista: `version`, `input_revision`, `status=ready|partial|unavailable`, `sales_motion_key`, `interest`, `pain_confirmed`, `commitments`, `objections`, `meeting`, `competitor_mentions`, `playbook_observations`, `evidence`.

```json
{"id":"ev-1","source_type":"transcript","source_id":"memo-1","turn_id":"turn-1","quote":"El seguimiento nos ocupa tres horas","start_ms":4000,"end_ms":6500,"speaker_role":"prospect"}
```

Para nota humana: `source_type=human_note`, `source_id=annotation_id`; no atribuirla al prospecto. Tiempos y turno son nullable cuando no existan. Una cita debe existir en la fuente referenciada; evidencia no validada no habilita una afirmación.

`commitments[]`: id, kind, actor, text, due_at nullable, temporal_precision, evidence_refs. `objections[]`: id, category canónica, kind objection/obstacle/unknown, response nullable, resolution resolved/open/unknown, evidence_refs. `meeting`: agreed nullable, starts_at nullable, timezone nullable, precision y evidence_refs. `competitor_mentions[]`: nombre/afirmación/evidencia, no análisis externo.

`playbook_observations[]`: step_id, playbook_version_id, status met/missed/not_applicable/unknown, evidence_refs y origin live/final. Antes de F08 puede estar vacío. F12 añade observación live por turno; evaluación final conserva la distinción y no transforma automáticamente una ausencia provisional en incumplimiento.

La extracción es la dueña del significado. F09 consume evidencia y criterios; F05 calcula señales; F14 normaliza una propuesta temporal. Ninguno arranca su propio agente para volver a interpretar toda la conversación.

Una revisión tiene una única producción lógica de inteligencia. Si el camino de extracción ya persistió C04 válido para esa revisión, el handler recupera ese resultado y programa consumidores; no repite la interpretación. Si todavía falta, el job `intelligence` llama al mismo dominio de extracción para completarla. Normal, reextracción y WhatsApp convergen en esa comprobación. Las correcciones de notas o identidad producen una revisión nueva; un simple retry de transporte no.

## C05 — Jobs, revisión y aislamiento

Campos: id/company_id/memo_id/kind/input_revision/status/attempts/available_at/lease_until/run_id/last_error y fechas. Estados: pending/running/success/failed/superseded. Unicidad `(memo_id,kind,input_revision)`; claim atómico en PostgreSQL y publicación condicionada a run_id/revisión vigentes.

Un fallo tras guardar extracción se recupera con barrido; un lease vencido puede reclamarse, pero el trabajador anterior pierde permiso de publicar. No dar a un consumidor más de una revisión como si fueran contemporáneas. Reintentar errores transitorios con backoff acotado; errores de contenido sin solución terminan con motivo explícito, no spinner perpetuo.

**Ámbitos que no son memos:** el diseño original de `memo_jobs` no sirve literalmente para una importación de playbook ni un trabajo diario de empresa. Se reutilizan las reglas de claim/retry, pero F08 ejecuta estado/lease sobre `playbook_imports` de 040 y F05 sobre su registro de ejecuciones de 043. No crear memos falsos para alimentar la cola ni cambiar unicidad a un ID polimórfico sin necesidad. F13 programa/entrega sobre tablas de 048. Esta separación elimina una contradicción del plan monolítico sin añadir migraciones.

## C06 — PlaybookSnapshot

```json
{"playbook_id":"pb-1","version_id":"pv-2","sales_motion_key":"discovery","steps":[{"step_id":"pain","label":"Confirmar problema","criterion":"El prospecto confirma un problema concreto"}],"entries":[{"entry_id":"price-1","category":"price","guidance":"Preguntar por coste actual","source_ref":"source-paragraph-4"}]}
```

Solo versión publicada es consumible. `get_published_playbook(company_id,sales_motion_key,version_id=None)` retorna snapshot o ausencia explícita. Publicar activa una versión atómicamente; no modifica scores antiguos ni reuniones ya iniciadas. Un borrador/contradicción/importación fallida no cuenta como proceso configurado.

## C07 — Conversación Ask y operación

Rutas `/ask/conversations`, `/ask/conversations/{id}`, `/ask/conversations/{id}/turns`, `/ask/conversations/{id}/turns/{turn_id}`. POST turno incluye client_turn_id y texto; respuesta200 final o202 con turn_id. Estados de turno: pending/running/completed/failed. Selección/confirmación son resultado del turno, no un POST de efecto implícito.

Operation: operation_id, revision, target CRM completo, resumen de acción, status proposed/confirmed/running/succeeded/failed/uncertain/cancelled. Confirmar valida operación/target/revisión dentro de la conversación. Cambiar contacto invalida propuesta anterior. Un resultado uncertain se reconcilia.

Voz produce texto editable; no crea memo comercial. Web hace polling de estado persistido y nunca simula tokens. El loop actual se reutiliza en web y WhatsApp, manteniendo sus transportes aislados.

## C08 — Capacidades CRM y cobertura

Envelope de lectura: `items`, `coverage=complete|partial|forbidden|unavailable`, `observed_at`, `next_cursor`, `reason` nullable. Identidad: connection_id, object_type, external_id; los modelos de consumidor pueden exponer contact_id/deal_id sin perder connection_id.

F07 entrega lectura contextual/contacto/tareas y adaptación de herramientas; F04 añade listado completo de asignados y caché; F14 registra reunión aprobada; F13 añade lectura mínima de outcomes; F15 agrega historia observada. Cada capacidad se incorpora al protocolo pequeño que la necesita, no a una clase gigante obligatoria para todos.

Lecturas de resultados CRM en F13 devuelven estado observado y cobertura del periodo. Si el proveedor no puede demostrar el evento/fecha de cierre de ese periodo, esa métrica es no disponible; F15 empieza a conservar observaciones para periodos siguientes y no inventa retrospectiva.

## C09 — PriorityCandidate

Campos: id estable por ámbito, connection_id/contact_id/deal_id nullable, tier, reason, evidence_refs, next_action, observed_at y coverage. `rank_candidates(candidates,now,recent_days=14)` aplica reglas F04; no clasifica nunca llamado con fuentes incompletas.

F04 consulta `intelligence.meeting.agreed` de F0 para excluir llamada de captación cuando ya hay acuerdo; no necesita `meeting_proposals` ni migración046. F05 no sustituye `rank_cards` de S por este tier: prioridad comercial y orden de señales tienen contratos distintos.

## C10 — Hoy

Conservar estructuras/algoritmos Touch, Signal, Card, signals_for_contact, rank_cards, reconcile, reason y due_label de S; el adaptador traduce C04/C08/C09. Tres señales: commitment_due/going_cold/objection_open; enfriamiento de 10 días; siete tarjetas inicialmente.

Signal persistida: tenant/autor/conexión/contacto/deal/memo, type, dedupe_key, payload, status pending/done/dismissed/snoozed/resolved, version entera, snoozed_until y metadata de acción.043 incluye previous_status, last_action_request_id, last_action_at y undo_deadline para F06; el historial mínimo debe permitir devolver mismo resultado al reintentar la acción dentro del contrato acordado.

TodayView: items, pulse, folded_count, generated_at, coverage por fuente. Un pulso incompleto no se presenta como completo. Manual task conserva remote_id y origen; no se escribe una tarea nueva en CRM por mostrarla en Hoy.

F05 usa objeciones vigentes C04 antes de F10. La proyección de patrones F10 puede enriquecer contexto, pero no retrasa ni duplica el primer feed.

## C11 — Acción y cola

POST `/today/{id}/resolve`: action resolve/dismiss/snooze, request_id, expected_version, until nullable. Respuesta: estado/version actual y undo_deadline. PATCH mismo recurso referencia request_id de la acción a deshacer y expected_version; cinco segundos del reloj servidor, no de la animación.

La idempotencia se define por señal+request_id dentro del ámbito de usuario. Un retry de una acción ya aplicada devuelve su resultado; si una acción posterior la ha sustituido, devuelve conflicto y estado vigente, nunca aplica otra vez la transición antigua. Esta regla evita necesitar una tabla de idempotencia genérica fuera de 043.

`queueReducer` de S conserva modos idle/queue/calling/review/done. Adaptación `call_ended` usa screeningOutcome además de memoId: buzón/no respuesta avanza aunque haya memo. Deshacer solo restaura señal; no revierte una llamada ni retira correo.

## C12 — Preparación, todavía condicionada

Rutas/formatos permanecen propuestos hasta aprobación expresa: GET `/briefs?connection_id=&contact_id=&deal_id=`. Campos: identidad completa, status ready/no_interactions/partial/unavailable, coverage, source_revision, blocks máximo4, crm_url permitido. Cada bloque incluye type/text/source_ref/observed_at.

Primario: extensión en contacto HubSpot sin llamada activa; secundarios: tarjeta/marcador/home desktop. Captura/revisión activa prevalece sobre screen-contact. Respuesta de identidad antigua se descarta. No genera LLM ni dependencia de la cola.

## C13 — Notas y patrones

Annotation: annotation_id, client_capture_id, memo_id al resolverse, author_id servidor, text, offset_ms, turn_id nullable, revision, created_at/updated_at. PUT `/memos/{id}/annotations/{annotation_id}`, GET colección. Antes de tener respuesta de captura se conserva local; no se exige un memo inexistente para escribir offline.

InteractionPattern: pattern_id, memo_id, input_revision, category, kind, response nullable, resolution y evidence_refs. Una proyección vieja no suma otra frecuencia. Reinterpretar nota invalidará revisiones dependientes de esa evidencia; no alterará el offset original ni atribuirá nota a prospecto.

## C14 — Score y denominadores

ScoreView: status pending/ready/partial/unavailable/failed, reason nullable, value0..10 nullable, criteria, strengths/improvements, met_steps/applicable_steps/unknown_steps/not_applicable_steps, adherence/coverage, input_revision, playbook_version_id, model_version y prompt_version.

`applicable_steps = count(met)+count(missed)` conocidos. `adherence = met_steps/applicable_steps`, nullable si denominador0. `coverage = applicable_steps/(applicable_steps+unknown_steps)`, nullable si no hay pasos posibles; not_applicable queda fuera y visible por separado. Un unknown no es missed. Las agregaciones suman estos conteos, no promedian porcentajes sin ponderar.

`compute_adherence(statuses)` produce esos conteos/ratios; no produce value. La nota global proviene de evaluación de criterios contextualizados y validada; la ambigüedad de rúbrica o evidencia insuficiente puede dejarla null aunque haya observaciones útiles. Resultado CRM no suma puntos; un comportamiento de confirmar siguiente paso sí puede ser un criterio si está en el proceso.

## C15 — Reunión acordada, revisión y escritura

MeetingProposal: proposal_id/memo_id/input_revision/evidence_refs, agreement agreed/not_agreed/unknown, starts_at/timezone/precision, decision pending/accepted/corrected/omitted, crm_status not_requested/pending/succeeded/failed/uncertain y remote_id nullable.

El payload de aprobación existente incorpora proposal_id/revision/decisión/correcciones. No se crea otro flujo de consentimiento ni escritura desde overlay. La detección es posterior a la interacción y se muestra en revisión. Aceptar no es invitación de calendario ni venta; registrar actividad no cambia etapa salvo configuración explícita.

## C16 — Brief posterior

Campos status pending/partial/ready/skipped/unavailable/failed, reason, input_revision, sections y evidencia/audio disponibles. Los estados de UI no se confunden con status success del job. No añadir un séptimo estado «diferido»: preferencia de destaque y disponibilidad son ortogonales.

Preferencia propuesta: highlight_mode immediate/deferred/end_of_day, timezone y, cuando sea deferred, delay_minutes positivo con valor inicial 30 configurable en Settings. End_of_day usa hora local configurada del usuario, valor inicial 18:00. Estas precisiones concretan «diferida/fin del día» sin modificar el momento de procesamiento; no habilitan notificaciones push nuevas.

## C17 — Live, SSE y overlay

Mantener `/copilot/suggest` y tipos de evento beta token/result/error/done. Para F12 añadir capture_id, input_revision y request_id; backend resuelve el snapshot y valida permiso/tipología meeting. El resultado añade grounded/source_id/source_label/playbook_version_id; el adaptador construye el objeto del `pillReducer` con isObjection/category/text/grounded.

No mostrar token como consejo validado. Sin capture_id legacy conserva comportamiento beta y no habilita grounding F12. Checklist POST `/copilot/checklist` consume turnos finalizados/revisión y devuelve pasos observados con evidence_refs propios; grounded de una sugerencia no valida el checklist.

Overlay state: capture_id, revision, listening, lastLine, assist_enabled, suggestion nullable, checklist summary. `shell:state -> overlay:state` existente; show/hide existentes. IPC SSE autenticado separado del proxy JSON, dirigido solo al renderer solicitante, cancelable y con allowlist de hosts. El overlay no abre otra captura ni pide sugerencias.

Tiempos de S:4 s mínimo, 10 s máximo, 60 s por categoría. Stop/cambio sesión limpia tokens, timestamps y evidencia. Una versión nueva publicada no cambia la fijada a esa captura.

## C18 — Reportes, entrega y notificaciones

ReportSnapshot: report_id/revision/recipient/scope self|team/type daily|weekly, period_start/end/timezone, generated_at, metrics/series/evidence_refs/coverage. Lectura del informe siempre sirve la instantánea persistida. Una corrección posterior genera revisión identificada y no reescribe silenciosamente el email ya recibido.

ReportDelivery: report_id/revision/channel/status pending/sending/sent/failed/uncertain, attempts, idempotency_key, remote_id. Notification: destinatario/type/text/report_id/read_at. Métricas del informe no dependen de que email se envíe correctamente.

Revalidar ámbito al generar/entregar/leer. Un reporte de equipo no se envía a quien perdió el rol. Cron diario/semanal es configurable y opt-in; no crear automatización de Codex como infraestructura de producto.

## C19 — Equipo y atribución

Filtros comunes: periodo/comercial/tipología y contexto de empresa derivado. overview/objections/competitors/outcomes usan el mismo scope y revisión de lectura. Dashboard, chat y reporte consultan la misma agregación.

OutcomeSnapshot: connection_id/deal_id/state open|won|lost|unknown, amount decimal/currency, owner CRM y user_id si mapeado, attribution resolved|unresolved, crm_event_at nullable, observed_at. No sumar monedas ni duplicar deals por joins con contactos/patrones. Un owner ambiguo cuenta una vez en total, fuera de subtotales individuales.

Win rate solo entre won+lost conocidos, si denominador>0; abiertos y unknown visibles aparte. Menciones de competidores son hechos citados. No convertir relación estadística en causalidad ni atribuir cierre a cada llamada del deal.

## Cambios de contrato y compatibilidad

1. Identificar productor, consumidores y casos afectados en esta matriz.
2. Escribir ejemplo válido, inválido y legacy y fijar el resultado esperado antes de modificar código.
3. Cambiar primero productor de forma aditiva, luego adapter/consumidor; mantener comportamiento antiguo hasta completar pruebas de integración.
4. Actualizar spec de cada consumidor y su handoff. Si cambia semántica de una decisión de producto pendiente, aplicar protocolo B2, no decidir por compatibilidad técnica.
5. Registrar revisión de contrato y resultados. No renumerar migraciones ya aplicadas ni borrar datos para hacer coincidir el nuevo formato.
