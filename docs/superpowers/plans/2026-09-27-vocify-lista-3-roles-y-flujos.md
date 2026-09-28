# Vocify · Lista 3 — roles, flujos SDR/AE y Head of Sales (27 sep 2026)

> **Para agentes:** este plan se ejecuta tarea a tarea (subagent-driven-development). Cada tarea: TDD, suite en verde, un commit. Revisión por tarea antes de pasar a la siguiente.

**Objetivo:** que Vocify funcione con tres tipos de comercial (SDR, AE, General) y un Head of Sales. El SDR agenda y pasa el deal al AE, el AE lo lleva al cierre viendo lo que habló el SDR, y el Head of Sales configura y ve todo.

**Base:** `origin/staging` @ `3959162`. Rama `claude/gallant-rubin-akpmoi`.

**Arquitectura:** se respetan los principios de la Lista 2 (§2): un hecho, un productor; `memos` es la Interaction; determinista donde se pueda; **flag por empresa en todo lo nuevo, apagado por defecto** (`feature_flags.is_enabled`); sin paneles nuevos si uno existente lo absorbe. Contratos C01–C19 del plan v1 intactos. Un contrato que cambia se anota aquí.

**Stack y comandos:**
- backend: `cd backend && /home/user/venv/bin/python -m pytest -q` (línea base: 1686 passed, 32 skipped);
- frontend: `node --experimental-strip-types --test src/lib/*.test.ts src/features/**/*.test.ts` (línea base: 293 pass);
- tipos: `npx tsc -p tsconfig.app.json --noEmit` (línea base: **39 errores**, no se admite ninguno nuevo);
- build: `npm run build`.

**Hallazgo al empezar:** el estado que se recibió da por hechos el rol SDR/AE/Ambos en Equipo, el corte Llamadas/Reuniones en Hoy y otros puntos. En `staging` no existen: `company_members.role` solo admite `owner|admin|member`. El plan parte del código real. Si esa parte existe en una rama local sin subir, al integrar hay que quedarse con una de las dos versiones.

**Migraciones:** numeración `NNN_nombre.sql` con su `.down.sql`, desde `054`. Se aplican a mano en Supabase. Los tests usan dobles en memoria, como hasta ahora.

---

## Decisiones tomadas en este plan (no se vuelven a preguntar)

| # | Decisión |
|---|---|
| D1 | El tipo de comercial es `company_members.sales_role` ∈ `sdr|ae|general`, nullable. `null` se trata como `general`, que es el comportamiento actual. Es independiente de `role` (owner/admin/member): un owner puede ser además AE. |
| D2 | El reparto SDR→AE es `company_members.handoff_ae_user_id`: un AE por SDR, editable por el Head of Sales. Si no hay AE asignado, el traspaso pide elegir uno. |
| D3 | «Qué puede ver cada uno» es `company_members.visibility` ∈ `own|team`, por defecto `own`. `team` da lectura de la actividad del equipo, sin permisos de gestión. |
| D4 | Flujos: se conservan las claves `discovery` y `closing`, que ya tienen datos. En la UI se llaman «Prospección (SDR)» y «Demo y cierre (AE)». `qualification` se oculta del editor si no tiene versión publicada. Cada playbook tiene `goal`: `meeting_booked` para prospección y `proposal_and_close` para cierre. |
| D5 | Playbook por captura: SDR→`discovery`, AE→`closing`. General según `interaction_kind`: una llamada va a `discovery` y una reunión o visita a `closing`. Un `sales_motion_key` explícito en la captura sigue mandando. |
| D6 | El traspaso es una fila en `deal_handoffs`. Se crea cuando el SDR marca «Reunión agendada» (acción nueva en Hoy o en el panel de contacto) o cuando se acepta su propuesta de reunión (F14). Con la fila activa, el contacto sale del Hoy del SDR y entra en el del AE. |
| D7 | Cambiar el owner en el CRM (deal, y contacto si no tiene deal) al AE va detrás de `HANDOFF_CRM_OWNER_ENABLED`. Si el AE no tiene owner mapeado en el CRM, el traspaso se hace en Vocify y el CRM queda con el aviso «owner sin mapear». |
| D8 | El AE lee los memos del SDR de un contacto traspasado a él. Lo mismo vale para briefs y Ask. No ve nada más del SDR. |
| D9 | El follow-up se envía desde Vocify con Resend. `from` es «{Nombre} vía Vocify» y `reply_to` es el email del comercial. Se registra en el CRM como nota o email. Flag `FOLLOWUP_SEND_ENABLED`. Sin Gmail. |
| D10 | La estrategia de ventas es `companies.sales_strategy` (texto). Solo la edita el Head of Sales y entra como contexto en follow-up, briefs y Ask. |
| D11 | El Head of Sales es `role IN (owner, admin)`. No se crea otro rol. |
| D12 | Fuera de este plan: desktop Windows, instalador firmado, overlay en vivo (Dani), MCP de HubSpot (Ask sigue con las herramientas propias de Vocify), win/loss con permisos nuevos de HubSpot, lectura de emails de Pipedrive (su API pide scopes de mail) y la conexión a Gmail. El bot de Recall.ai se hace (T14), pero solo funciona con `RECALL_API_KEY`. |

## Flags nuevos (config.py, `False` por defecto)

`SALES_ROLES_ENABLED`, `HANDOFF_ENABLED`, `HANDOFF_CRM_OWNER_ENABLED`, `HOY_LEAD_TIERS_ENABLED`, `HOY_AE_DEALS_ENABLED`, `FOLLOWUP_SEND_ENABLED`, `FOLLOWUP_BY_FLOW_ENABLED`, `ONBOARDING_WIZARD_ENABLED`, `SCORING_OBJECTION_CREDIT_ENABLED`, `DEBRIEF_V2_ENABLED`, `PLAYBOOK_TAB_ENABLED`, `REPORTING_BY_FLOW_ENABLED`, `BELL_TASKS_ENABLED`, `MANAGER_HOME_ENABLED`, `RECALL_BOT_ENABLED`.

El frontend recibe los flags que necesita en `GET /auth/me` → `company.features: string[]`, solo los encendidos. Se añade en T1 y cada tarea agrega el suyo.

---

## Tareas (se ejecutan en este orden)

### T1 · Tipo de comercial, reparto SDR→AE y visibilidad (datos + API + Equipo)
- Migración `054_sales_roles.sql` (+down). Añade a `company_members` las columnas `sales_role`, `handoff_ae_user_id` (FK a `auth.users`, nullable) y `visibility`, con sus CHECK.
- `services/company.py`:
  - `Membership` lleva `sales_role`, `handoff_ae_user_id` y `visibility`;
  - `update_member_profile(company_id, actor, member_user_id, sales_role?, handoff_ae_user_id?, visibility?)` solo para owner/admin (403 si no). Valida que el AE pertenezca a la empresa y tenga `sales_role` `ae` o `general`, y que un SDR no se apunte a sí mismo.
- API `PATCH /company/members/{id}` acepta los campos nuevos. `GET /company/members` los devuelve. Invitar acepta `sales_role` opcional, guardado en `company_invites.sales_role` (misma migración), que se copia al aceptar la invitación.
- `/auth/me`: `company.salesRole` del usuario y `company.features` (solo flags encendidos). Helper `enabled_features(supabase, company_id, names)`.
- `activity_scope.can_view_company_activity(role, visibility=None)` devuelve `True` también con `visibility == "team"`. Se revisan los consumidores para pasarle la visibilidad donde haya `Membership`.
- UI `TeamPage.tsx` (solo para quien gestiona): por miembro, un select de tipo (SDR/AE/General), en el SDR un select «pasa reuniones a» con la lista de AEs, y un select de visibilidad (Solo lo suyo / Todo el equipo). En la invitación, el tipo. Textos en `i18n.tsx` (es/en).
- Tests: `tests/test_sales_roles.py` cubre validaciones, 403 y la copia desde la invitación. Se amplía `test_activity_scope.py`.
- Flag `SALES_ROLES_ENABLED`: sin él, la API ignora y no devuelve los campos y la UI no los muestra.

### T2 · El playbook sigue al rol (prospección / cierre)
- Migración `055_playbook_goal.sql`: `playbooks.goal TEXT NULL`.
- `captures.playbook_fields_for_capture`: si no llega motion explícito, `motion_for(sales_role, interaction_kind)` (D5, función pura en `services/playbooks/motion.py`) elige el motion. Si ese motion tiene versión publicada, se fija. Si no, se aplica la regla actual (única publicada). Solo con `SALES_ROLES_ENABLED`.
- `GET /playbooks` devuelve `goal`, y para un member solo los motions de su rol (general ve los dos). Owner/admin ven todos.
- `PlaybooksSection.tsx`:
  - etiquetas «Prospección (SDR)» y «Demo y cierre (AE)» y objetivo visible, con defaults según D4;
  - `qualification` solo aparece si ya tiene versión publicada;
  - un solo editor con pestañas por flujo, no tres bloques.
- Tests: `motion_for` con la tabla completa, captura de un SDR con dos playbooks publicados y filtrado por rol en GET.

### T3 · Traspaso SDR→AE (meeting booked)
- Migración `056_deal_handoffs.sql`: `deal_handoffs` con las columnas:
  - `id`, `company_id`, `connection_id`, `contact_id`, `deal_id`;
  - `sdr_user_id`, `ae_user_id`, `source_memo_id`, `meeting_starts_at`;
  - `status` (active|closed|cancelled), `crm_owner_status` (done|skipped|unmapped|failed), `created_at`, `closed_at`.
  - Índice único parcial: un solo activo por `(company_id, connection_id, contact_id)`.
- `services/handoffs.py`, con reglas puras y efectos aparte:
  - `resolve_ae(sdr_membership, requested_ae)` → AE o error `needs_ae`;
  - `create_handoff(...)` es idempotente: repetirla devuelve la fila activa;
  - `close_handoff(contact, reason)` se llama cuando el deal entra en una etapa de fin.
- Efecto CRM tras `HANDOFF_CRM_OWNER_ENABLED`:
  - HubSpot: `hubspot_owner_id` del deal, o del contacto si no hay deal, con el owner mapeado del AE (reutiliza el mapeo usuario→owner que ya usan `hoy/assigned.py`/priority);
  - Pipedrive: `user_id` del deal o de la persona.
  - Los métodos se añaden al adaptador de cada proveedor, en un Protocol pequeño `CRMOwnerWriteProtocol`.
  - Mueve también la etapa a `meeting_booked_stage_id` si está configurada y el deal no está ya ahí.
- API `POST /handoffs` con `{contact_id, connection_id, deal_id?, ae_user_id?, memo_id?, meeting_starts_at?}`, que solo puede llamar un SDR o General (un General sin AE no traspasa: 409 `self_owned`), y `GET /handoffs?role=ae|sdr`.
- Hook: al aceptar una propuesta de reunión F14 (`meetings/accept.py`) de un SDR con `HANDOFF_ENABLED`, se crea el traspaso.
- UI: en las tarjetas de llamada de Hoy y en `ContactPanel`, la acción «Reunión agendada → pasar a {AE}» abre un selector si no hay AE. Otra acción, «Descalificar», marca la señal como resuelta con motivo `disqualified`.
- Tests: idempotencia, `needs_ae`, cierre por etapa de fin y adaptadores con respx.

### T4 · El AE ve lo que habló el SDR
- `activity_scope.memo_readable_by(...)` recibe `handoff_contact_ids`. Un AE lee un memo de otro autor si el contacto del memo está en un traspaso activo o cerrado hacia él y el autor es el SDR de ese traspaso.
- Consumidores:
  - `api/memos.py` (detalle y lista con `scope=handoffs`);
  - `briefs` (v2, cold y el brief de reunión de T6);
  - `crm_copilot/viewer.py` (`Viewer.readable_user_ids` → `readable_memo_ids`/contactos traspasados) y Ask por WhatsApp.
- UI: en el detalle de contacto/memo del AE, la sección «Lo que habló {SDR}» con sus memos, en orden cronológico.
- Tests: el AE lee al SDR del traspaso, no lee a otro SDR ni otro contacto, y el SDR no lee al AE.

### T5 · Hoy del SDR: tipos de lead, calor y «Llamar ahora»
- Con `HOY_LEAD_TIERS_ENABLED` y el comercial SDR o General:
  1. **Callback explícito** (`commitment_due`, sin cambios).
  2. **Rellamada sin respuesta**, señal nueva `callback_no_answer`: el último intento fue `no_answer` o `voicemail` (`telephony/call_screening`, memos con `screening_outcome`), hace ≥ `companies.callback_after_days` días (migración `057_callback_after_days.sql`, por defecto 2) y no hubo conversación después.
  3. **Caliente estancado**: `going_cold` pasa a llamarse `stale_hot` en el motivo («Mostró interés y lleva {n} días sin hablar»), sin cambiar el tipo persistido.
  4. **Nunca contactado**, señal nueva `never_contacted`: contactos asignados (`hoy/assigned.py`) sin llamadas ni memos y con cobertura completa. Con cobertura parcial no se crea: la regla existente de `priority.py` se respeta.
- `hoy/heat.py`: `heat_score(facts)` puro, 0–100. Pesa interés (C04 `interest`), dolor confirmado, objeción abierta, recencia del último contacto y respuesta a email. Se usa como segundo criterio dentro de cada nivel y se expone en la tarjeta (`heat`).
- Tope de 7 tarjetas intacto. El orden de `TIER` se ajusta: callback 0, meeting_today 0, callback_no_answer 1, no_reply 1, stale_hot 2, objection_open 3, never_contacted 4.
- Los contactos con traspaso activo no salen en el Hoy del SDR.
- UI: el botón pasa a llamarse «Llamar ahora» y sale siempre que haya teléfono o contacto:
  - con dialer → marcar;
  - sin dialer → `tel:` o abrir la ficha en el CRM.
- Motivos nuevos en `reasons.py` (es/en).
- Tests: orden completo, `heat_score` y su tabla, el traspaso excluye, la cobertura parcial no crea `never_contacted`, y `callback_no_answer` en los bordes de días.

### T6 · Hoy del AE (deals en curso + pre-meeting brief) y Hoy del General separado
- Con `HOY_AE_DEALS_ENABLED`, `GET /today` devuelve `sections`:
  - AE: `meetings` (lo actual) y `deals` (traspasos activos hacia él + deals propios con memo, fuera de etapas de fin), cada uno con `brief`;
  - SDR: `calls`;
  - General: `calls` + `meetings` + `deals`, separados.
  - `items` sigue igual por compatibilidad.
- `services/briefs/meeting.py`, `prepare_meeting_brief(contact)` determinista:
  - `company` (nombre, sector y tamaño, si están en el CRM);
  - `interactions` (últimas 5 con fecha, autor y una frase, incluidas las del SDR, vía T4);
  - `open_items` (objeciones abiertas, compromisos sin cumplir y pasos del playbook de cierre no cubiertos).
  - Sin LLM. `GET /briefs/meeting?contact_id=&connection_id=`.
- UI: `RepHome`/`TodayItemList` pintan las secciones con cabecera («Llamadas», «Reuniones», «Deals en curso»). El brief de reunión se despliega en la tarjeta.
- Tests: secciones por rol, brief con y sin historial del SDR, deal en etapa de fin excluido.

### T7 · Pre-call brief del SDR en dos líneas
- Con `BRIEF_V2_ENABLED` y un comercial SDR o General en una llamada, `prepare_brief_v2` devuelve `lines` de máximo 2:
  - L1: «{fecha}: {qué se habló}. Pendiente: {pendiente}.»;
  - L2: «Llama porque {porqué}. Gancho: "{cita}".»
  - Solo hechos internos (C04 y tareas CRM). Si falta un hecho, la parte correspondiente se omite, no se inventa.
- El formato de 3 líneas se mantiene para el AE y para cuando falte el rol.
- Tests: composición con cada hecho ausente.

### T8 · Follow-up por flujo, envío desde Vocify y estrategia de ventas
- Migración `058_sales_strategy.sql`: `companies.sales_strategy TEXT`. `PATCH /company` la acepta (owner/admin). UI en `OfferSection.tsx`, un bloque «Estrategia de ventas».
- `followup_logic.build_messages`, con `FOLLOWUP_BY_FLOW_ENABLED`, añade una instrucción por flujo:
  - `discovery`/SDR: información pedida e invitación a la reunión (hora acordada si C04 `meeting` la tiene; si no, proponer hueco);
  - `closing`/AE: propuesta con los puntos acordados y los siguientes pasos.
  - Se añade también la `sales_strategy`.
  - El prompt nuevo va en `prompts/followup_v3.md` y `PROMPT_VERSION` pasa a `followup_v3` solo con el flag.
- Envío con `FOLLOWUP_SEND_ENABLED`: `POST /memos/{id}/followup/send` con `{to, subject, body}`:
  - envía por Resend (`integrations/resend_client.py`) con `reply_to` = email del comercial;
  - registra `action="sent", channel="vocify_email"`;
  - deja una nota en el CRM con el cuerpo (HubSpot note / Pipedrive note);
  - es idempotente por memo y la revisión del cuerpo.
- UI `FollowupCard.tsx`: si el flag está encendido, «Enviar» envía desde Vocify; si no, lo actual (`mailto`).
- Tests: mensajes por flujo, envío idempotente y registro CRM con respx.

### T9 · Onboarding del Head of Sales
- Migración `059_company_onboarding.sql`: `companies.onboarding_completed_at`.
- Con `ONBOARDING_WIZARD_ENABLED`, un owner/admin cuya empresa no tiene `onboarding_completed_at` ve `/dashboard/onboarding`. Pasos, cada uno reutilizando componentes existentes:
  1. Conectar CRM (enlace/estado).
  2. Equipo: invitar con email y tipo (SDR/AE/General).
  3. Reparto SDR→AE.
  4. Playbooks (enlace al editor de T2, con aviso de que el primero se monta con Vocify).
  5. Estrategia de ventas.
  - Cada paso se puede saltar. `POST /company/onboarding/complete`.
- Redirección desde `DashboardHome` cuando falte. Tests del endpoint y del helper de «qué paso toca».

### T10 · Scoring con mérito por objeción y debrief por flujo
- `coaching/score_assembly.py`, con `SCORING_OBJECTION_CREDIT_ENABLED`, añade el criterio sintético `objection_handling` por cada objeción real (`kind=objection`) con evidencia:
  - `met` si `resolution=resolved` y hay `response` con evidencia;
  - `missed` si `open` y el comercial no respondió;
  - `unknown` en el resto.
  - Entra en `compute_adherence`. Sin objeciones no suma ni resta, así que un prospecto fácil no gana puntos.
- `coaching/briefs.py`, con `DEBRIEF_V2_ENABLED`, amplía el cuerpo con:
  - `flow` (sdr/ae según motion);
  - `missed` (pasos `missed` con su `label`);
  - `phrases`: la frase del playbook (`entries.guidance`) para cada paso u objeción fallada, máximo 3;
  - `highlights`: evidencias con `start_ms`, como «min 03:12 · cita», máximo 5;
  - `progress`: la adherencia de las últimas 5 interacciones del mismo flujo del comercial.
  - Para SDR se añade «¿reunión agendada?» (C04 `meeting.agreed`); para AE, «¿siguiente paso/propuesta?».
- La preferencia de timing (`brief_preferences`) ya existe y se respeta. Se añade en la UI de ajustes personales si falta.
- UI: la vista del brief posterior (`MemoDetail`) pinta los campos nuevos.
- Tests: una llamada fácil no puntúa más que una objeción bien trabajada (fixture en `backend/evals/F09` si existe; si no, un test unitario), frases desde el playbook, highlights ordenados y progreso.

### T11 · Objeciones con cómo resolverlas, competidores y pestaña Playbook
- `team_insights/objections.py` amplía cada categoría con `how_to` (la `guidance` del playbook publicado con esa `category`) y `best_example` (la cita de respuesta de un memo del equipo con `resolution=resolved`, la más reciente). Se ve en el panel de equipo y, para el comercial, en su vista de objeciones sin nombres de compañeros.
- Competidores: `competitor_counts` devuelve también `mentions` (nombre, cuántas, las 3 últimas citas con fecha). El panel de equipo añade la lista «Competidores mencionados» separada de las objeciones. Usa el flag `TEAM_COMPETITORS_ENABLED`, que ya existe.
- Pestaña Playbook (`PLAYBOOK_TAB_ENABLED`): `GET /coaching/best?week=` → por flujo, las 3 interacciones con mejor puntuación de la semana. Lleva autor, fecha, nota y sus highlights (citas). Un comercial ve las citas y no puede abrir el memo si no es suyo. Página `/dashboard/playbook` con entrada de navegación.
- Tests: `how_to` por categoría, `mentions` y selección de mejores por flujo y semana.

### T12 · Informes por flujo y campanita con tareas y feedback
- Con `REPORTING_BY_FLOW_ENABLED`, el diario y el semanal personal eligen secciones por `sales_role`:
  - SDR: intentos, conectadas, reuniones agendadas y traspasos;
  - AE: reuniones hechas, deals en curso, propuestas enviadas (follow-ups enviados en `closing`) y deals cerrados;
  - General: las dos cosas.
  - Afecta a `reporting/daily_snapshot.py`, `weekly.py` y `presentation.py`.
- Con `BELL_TASKS_ENABLED`, `GET /notifications` añade:
  - `tasks`: pendientes de hoy de Hoy (commitment_due, callback_no_answer) con su motivo;
  - `feedback`: briefs posteriores `ready` cuyo `highlight_at` ya pasó y no se han visto (tabla de vistos: `060_brief_seen.sql`).
  - Ninguno de los dos cuenta en `unread`, igual que `activity`.
- UI `ReportBell.tsx`: secciones «Tareas», «Resumen» y «Feedback».
- Tests: secciones por rol y campanita con cada bloque.

### T13 · Home del Head of Sales, detalle por comercial y adherencia por flujo
- Con `MANAGER_HOME_ENABLED`, un owner/admin entra en `/dashboard` y ve `TeamInsightsPage` como home, con acceso a su Hoy si también vende.
- `TeamOverview` lleva un enlace por comercial a `/dashboard/insights/rep/:userId` con:
  - tendencia de adherencia por flujo;
  - objeciones propias;
  - últimas interacciones con nota;
  - traspasos (SDR: pasados; AE: recibidos).
  - Reutiliza `team_adherence(user_id=…)` y `adherence_trend`.
- Adherencia por flujo: el filtro de motion pasa a «Flujo SDR / Flujo AE». La tabla de reps muestra dos columnas de adherencia según el `sales_role`.
- Manager chat: `get_team_metrics` de Ask llama a la misma función que el endpoint (`team_adherence`), con los mismos parámetros. Hay un test que compara las dos salidas con los mismos datos.
- El informe semanal de equipo queda como el informe global fijo: con `REPORTING_TEAM_ENABLED` no se puede desactivar por usuario para owner/admin, y se documenta.
- Tests: acceso (403 para member sin `visibility=team`), detalle y paridad de Ask.

### T14 · Bot de reuniones con Recall.ai
- `integrations/recall_client.py`: crear bot (`meeting_url`, `bot_name`) y obtener la transcripción, con `RECALL_API_KEY` y `RECALL_REGION`.
- `POST /meetings/bot` con `{meeting_url, contact_id?, connection_id?}` crea el bot y reserva la captura (`captures.create`, `interaction_kind=meeting`, `source_type=recall_bot`).
- `POST /webhooks/recall` verifica la firma (`RECALL_WEBHOOK_SECRET`). En `bot.done` descarga la transcripción, la convierte a turnos con hablantes y completa la captura por el pipeline normal (`run_post_extraction_hooks`).
- UI: en Grabar, el campo «Enviar bot a una reunión (Zoom/Meet/Teams)» si `RECALL_BOT_ENABLED`.
- Tests: con respx, creación, webhook con firma válida e inválida, y conversión de turnos.

### T15 · Cierre
- Suite backend, tests JS, `tsc` (≤39) y `npm run build`.
- Actualizar este plan con el estado final por punto y la tabla «hecho / a medias / falta» para el founder.
- SQL de activación en staging para los flags nuevos: `docs/superpowers/plans/2026-09-27-activacion-lista-3.sql`.

---

## Estado final (28 sep 2026)

Todo va detrás de flags por empresa, apagados por defecto. Para activarlo en staging: `2026-09-27-activacion-lista-3.sql`, que incluye el orden de las migraciones 054–061. Cada tarea pasó por revisión, y sus bloqueantes se arreglaron en un commit `fix(lista-3): Tn review fixes`.

| Punto pedido | Estado | Dónde |
|---|---|---|
| Head of Sales crea el equipo y asigna SDR/AE/General en el onboarding | Hecho | T1 (Equipo), T9 (asistente `/dashboard/onboarding`) |
| SDR: leads nuevos, fríos y calientes; «Hoy» solo llamadas por hacer | Hecho | T5 |
| Orden: callbacks → rellamadas sin respuesta → calientes estancados → no contactados, con score de calor | Hecho | T5 (`hoy/heat.py`, `callback_no_answer`, `never_contacted` desde la caché de prioridades) |
| Cada item con su porqué y «Llamar ahora» (dialer → CRM → `tel:`) | Hecho | T5 |
| Marcar meeting booked lo quita del SDR y lo pasa al AE, con cambio de owner y etapa en el CRM | Hecho | T3 (el owner va aparte, con `HANDOFF_CRM_OWNER_ENABLED`) |
| Descalificar lo quita de la lista | Hecho | T3 |
| AE: recibe los meetings del SDR y ve lo que habló el SDR | Hecho | T3, T4 (memos, briefs y Ask limitados al traspaso) |
| AE: deals en curso hasta el cierre, cada uno con su pre-meeting brief | Hecho | T6; el traspaso se cierra solo al observar una etapa de fin |
| General: llamadas, reuniones y deals separados | Hecho | T6 |
| Visibilidad: cada uno ve lo suyo; «qué puede ver cada uno» se configura por persona | Hecho | T1 (`visibility` own/team, solo lectura), T13 |
| Qué SDR pasa a qué AE | Hecho | T1 |
| Un playbook por flujo, y cada rol ve solo el suyo | Hecho | T2 |
| Estrategia de ventas como ajuste propio | Hecho | T8 |
| Pre-call brief del SDR en 2 líneas (qué se habló, pendiente, porqué y gancho) | Hecho | T7 (el «pendiente» solo muestra compromisos ya vencidos) |
| Follow-up por flujo (SDR: invitación; AE: propuesta), en el estilo del rep, enviado desde Vocify | Hecho | T8 (el envío va aparte, con `FOLLOWUP_SEND_ENABLED` + Resend) |
| Tareas que nadie crea (rellamar si no contesta en X días) | Hecho | T5 (`companies.callback_after_days`) |
| Campanita: tareas, resumen y feedback | Hecho | T12 |
| Scoring: mérito por objeción real bien rebatida | Hecho | T10 (C04 guarda ahora la cita de respuesta del rep) |
| Debrief por flujo: qué faltó, frases, highlights por minuto y progreso | Hecho | T10 |
| Objeciones: cómo resolverlas y mejor ejemplo | Hecho | T11 |
| Tab Playbook: las mejores llamadas y meetings de la semana por flujo | Hecho | T11 |
| Informes diario y semanal por flujo; informe de equipo fijo para el Head of Sales | Hecho | T12, T13 |
| Dashboard del Head of Sales como home, detalle por comercial y adherencia por flujo | Hecho | T13 |
| Menciones de competidores con citas | Hecho | T11 |
| Manager Chat con las mismas cifras que el panel | Hecho | T13 (test de paridad) |
| Bot para Zoom/Meet/Teams | Hecho, falta configurarlo | T14; necesita `RECALL_API_KEY`, `RECALL_WEBHOOK_SECRET` y registrar el webhook |
| Desktop Windows, instalador firmado, resumen y tareas al acabar en el desktop | Fuera | D12 (Dani) / `INTELLIGENCE_WORKER_PUBLISH` sigue apagado |
| Coaching en vivo en el desktop | Fuera | D12 (Dani) |
| Ask por MCP de HubSpot | Fuera | D12; Ask sigue con las herramientas propias, ya con recorte por rol y traspaso |
| Win/loss insights | Fuera | necesita scopes nuevos de HubSpot |
| Emails de Pipedrive y lectura del hilo | Fuera | la API de Pipedrive pide scopes de mail |

**Verificación:** suite backend, tests JS, `tsc` (39 errores, ninguno nuevo) y `npm run build`. Reticle no está disponible en esta sesión y el backend necesita Supabase real, así que las pantallas quedan por ver en staging con sesión real.

## Correcciones tras la revisión del código (28 sep 2026)

La tabla de arriba marcaba todo como «Hecho». Al seguir cada flujo en el código aparecieron huecos; estos commits los cierran (todos en `staging`, suite backend, tests JS, `tsc` sin errores nuevos y `build` en verde):

| Hueco | Arreglo | Commit |
|---|---|---|
| `visibility=team` (solo lectura, D3) dejaba aprobar y previsualizar memos de otro comercial por HTTP | La ruta aplica la misma regla que `approve_memo_core` | `719bc0f` |
| El AE perdía sus propios callbacks en Hoy; la reunión que agendó el SDR no le salía como «Reunión hoy»; las tarjetas de deal decían «Contacto»; «Lo que habló {SDR}» no se podía abrir desde un deal | El AE conserva `calls`; el traspaso guarda la hora (también al aceptar F14) y genera `meeting_today` para el AE; deals con nombre, hora, llamar/CRM y el historial del SDR | `ac68628` |
| Un traspaso no se podía deshacer ni cerrar; en pipelines propios de HubSpot nunca se cerraba; los errores eran silenciosos (un General nunca podía traspasar); los leads nunca contactados no tenían Descalificar ni Reunión agendada; borrar un miembro dejaba traspasos huérfanos | `POST /handoffs/{id}/close`, Deshacer en el panel, «Deal cerrado»/«Devolver al SDR» en el deal, `hs_is_closed`, selector de AE y mensajes, `POST /today/never-contacted`, liberación al borrar o pasar a SDR | `c7a4625` |
| Subidas, grabaciones de la extensión y HubSpot calling no fijaban playbook: sin nota, debrief ni adherencia | Mismo pin que el marcador | `64ce59f` |
| Un bot de Recall que fallaba dejaba la captura «grabando» para siempre; si la transcripción llegaba tarde se marcaba fallida | `bot.fatal`/`transcript.failed` la marcan fallida; `transcript.done` la completa | `684a7c3` |
| Onboarding apuntaba a un select eliminado; `callback_after_days` sin ajuste; detalle del comercial sin nombre y con ids del CRM; competidores con 1 cita sin fecha; el feedback de la campana no se limpiaba al leerlo | Textos, ajuste en Ajustes → Oferta, nombres, 3 citas con fecha, marcar visto desde la nota | `cc0c263` |

**Segunda revisión (UX, Ask, playbook, coaching):**

| Hueco | Arreglo | Commit |
|---|---|---|
| El playbook solo se podía pegar o subir en PDF y se guardaba como **un único paso** con todo el documento; una vez publicado desaparecía el editor | Editor de pasos y respuestas por tipo de objeción, plantillas por flujo, pegar/PDF/audio convertidos en pasos, validación, guardar/publicar con estados; se ve la versión activa | `5920519` |
| C04 devolvía siempre `playbook_observations: []` y `competitor_mentions: []`, y el scoring ponía `strengths/improvements: []`: adherencia, pasos fallados, frases, checklist, «Qué hiciste bien / Qué mejorar» y competidores con nombre nunca salían | `intelligence_v4` detrás de `PLAYBOOK_OBSERVATIONS_ENABLED`: un estado por paso con cita y competidores con cita; líneas de coaching deterministas desde esas citas; evals `cases_v4.json` + `eval_intelligence.py --v4` | `91b2cd9` |
| Ask: un spinner y nada más; un fallo no se veía; memoria compartida entre pestañas; prompt de «WhatsApp» y «HubSpot» para todos | Pasos en vivo («Buscando contactos · Marc»), pasos plegados bajo la respuesta, error con reintentar, memoria por conversación y «Nueva conversación», prompt neutro | `130f5fc` |
| Nada impedía el relleno de IA en follow-ups y Ask | Guardia determinista: reintento nombrando las frases y, si sigue, se quita la frase | `bbcf61a` |

**Sigue pendiente (no es código de este plan o necesita decisión):**
- Verificar en staging con sesión real (Reticle no está disponible en esta sesión) y aplicar migraciones 054–061 + SQL de activación si no se ha hecho.
- Nombres de eventos de Recall: confirmar en el panel de Recall que el endpoint tiene `bot.done`, `transcript.done`, `bot.fatal` y `transcript.failed`, y el idioma de la transcripción (no se fija idioma al crear el bot).
- El comercial sigue sin vista propia de objeciones con «cómo resolverla» (solo el Head of Sales).
- Pestaña Playbook: enseña nombre y nota de compañeros a todos; choca con «sin ranking» de la Lista 2. Decisión de producto.
- Prompts: `intelligence_v3` se editó sin cambiar de versión ni correr evals; `followup_v3` no tiene casos de eval por flujo. `intelligence_v4` tiene casos pero **no se han corrido** (no había clave de OpenRouter en esta sesión): correr `python -u scripts/eval_intelligence.py --v4` 3 veces antes de encender `PLAYBOOK_OBSERVATIONS_ENABLED`.
- Para que haya coaching de verdad: publicar el playbook de Vocify con pasos reales en el editor nuevo y después encender `PLAYBOOK_OBSERVATIONS_ENABLED`.
- Extensión: cambios desde la 1.0.23 sin publicar. Nada de esto está en `main`.

## Gates por tarea
1. Test que falla primero y luego pasa.
2. Suite backend completa en verde y tests JS en verde.
3. `tsc` sin errores nuevos si toca `src/`.
4. Revisión del diff (spec + calidad) antes de la siguiente tarea. Los hallazgos bloqueantes se arreglan en la misma tarea.
5. Un commit por tarea: `feat(lista-3): Tn …`.

## Verificación en navegador
Reticle no está conectado en esta sesión (no hay herramientas `reticle_*`) y el backend necesita Supabase real. Las pantallas se verifican con `tsc` y `build`, y con la revisión. Queda pendiente verlas en staging con sesión real.
