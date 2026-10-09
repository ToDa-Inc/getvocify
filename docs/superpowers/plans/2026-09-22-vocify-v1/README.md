# Vocify V1 — Planes por entrega

[Plan maestro](/Users/danizal/getvocify/proposed_plan.md) · [Contratos](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-contracts.md) · [Cierre](./00-cierre.md) · [Integración y gates](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-integration-and-gates.md)

**Estado:** en ejecución en `feat/vocify-v1`. Decisiones cerradas en [00-decisiones.md](./00-decisiones.md). F03 usa el formato mínimo. La firma de Apple queda fuera. El worker de inteligencia sigue apagado.

Cada plan contiene la especificación funcional previa y su descomposición en tareas con archivos, interfaces, casos de prueba, acciones de implementación, comandos, gates y handoff. Leer un plan no autoriza a implementar otras features ni a redefinir contratos.

| Orden | Plan | Objetivo | Tareas |
|---|---|---|---|
| 1 | [F01 — Entregar captura desktop recuperable, transcripción continua y un paquete macOS verificable.](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/01-f01-captura-desktop.md) | C01 CaptureContext, evidencia temporal, memo idempotente; C02 kernel/transcript; artefacto distribuible condicionado a Developer ID. | 5 |
| 2 | [F02 — Entregar follow-up editable en tres superficies sin bloquear extracción ni fingir envío.](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/02-f02-followup.md) | C03 FollowupView y GET/POST /memos/{id}/followup; handoff honesto y protección de edición. | 4 |
| 3 | [F0-F0.1 — Producir evidencia tipada, nullable y versionada y una ejecución recuperable para sus consumidores.](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/03-f0-f0.1-inteligencia-y-jobs.md) | C04 IntelligenceV1/EvidenceRef; C05 memo_jobs y publicación de resultados por revisión. | 4 |
| 4 | [F08 — Publicar playbooks por tipología con revisión humana, versiones estables y onboarding manual.](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/04-f08-playbooks.md) | C06 PlaybookSnapshot, pasos con IDs estables y entradas respaldadas; Settings con estados por tipología. | 3 |
| 5 | [F07 — Hacer accesible el loop CRM existente mediante chat web y pregunta por voz con permisos e idempotencia.](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/05-f07-ask-vocify.md) | C07 AskTurn/Operation; C08 lecturas CRM con cobertura; panel de chat y audio editable. | 4 |
| 6 | [F04 — Producir candidatos con motivo y cobertura, priorizando pain confirmado sin inventar contactos nunca llamados.](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/06-f04-priorizacion.md) | C09 PriorityCandidate y GET /contact-priorities; caché con cobertura y mapeo de responsables. | 3 |
| 7 | [F05 — Entregar Hoy como lista diaria persistente que reconcilia compromisos, enfriamiento y objeciones.](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/07-f05-hoy.md) | C10 Touch/Signal/Card y TodayView; action_signals con versiones; scheduler diario y GET /today. | 4 |
| 8 | [F06 — Convertir señales de Hoy en acciones recuperables y una cola de llamadas usable con teclado.](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/08-f06-acciones-y-cola.md) | C11 resolve/undo con expected_version, undo_deadline y estado revisado; queueReducer y v-today-card. | 3 |
| 9 | [F03 — Antes de llamar, como mucho tres hechos. Sin conversación, o conversación que no dejó nada, una frase.](/Users/danizal/getvocify/.worktrees/vocify-v1/docs/superpowers/plans/2026-09-22-vocify-v1/09-f03-preparacion.md) | C12 PreparationBrief mínimo; screen-contact. | 4 |
| 10 | [F10 — Conservar anotaciones humanas y hechos estructurados de objeción/respuesta con tiempo y procedencia.](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/10-f10-objeciones-y-notas.md) | C13 Annotation/InteractionPattern; endpoints de notas y revisión; hechos consumibles por scoring/brief/equipo. | 3 |
| 11 | [F09 — Evaluar proceso con evidencia, nota secundaria y adherencia matemáticamente explícita.](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/11-f09-scoring.md) | C14 ScoreView, memos.score y GET /memos/{id}/score. | 3 |
| 12 | [F14 — Convertir acuerdo de reunión en propuesta revisable y una escritura CRM idempotente.](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/12-f14-meeting-booked.md) | C15 MeetingProposal y operaciones CRM auditadas; KPI de acuerdo separado de close. | 3 |
| 13 | [F11 — Ofrecer un brief corto posterior con estados honestos y preferencia de cuándo destacarlo.](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/13-f11-brief-posterior.md) | C16 PostInteractionBrief, preferencias y GET /memos/{id}/brief. | 3 |
| 14 | [F12 — Mostrar checklist y ayuda respaldada en el overlay existente sin duplicar captura ni motor de copiloto.](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/14-f12-asistencia-live.md) | C17 SuggestResult/checklist/overlay state; adaptadores unificados y pillReducer. | 4 |
| 15 | [F13 — Persistir un informe personal por periodo y distribuirlo por email/campana con datos consistentes.](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/15-f13-reporting.md) | C18 ReportSnapshot/Delivery/Notification y preferencias; layout diario/semanal. | 3 |
| 16 | [F15 — Agregar actividad/proceso/resultados de equipo con evidencia, atribución explícita y permisos owner/admin.](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/16-f15-equipo.md) | C19 TeamOverview/Objections/Competitors/Outcomes; snapshots de la migración 049; herramientas de lectura para Ask. | 4 |

## Uso eficiente por sesión

1. El coordinador comprueba alcance/bloqueos del maestro y estado de dependencias.

2. Entrega al subagente este plan individual, contratos Cxx consumidos/producidos y evidencia de los productores ya aceptados.

3. El implementador ejecuta tareas en orden, resuelve casos nuevos y reporta pruebas/veredictos/bloqueos.

4. El coordinador verifica handoff y habilita la siguiente entrega; no se desarrolla en paralelo.

5. Cambios de contrato se registran en el catálogo y se propagan a planes afectados antes de tocar código.

## Conservación y revisión

Las migraciones 037–049 y la tabla de pruebas/evaluación original siguen en el maestro. Las 15 specs funcionales y sus criterios se conservan en estos archivos; no son resúmenes que omitan decisiones UX. El detalle de F0/F0.1 se trasladó desde §3.2–3.3. Se añadieron tareas y pruebas de integración sin afirmar que la implementación esté hecha.

Las copias de restricciones globales en cada plan son un extracto controlado para contexto aislado. Al cambiar una restricción, actualizar el maestro y todos los extractos en la misma revisión documental; no generar variantes por feature.
