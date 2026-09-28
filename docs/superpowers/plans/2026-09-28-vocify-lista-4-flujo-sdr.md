# Vocify · Lista 4 — flujo de trabajo y dashboard del SDR (28 sep 2026)

> **Para agentes:** este plan se ejecuta tarea a tarea (subagent-driven-development). Cada tarea: TDD, suite en verde, un commit. Revisión por tarea antes de pasar a la siguiente.

**Objetivo:** que el día del SDR sea una sola línea de trabajo: entra → ve qué toca hoy (tareas, calientes a los que ya toca volver, nuevos) → abre un contacto con su brief → llama → al colgar confirma la propuesta del CRM y el resultado → envía el follow-up si lo prometió → siguiente llamada. Todo lo que no sirve a esa línea sale de su navegación.

**Base:** `origin/staging` @ `9e2b9da`. Se trabaja y se sube directamente en `staging` (pedido por el founder).

**Principios (se heredan de las Listas 2 y 3):** un hecho, un productor; `memos` es la Interaction; determinista donde se pueda; sin paneles nuevos si uno existente lo absorbe; contratos C01–C19 intactos. **Lo que cambia el comportamiento de un flujo existente va detrás de un flag por empresa, apagado por defecto.** Los cambios de navegación los pidió el founder tal cual y no llevan flag.

**Stack y comandos (línea base medida al empezar):**
- backend: `cd backend && /home/user/venv/bin/python -m pytest -q -p no:cacheprovider` → **2216 passed, 32 skipped**;
- frontend: `node --experimental-strip-types --test src/lib/*.test.ts src/features/**/*.test.ts` → **338 pass**;
- tipos: `npx tsc -p tsconfig.app.json --noEmit` → **39 errores** (no se admite ninguno nuevo);
- build: `npm run build`.

**Migraciones:** desde `062`, con su `.down.sql`. Se aplican a mano en Supabase.

---

## Lo que ya existe y se reutiliza (no se rehace)

| Pieza | Dónde |
|---|---|
| Rol comercial `sales_role` (sdr/ae/general) y Head of Sales = owner/admin | Lista 3 T1, D1, D11 |
| **Match por email Vocify ↔ owner del CRM** (puntualización 1): el email de login se compara con el email del owner de HubSpot/Pipedrive y se cachea por miembro | `hubspot/sync.py::_get_hubspot_owner_id_for_user`, `cache_owners_for_members`, `hoy/assigned.py` |
| **Qué campos del CRM se pueden escribir** (puntualización 1): `allowed_deal_fields` / `allowed_contact_fields` por conexión, que configura el Head of Sales en Ajustes → CRM | `crm_config.py`, `memo_approval.py` |
| Tiers de Hoy: `commitment_due`, `callback_no_answer`, `never_contacted`, calor | Lista 3 T5 |
| Brief pre-llamada v2 (2 líneas SDR) y brief en frío | `services/briefs/*`, `GET /briefs`, extensión (`contact-brief-box.js`) |
| Aprobación de memo con `call_outcome` (converted/on_hold/lost), `lost_reason`, `skip_deal` | `models/memo.py::ApproveMemoRequest`, `memo_approval.py` |
| Traspaso SDR→AE al marcar reunión agendada, Descalificar | Lista 3 T3 |
| Follow-up por flujo y envío desde Vocify | Lista 3 T8, `FollowupCard.tsx` |
| Métricas, adherencia, objeciones con cómo resolverlas, debrief | Lista 3 T10–T13 |

## Decisiones (no se vuelven a preguntar)

| # | Decisión |
|---|---|
| E1 | «Dashboard del SDR» = la navegación de quien **no** es Head of Sales (`role = member`). El Head of Sales (owner/admin) conserva Equipo y todos los Ajustes. |
| E2 | Copiloto sale de la navegación de todos. La ruta `/dashboard/copilot` sigue existiendo (sin enlace). |
| E3 | «Preguntar» y «Llamar» salen de la barra lateral y van a la barra superior, a la izquierda (Preguntar, Llamar), para todos los roles. Preguntar sigue con el alcance que ya tiene (lo suyo, más traspasos). |
| E4 | «Notas de voz»/«Conversaciones» pasa a llamarse «Grabaciones» / «Recordings». Para un member la lista es siempre solo suya (`scope=me`), aunque tenga `visibility=team`. |
| E5 | Para un member, «Equipo» no aparece; aparece «Coach» (`/dashboard/coach`) con **solo sus** métricas, adherencia, objeciones (con cómo resolverlas) y feedback de sus llamadas. El detalle del coaching se ampliará en otra lista. |
| E6 | Ajustes de un member: Llamadas, Glosario, Uso. CRM, Oferta, Resúmenes, Proceso, Equipo y Facturación son del Head of Sales. |
| E7 | Hoy del SDR en tres bloques: **Tareas** (compromisos con fecha de hoy o vencidos: rellamadas acordadas, emails prometidos; rellamadas sin respuesta; follow-ups listos para enviar), **Seguimiento** (contactos calientes cuya fecha de seguimiento ya llegó) y **Nuevos** (nunca contactados). Cada bloque tiene su propio tope, para que los nuevos no desaparezcan detrás de los calientes. |
| E8 | **Cadencia de seguimiento:** un contacto caliente no vuelve a Hoy hasta que llega su fecha. La fecha es, por orden: (1) la que el comercial eligió al colgar; (2) un compromiso con fecha («llámame el jueves») → sigue siendo tarea; (3) la última conversación + la espera del **freno** por el que no avanzó a reunión. Esperas por defecto (días): interés alto sin objeción 2 · interés medio sin objeción 5 · price 7 · authority 5 · trust 7 · competitor 14 · status_quo 14 · timing 21 · other 7 · interés bajo 30 · interés nulo nunca. El Head of Sales puede sobrescribirlas (`companies.followup_cadence`). Antes de su fecha, el contacto sale en «Próximos», no en Hoy. |
| E9 | El brief en frío añade la línea **«gancho de empresa»**: si el comercial (o un traspaso que puede leer) ya habló con otra persona de la misma empresa, una línea «En {empresa} ya hablaste con {nombre} el {fecha}: {resumen corto}». Solo con memos que el comercial puede leer. La misma respuesta de `GET /briefs` alimenta el dashboard y la extensión. |
| E10 | **Al colgar**, en el panel del contacto y sin salir de Hoy: (1) propuesta del CRM (campos + nota) editable; (2) resultado obligatorio: Reunión agendada · Seguimiento (con fecha sugerida por E8, editable) · No interesado · Descalificado (con motivo); estado de lead del contacto propuesto según el resultado y editable; (3) Confirmar escribe en el CRM; (4) si en la llamada se prometió un email, aparece la propuesta de follow-up; si no, un enlace «Escribir follow-up igualmente»; (5) Siguiente llamada. |
| E11 | **Lead → deal:** el Head of Sales elige en Ajustes → CRM cuándo Vocify crea el deal en el CRM para un contacto sin deal: `always` (lo de hoy, por defecto), `meeting_booked`, `follow_up_or_meeting`, `never`. Con un deal ya existente siempre se actualiza. Lo aplica el backend en la aprobación (`skip_deal`), no solo la UI. |
| E12 | En Grabaciones, el detalle de una llamada propia deja revisar y enviar el follow-up aunque no se enviara al colgar, y reenviarlo. |

## Flags nuevos (`False` por defecto; se exponen en `/auth/me → company.features`)

`HOY_SDR_SECTIONS_ENABLED` (E7, E8), `AFTER_CALL_FLOW_ENABLED` (E10, E11), `BRIEF_COMPANY_HOOK_ENABLED` (E9).

---

## Tareas

### T1 · Navegación y barra superior (E1–E6)
- `src/lib/nav.ts`: fuera `COPILOT` y `ASK`/`CALL` de los items; member → `[Hoy/Inicio, Grabaciones, Playbook?, Coach, Ajustes]`; manager → `[Hoy/Inicio, Grabaciones, Playbook?, Equipo, Ajustes]`. Tests en `nav.test.ts`.
- `DashboardLayout.tsx`: botones «Preguntar» y «Llamar» en la barra superior, a la izquierda, con el mismo estado que hoy (`askOpen`, `dialerOpen`, punto de llamada en curso). `showDialer` sigue mandando sobre Llamar.
- Textos: `navMemos`/`navConversations` → «Grabaciones»/«Recordings»; título y vacíos de `MemosPage` coherentes; `navCoach`.
- `MemosPage.tsx`: member siempre `scope=me` y sin filtro de autor.
- `settings-nav.ts`: member → calling, glossary, usage. Comprobar que el backend deja a un member leer/editar el glosario y leer su uso; si no, ajustar lo mínimo y testear.
- Ruta `/dashboard/coach` (página mínima que T6 completa).

### T2 · Hoy del SDR: Tareas / Seguimiento / Nuevos con cadencia (E7, E8)
- `hoy/cadence.py` (puro): `stopper_for(touch)` y `followup_due_at(touch, overrides)` con la tabla E8.
- `signals.py`: con cadencia activa, `going_cold` y `objection_open` se sustituyen por un único `followup_due` (tier 2, payload con `stopper`, `days_since`, `interest`, cita de la objeción si la hay), que solo nace cuando `now >= due_at`; si aún no toca, no se genera señal de Hoy (sale en Próximos).
- Fecha elegida por el comercial (T4): `memos.followup_at` manda sobre la cadencia.
- `GET /today`: con el flag y SDR/General, `sections` = `tasks`, `followups`, `new`, cada una con su tope (tareas sin tope práctico ≤ 20, seguimiento 7, nuevos 10). Próximos incluye los seguimientos futuros con su fecha y motivo.
- Migración `062_followup_cadence.sql`: `companies.followup_cadence JSONB NULL`, `memos.followup_at TIMESTAMPTZ NULL`, `memos.rep_outcome TEXT NULL` (CHECK `meeting_booked|follow_up|not_interested|disqualified`).
- Motivos en `reasons.py` y en el catálogo es/en («Le interesó; frenó por precio hace 8 días»).
- UI `RepHome`: tres `HomeSection` con cabeceras «Tareas», «Seguimiento», «Nuevos» cuando el flag está encendido; si no, lo de hoy.
- Tests: tabla de cadencia completa, override por empresa, `followup_at` manda, no aparece antes de su fecha, secciones y topes, flag apagado = comportamiento anterior.

### T3 · Brief con gancho de empresa (E9)
- `briefs/company_hook.py` (puro) + lectura: otros memos legibles de la misma empresa CRM (asociación contacto→empresa del CRM si la capa ya la da; si no, nombre de empresa normalizado del perfil vs. `extraction.companyName`), otro `hubspot_contact_id`, el más reciente.
- Se añade al brief en frío y al brief con historial (como línea extra, respetando `MAX_LINES` + 1 para el gancho).
- Extensión: comprobar que `shared/ui/brief.js`/`contact-brief-box.js` pintan un tipo de línea nuevo; si no, añadirlo.
- Tests: con y sin colega, colega no legible excluido, mismo contacto excluido.

### T4 · Al colgar: propuesta → resultado → follow-up → siguiente (E10, E11)
- Backend: `ApproveMemoRequest` acepta `rep_outcome` y `followup_at`; se mapean a `call_outcome` (meeting_booked→converted, follow_up→on_hold, not_interested/disqualified→lost con motivo). Se guardan en `memos`. `meeting_booked` crea el traspaso si `HANDOFF_ENABLED` (reutiliza `handoffs.create_handoff`). `disqualified`/`not_interested` resuelven las señales pendientes del contacto.
- Migración `063_deal_creation_rule.sql`: `crm_configurations.deal_creation_rule TEXT NOT NULL DEFAULT 'always'` con CHECK. `memo_approval` fuerza `skip_deal` cuando el contacto no tiene deal y la regla no permite crear con ese resultado.
- Estado de lead propuesto por resultado (reutiliza `llm/lead_status` si aplica; mapeo determinista por defecto HubSpot: meeting_booked→`OPEN_DEAL` si hay deal / `CONNECTED`; follow_up→`IN_PROGRESS` o `BAD_TIMING` si el freno es timing; not_interested/disqualified→`UNQUALIFIED`), editable.
- `GET/PATCH` de configuración CRM exponen `deal_creation_rule`; UI en Ajustes → CRM (Head of Sales).
- Frontend: componente `AfterCallReview` en `ContactPanel` (modo review) con los pasos E10. Reutiliza la propuesta de MemoDetail extrayendo el bloque a un componente compartido en vez de duplicarlo. La fecha sugerida de seguimiento sale de un endpoint o de la cadencia devuelta con el memo.
- Tests backend: mapeos, regla de deal por resultado, traspaso al agendar, validaciones (seguimiento sin fecha → se usa la sugerida; descalificado sin motivo → 422). Tests JS de la lógica pura del paso a paso.

### T5 · Grabaciones: follow-up en el detalle (E12) — **ya existía, no se hace**
- El detalle de una llamada propia ya muestra el follow-up y deja enviarlo después (`FollowupCard` en `MemoDetail`); reenviar tras editar ya está permitido (idempotencia por revisión). Solo cambió el nombre (T1).
- `MemoDetail`: el follow-up se ve siempre en llamadas propias, con «Enviar» si no se envió y «Reenviar» si ya se envió (el envío idempotente por revisión del cuerpo admite un reenvío explícito).
- Resultado de la llamada y fecha de seguimiento visibles en la cabecera.
- Tests del endpoint de reenvío.

### T6 · Coach del comercial (E5)
- `GET /api/v1/coach/me`: las mismas cifras de `team_adherence` con `user_id` = el propio comercial (sin exigir permiso de equipo), tendencia propia, objeciones con cómo resolverlas (sin nombres de compañeros) y sus últimos debriefs/feedback.
- Página `CoachPage` reutilizando `AdherenceBreakdown`, `AdherenceTrend`, `ObjectionBreakdown`.
- Tests: un member solo recibe lo suyo; no puede pedir otro `user_id`.

### T7 · Cierre (se ejecuta al final, después de T10)
- Suites, `tsc`, build. SQL de activación `2026-09-28-activacion-lista-4.sql` (migraciones 062–063 + flags). Estado final en este documento.

---

## Ampliación: AE y General (pedido del founder, 28 sep)

Los puntos 2–7 del AE (Grabaciones solo suyas, sin Copiloto, Preguntar y Llamar arriba, Coach en vez de Equipo, Ajustes Llamadas/Glosario/Uso) son los mismos que los del SDR y ya los cubre T1 para todo el que no es Head of Sales. Lo que el AE ve del SDR que tuvo antes el contacto ya existe (Lista 3 T4/D8) y se mantiene en brief, contexto y Ask.

| # | Decisión |
|---|---|
| E13 | Hoy del AE en tres bloques: **Tareas** (emails prometidos, compromisos con fecha, respuestas pendientes, confirmaciones), **Seguimiento** (deals/contactos calientes cuya fecha de seguimiento llegó y no se ha hecho: misma cadencia E8 por freno, sobre sus deals propios y los traspasados) y **Demos de hoy** (reuniones del día, incluidas las que agendó el SDR). La lista de «Deals en curso» deja de salir entera en Hoy: un deal vuelve cuando le toca. |
| E14 | **Brief de demo** (se despliega en cada demo de hoy y en el panel): empresa (sector, tamaño), deal (etapa, importe, fecha de cierre si están en el CRM), **qué habló el SDR** (resumen, dolor confirmado, interés, cita), objeciones abiertas, compromisos pendientes, otras personas/deals de la misma empresa (gancho E9), y los pasos del playbook de cierre que faltan por cubrir. Determinista, sin LLM. |
| E15 | **Al colgar (AE):** mismos pasos que E10 pero el resultado es el **estado del deal**: selector de etapa del pipeline del CRM (prefijado con la propuesta), más resultado: Siguiente paso (con fecha, E8) · Propuesta enviada · Ganado · Perdido (motivo). Estado del contacto editable. Después, propuesta de email de follow-up/propuesta según lo hablado (flujo `closing`, Lista 3 T8). |
| E16 | **General** = SDR + AE en uno: Hoy con Tareas, Seguimiento, Demos de hoy y Nuevos. Al colgar, el resultado depende de la interacción: contacto sin deal y llamada → resultados de SDR (E10, regla lead→deal E11); con deal o reunión → resultados de AE (E15). Un General con AE asignado puede traspasar al agendar; sin AE, la reunión agendada se queda en su propio Hoy. |

### T8 · Hoy del AE y del General (E13, E16)
- `GET /today` con `HOY_SDR_SECTIONS_ENABLED` (se reutiliza el flag: es el Hoy por bloques): AE → `tasks`, `followups`, `demos`; General → `tasks`, `followups`, `demos`, `new`. La cadencia E8 se aplica también al AE, sobre sus memos y los deals traspasados (fecha desde la última interacción del AE o, si no hay, desde el traspaso). `demos` = `meeting_today` (propias y de traspasos).
- Frontend: `RepHome` pinta los bloques según las secciones presentes, en este orden: Demos de hoy · Tareas · Seguimiento · Nuevos.

### T9 · Brief de demo completo (E14) — **no se hace ahora**
- El brief de reunión ya existe (Lista 3 T6: empresa, últimas interacciones con las del SDR, pendientes, pasos de cierre). Faltan etapa/importe del deal y el gancho de empresa; queda como mejora opcional.
- Amplía `services/briefs/meeting.py` y `GET /briefs/meeting` con deal (etapa, importe, cierre), bloque «Lo que habló {SDR}» (resumen, dolor, interés, cita), objeciones abiertas, compromisos, gancho de empresa (reutiliza `company_hook`) y pasos de cierre pendientes. Se ve en la tarjeta de la demo y en el panel. Tests por cada hecho ausente.

### T10 · Al colgar del AE y del General (E15, E16) — **fuera: lo hace Dani en el desktop app**
- El «after demo» del AE va en el desktop app (las demos se graban ahí). En la web, el AE revisa sus demos en Grabaciones (la lista no filtra por origen, así que las grabaciones del desktop salen, solo las suyas).
- Migración `064`: amplía el CHECK de `memos.rep_outcome` con `next_step`, `proposal_sent`, `won`, `lost`.
- `after_call.py`: resultados por rol/interacción; `won`/`lost` → `call_outcome` y etapa de fin; `next_step`/`proposal_sent` → fecha de seguimiento (E8). La etapa elegida se escribe en el deal (respeta los campos permitidos).
- `GET /memos/{id}/after-call` devuelve `mode` (`sdr`|`ae`) y las etapas del pipeline del deal.
- `AfterCallReview` pinta el modo AE (selector de etapa + resultados E15) y el General elige el modo por la regla E16. Follow-up en modo propuesta.

## Gates por tarea
1. Test que falla primero y luego pasa. 2. Suite backend y JS en verde. 3. `tsc` sin errores nuevos. 4. Revisión del diff antes de la siguiente. 5. Un commit por tarea: `feat(lista-4): Tn …`.
