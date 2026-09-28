# Coaching SDR/AE · Implementación v1 (contrato para esta entrega)

> Plan de producto: [`COACHING_SDR_AE_PLAN.md`](./COACHING_SDR_AE_PLAN.md). Plan hermano: [`HEAD_OF_SALES_DASHBOARD_PLAN.md`](./HEAD_OF_SALES_DASHBOARD_PLAN.md).
> Fecha: 2026-09-28. Base: `staging` @ `9d61c3e`.

## 0. Qué entra y qué no

Staging ya tiene casi todo el F0–F1 del plan:
- playbooks versionados por flujo (040);
- evaluación por paso con cita verificada, `memos.extraction.intelligence.playbook_observations` (C04 v4);
- objeciones (044);
- reunión acordada por llamada (`intelligence.meeting.agreed`), además de `memos.rep_outcome`;
- informes diario y semanal (email + campana), con un hueco `snapshot.coaching` vacío hoy.

Esta entrega es el **F2 del plan (pestaña + mensajes con un foco)** montado sobre ese motor, más su enlace con el dashboard del Head of Sales. **Un hecho, un productor**: no se crea un segundo evaluador ni una segunda cuenta de actividad.

| Entra (v1) | Queda fuera (siguiente entrega) |
|---|---|
| Pestaña **Coaching** para reps con 4 vistas: Resumen, Mis llamadas / Mis reuniones, Mi proceso, Ejemplos | ✅ vs 🟡 («bien hecho» vs «flojo» con criterio que falla): el paso hoy tiene un solo criterio y C04 devuelve met/missed. Requiere ampliar el paso (§3.1) y un prompt nuevo con evals |
| Estados por paso mapeados desde el motor actual: `met`→**hecho**, `missed`→**no hecho**, `unknown`→**sin evidencia** (no penaliza), `not_applicable`→**no se llegó** (no penaliza) | ↕️ fuera de orden, minuto exacto (no hay marcas de tiempo), reescritura sugerida, disputas, modo sombra y calibración ≥85 %, cuestionario, plantillas BANT/SPICED/MEDDICC |
| **Foco de la semana**: un paso, elegido con reglas (§4.1–4.2), estable durante toda la semana | «Mis deals» del AE y «Para hoy» (necesita cualificación por deal) |
| **Seguir el proceso te funciona** (conversión con proceso completo vs incompleto, con muestra mínima) | Bandeja «Coaching» propia (v1 usa la campana y el email que ya existen) |
| **Mensaje diario/semanal**: rellena `snapshot.coaching` de los informes propios, detrás de un flag | LLM redactor del mensaje: v1 usa plantilla determinista |
| Head of Sales: foco de cada comercial en **Equipo** | |

## 1. Motor puro · `backend/app/services/coaching/rep_coaching.py`

Sin I/O. Todo con tests en `backend/tests/coaching/test_rep_coaching.py`.

- **Fila por interacción** `interaction_row(memo) -> dict | None`:
  - memo con `id, user_id, sales_motion_key, screening_outcome, audio_duration, rep_outcome, extraction, capture_started_at, created_at`;
  - devuelve `{memo_id, user_id, observed_at, motion, is_conversation, meeting_agreed, duration_s, summary_line, steps:[{step_id,label,state,quote}]}`;
  - `state` ∈ `done | missing | no_evidence | not_reached`, mapeado desde met/missed/unknown/not_applicable;
  - `is_conversation`: false si `screening_outcome` ∈ {voicemail, no_response} o `audio_duration` < 30 s; en otro caso, true;
  - `meeting_agreed`: `intelligence.meeting.agreed is True` **o** `rep_outcome == "meeting_booked"`;
  - `summary_line`: primera frase real de `extraction.summary` (≤160 caracteres);
  - `None` si no hay `playbook_observations`.
- **Tasa por paso** `step_rates(rows, steps)`: por paso, `{step_id, label, done, missing, applicable = done + missing, rate = done / applicable | None}`. `no_evidence` y `not_reached` **no cuentan**.
- **Proceso completo** `process_complete(row)`: `True` si ningún paso está en `missing` y al menos uno está en `done`.
- **Foco** `choose_focus(rows_prev_week, steps, peer_rates=None)`:
  - candidatos: pasos con `applicable ≥ 3` y `missing ≥ 2`;
  - prioridad: menor `rate`; desempate por mayor distancia a la mediana del puesto (si hay) y después por más `applicable`;
  - sin candidato → `None` («vas bien»);
  - se calcula sobre la **semana anterior completa**, así es estable de lunes a domingo sin guardar estado.
- **Progreso del foco** `focus_progress(rows_this_week, step_id, week_start)`: un valor por día L–V, `{date, done, applicable}`, más el total de la semana. `achieved` = total `rate ≥ 0.8` con `applicable ≥ 3`.
- **Conversión** `conversion_split(rows, flow)`:
  - sobre conversaciones: tasa de `meeting_agreed` con proceso completo frente a incompleto;
  - muestra mínima: 30 conversaciones (sdr) u 8 (ae) en la ventana **y** ≥5 en cada grupo;
  - si no llega, `None`.
- **Mediana del puesto** `peer_step_medians(rows_by_user, steps)`: mediana por paso de las tasas individuales. Solo si hay ≥3 personas **y** ≥30 conversaciones en total; si no, `None`.

## 2. API del comercial · `backend/app/api/coaching.py` (prefijo `/api/v1`)

Siempre sobre el usuario que llama: no hay `user_id` en la petición. Vale para cualquier miembro activo. Flujo = el del `sales_role` (sdr → discovery, ae → closing, general → el flujo con más interacciones propias en la ventana).

| Método | Ruta | Devuelve |
|---|---|---|
| GET | `/coaching/me/summary` | `{flow, motion, week_start, steps:[{step_id,label,rate,prev_rate,peer_median}], numbers:{conversations, meetings_agreed, process_complete, interactions}, prev_numbers:{…}, focus:{step_id,label,criterion,example,why:{rate,applicable,missing,peer_median}, progress:[{date,done,applicable}], week_total:{done,applicable,rate}, achieved} \| null, conversion:{complete_rate, incomplete_rate, complete_n, incomplete_n} \| null, playbook_published: bool}` |
| GET | `/coaching/me/interactions?step_id=&state=&meeting=&limit=50` | `{items:[interaction_row…]}` en orden cronológico inverso, últimas 8 semanas; los filtros son opcionales |
| GET | `/coaching/me/process?weeks=8` | `{weeks:[week_start…], steps:[{step_id,label, by_week:[{done,applicable,rate}], rate, peer_median}], objections:[{category, total, resolved, open}]}` |
| GET | `/coaching/examples` | `{steps:[{step_id,label,criterion,example, moments:[{quote}]}], objections:[{category, guidance, best_response}]}` |

- `moments` son citas `done` de compañeros de la misma empresa y flujo en interacciones con `meeting_agreed`: máximo 3 por paso, **sin nombre ni enlace** (un comercial no puede abrir memos ajenos).
- Las objeciones reutilizan `team_insights.objections.objection_counts(include_guidance=True)`.
- Cuando no hay playbook publicado para el flujo: `playbook_published: false` y listas vacías. Nunca se inventan números.

## 3. Head of Sales

- `/team/adherence`: cada `reps[]` gana `coaching_focus: {step_id, label, rate} | null`, calculado con el mismo `choose_focus`. Es un campo aditivo.
- `HosPeopleTable` (Equipo del Head of Sales): nueva columna **Foco**. Muestra «—» si no hay foco.

## 4. Mensajes (diario/semanal) · flag `COACHING_MESSAGES_ENABLED` (False por defecto, en `CLIENT_FLAGS`)

- En los informes **propios** (`scope='self'`), `snapshot.coaching` = texto determinista:
  - **diario**: «Lo mejor: {paso} en {n} de {m}. Hoy: {foco} ({hecho} de {aplicable} ayer).»;
  - **semanal**: «Foco de la semana pasada: {paso} {rate_antes}→{rate_ahora}. Nuevo foco: {paso}.»;
  - sin foco: «Vas bien: ningún paso del proceso se repite como fallo.»
- **Escapado HTML obligatorio** (`html.escape`) antes de insertarlo en el email: `presentation.py` hoy lo mete sin escapar.
- Sin flag, `coaching` sigue siendo `None` (comportamiento actual).

## 5. Frontend

- **Menú del comercial**: la etiqueta `navCoach` pasa a «Coaching» (es/en). La ruta `/dashboard/coach` y el id `coach` **no cambian**: `nav.test.ts` fija los ids.
- `src/lib/rep-coaching.ts` (puro, con `.test.ts`): tipos, formato de estados (✅ hecho, ❌ no hecho, ⚪ no se llegó, ❔ sin evidencia), frases de foco y conversión, copia es/en.
- `src/features/coaching/rep/*`: `CoachingSummary`, `CoachingInteractions`, `CoachingProcess`, `CoachingExamples`. `CoachPage.tsx` solo compone, con pestañas internas Resumen · Mis llamadas (SDR) / Mis reuniones (AE) · Mi proceso · Ejemplos.
- Sin ranking, sin nota /10 como protagonista («pasos hechos: 3 de 5»), sin tono ni emoción.

## 6. Gates

- `cd backend && python -m pytest -q` en verde.
- `node --experimental-strip-types --test src/lib/*.test.ts src/features/**/*.test.ts` y `node --test shared/ui/*.test.js` en verde.
- `npx tsc -p tsconfig.app.json --noEmit` ≤ 39 errores; `npm run build` OK.
- Lista 4: no se toca la rama `member` de `navItemsFor` salvo la **etiqueta** de Coach; `settings-nav` no se toca.

## 7. Estado (2026-09-28)

- ✅ Motor y API del comercial (`/coaching/me/*`, `/coaching/examples`). Solo se evalúan conversaciones; las lecturas paginan.
- ✅ Pestaña **Coaching** del comercial (SDR «Mis llamadas», AE «Mis reuniones») con Resumen, Mi proceso y Ejemplos.
- ✅ Foco de cada comercial en el Equipo del Head of Sales (columna Foco y CSV).
- ✅ Línea de coaching en los informes propios detrás de `COACHING_MESSAGES_ENABLED` (apagado). El informe diario sale a las 18:00 del día que cubre, así que la línea habla de «hoy» y del foco de la semana. El email escapa el texto.
- Para activar los mensajes en una empresa: `INSERT INTO company_feature_flags (company_id, flag, enabled) VALUES ('<company_id>', 'COACHING_MESSAGES_ENABLED', true) ON CONFLICT (company_id, flag) DO UPDATE SET enabled = true;`
- ⏳ Siguiente: ✅ vs 🟡 con criterio que falla (paso ampliado + prompt con evals), fuera de orden, minuto exacto, reescritura sugerida, disputas, modo sombra, cuestionario y plantillas, «Mis deals» del AE.
