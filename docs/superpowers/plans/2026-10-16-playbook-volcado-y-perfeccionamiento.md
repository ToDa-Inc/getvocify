# Playbook de ventas: volcado asistido y perfeccionamiento — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que un Head of Sales vuelque su conocimiento en Vocify con ayuda (documentos, voz, llamadas modelo, preguntas de huecos), lo pruebe y lo perfeccione con la práctica real, sin tocar la ayuda en directo ni el coaching.

**Architecture:** Todo lo que el jefe vuelca se guarda en el formato de playbook que la ayuda en directo ya lee (respuestas con ramas, preguntas propias `custom`, ejemplos de pasos). La prueba llama a las funciones de la ayuda en directo (`read_turn`, `stream_objection_suggestion`) pasándoles el borrador como parámetro, sin publicar. El success rate se calcula con lo que ya extrae el post-llamada (`objections[].resolution` y `.response`) más un juez de "¿se usó?". Tablas nuevas solo para sesiones, llamadas modelo, cola y veredictos.

**Tech Stack:** FastAPI + Supabase (pytest, `InMemory` + `Sql` por repositorio), React + TypeScript + Tailwind + TanStack Query, `node --test` para helpers puros, `lucide-react`, kit `src/components/ui`.

**Spec:** `docs/superpowers/specs/2026-10-16-playbook-volcado-y-perfeccionamiento-design.md`

## Global Constraints

- No se modifica: `backend/app/services/copilot/*`, `backend/app/api/copilot.py`, los prompts `copilot_*`, `src/features/desktop/**`, `backend/app/services/coaching/*`. Solo se importan y se llaman.
- No hay casos de prueba con respuestas incorrectas ni con preguntas que el material no contesta. No hay botones ni marcas del comercial.
- Tope por respuesta de objeción: **1.200** caracteres (antes 600), en `structured.py` y `playbook-editor.ts`. Objeciones propias: hasta 200; etiqueta 60; `trigger` 200; `example` 300.
- Porcentajes solo con **al menos 3** casos con veredicto; por debajo, recuento ("2 de 2"). Los "no se sabe" nunca suman como éxito.
- Prueba: **10–12** casos; umbral de guía **80%** (activar por debajo está permitido, con aviso). Rondas del asistente: **10** preguntas. Resumen semanal: **5** momentos.
- Una respuesta entra en la cola con **3 o más** casos en **30 días** en que no se usó, o se usó y no resolvió. Cobertura: últimas **4 semanas**.
- Viabilidad del success rate: acuerdo ≥80% con las etiquetas de Toni y ≤30% de "no se sabe"; el success rate sale detrás de `PLAYBOOK_SUCCESS_RATE_ENABLED` hasta cumplirlo.
- La revisión no muestra quién lo dijo.
- Todo detrás de `PLAYBOOK_ASSISTANT_ENABLED` (por defecto `False`). Sin las tablas activadas, la API contesta 503 `{"detail": {"code": "not_activated"}}` y la UI lo dice con calma.
- Proveedor de modelos: el que ya usan las llamadas por-llamada (DeepSeek en Together). Nunca Gemini en pruebas. Nunca se escribe en HubSpot.
- UI: tokens de `THEME_TOKENS`/`MENU_TOKENS` y componentes de `src/components/ui`; papel para contenido, cristal solo para elementos flotantes; `lucide-react` con `strokeWidth={1.5}`; sin colores de paleta Tailwind ni hex; `npm run lint:ui` debe pasar. Textos en ES y EN.
- Git (CLAUDE.md): cambio grande → commits en la rama `staging` (`git checkout staging && git pull --rebase`), `git add <rutas propias>` (nunca `-A`), push al terminar cada fase. No PRs. No merge a `main` hasta que lo diga el dueño. Las tablas las activa el fundador con el SQL de activación; el agente no ejecuta DDL.
- Comandos: `PY=~/.venvs/vocify-backend/bin/python`; backend `cd backend && $PY -m pytest <ruta> -v`; frontend `node --experimental-strip-types --test src/lib/<archivo>.test.ts`, `npm run lint:ui`, `npm run build`.

## Review Focus

1. Staging con el código pero sin las tablas: la API devuelve 503 `not_activated` y la UI muestra un aviso tranquilo, sin pantalla rota (T2, T7, T8).
2. El borrador cambió mientras el asistente guardaba una respuesta (`stale_draft`): reintenta una vez con la base nueva; si falla, 409 visible sin perder lo que el jefe dictó (T5).
3. Una corrección o rama deja la respuesta por encima de 1.200: `guidance_too_long`, el borrador no se toca y la UI ofrece "crear objeción propia" (T14, T16).
4. Empresa vacía (sin llamadas, sin playbook, sin documentos): los huecos son solo temas típicos, la prueba usa objeciones típicas, las estadísticas muestran recuentos y nada falla (T4, T12, T18).
5. Subida de varios archivos con uno ilegible: los demás se procesan y el fallido se lista por nombre (T9).

## Diseño de pantallas (UI/UX)

Criterio: lo más fácil e intuitivo posible, bonito y funcional, con el lenguaje de Inicio y Coaching.

- **Una cosa a la vez.** Un paso, una pregunta, un botón principal. El resto, silencioso (`Button variant="quiet"`).
- **Voz primero.** El campo de respuesta es el compositor de Inicio (`HomeComposer`/`VoiceComposer`): texto grande, micro visible, clip para adjuntar.
- **Papel, no cristal.** Tarjetas `bg-card` con borde `border-border/70` y `rounded-xl`; títulos `THEME_TOKENS.typography.sectionTitle`/`panelTitle`; metadatos 13px `text-muted-foreground`.
- **Lo que dijo el cliente** va en la burbuja de cita de Coaching (`bg-secondary/70`, cursiva, «comillas»). Lo que se guardó o lo que sugiere Vocify, en la burbuja tintada (`bg-success/10` para confirmación; `bg-beige/10 text-beige`-style `THEME_TOKENS.colors.highlight` para "lo que vería tu comercial").
- **Progreso visible y sin estrés.** Medidor de segmentos como `StepMeter` de Coaching (segmento verde aprobado, ámbar corregido, gris pendiente) y "3 de 10" en `text-xs tabular-nums`.
- **Portada de "Mejorar".** Una tarjeta de papel al principio de Playbook (solo managers con el flag): estado en una línea ("Vocify ya contesta 31 de 40 preguntas de tus clientes") y **un** botón principal con el siguiente paso ("Responder lo que falta · 4"). Debajo, un `Segmented` con las vistas: Lo que falta · Prueba · Mejoras. La vista vive en la URL (`?view=assistant|trial|improve`) para volver atrás y enlazar desde el informe semanal.
- **Movimiento.** Entrada `THEME_TOKENS.motion.fadeIn`; la siguiente pregunta entra deslizando 200 ms con la curva de Inicio (`cubic-bezier(0.16, 1, 0.3, 1)`), respetando `prefers-reduced-motion`.
- **Estados.** Cargando: `Skeleton`/`VocifyLoader`; error con reintento: patrón `CoachError`; vacío: patrón `CoachEmpty`; sin activar: párrafo `THEME_TOKENS.typography.body`. Todo reversible ("Deshacer") y sin diálogos de confirmación salvo `ConfirmAction` en lo destructivo.
- **Teclado y accesibilidad.** Enfocar el campo al aparecer cada pregunta; ⌘/Ctrl+Enter guarda; en la prueba 1–4 eligen botón (`IconAction shortcut`); `aria-live="polite"` en confirmaciones; contraste y foco con los tokens existentes.
- **Móvil.** Una columna a <768 px, botones a todo el ancho en el pie.
- **Verificación visual.** Ruta solo de desarrollo `/__preview/playbook-assistant` con datos de ejemplo (sin login) para capturar cada estado en claro, oscuro y móvil.

## Estructura de archivos

Backend (nuevos): `backend/migrations/081_playbook_assistant.sql` + `.down.sql`, `backend/081_playbook_assistant_APPLY_IN_SUPABASE.sql`; `backend/app/services/playbooks/{assistant_store,gaps,assistant,model_calls,trial,outcomes,review_queue}.py`; `backend/app/api/playbook_assistant.py`; prompts `model_call_extract_v1.md`, `playbook_trial_cases_v1.md`, `suggestion_outcome_v1.md`; `backend/evals/outcomes/{run.py,README.md}`; tests en `backend/tests/playbooks/`.
Backend (modificados): `structured.py`, `structure.py` + `playbook_split_v3.md`, `config.py`, `feature_flags.py`, `router.py`, `reporting/weekly.py` (T20).
Frontend (nuevos): `src/features/playbooks/assistantApi.ts`, `components/{ImproveHub,UnderstoodSummary,GapAssistant,ModelCallImport,ModelCallProposals,TrialRunner,TrialResult,ReviewCase,ImproveQueue,ImproveStats}.tsx`, `hooks/{useAssistant,useTrial,useImprove}.ts`, `src/lib/playbook-assistant.ts` + `.test.ts`, `src/pages/dev/PlaybookAssistantPreview.tsx`.
Frontend (modificados): `PlaybookStart.tsx`, `IntakePanel.tsx`, `useIntake.ts`, `PlaybookList.tsx`, `src/lib/playbook-editor.ts`, `src/lib/product-catalog.ts` (copy ES/EN), `src/App.tsx` (ruta de preview en DEV).

---

## FASE 0: cimientos

### Task 1: Tope de 1.200, flags y documentos

**Files:**
- Modify: `backend/app/services/playbooks/structured.py` (`MAX_GUIDANCE = 1200`), `src/lib/playbook-editor.ts` (`MAX_GUIDANCE = 1200`), `backend/app/config.py`, `backend/app/services/feature_flags.py`
- Modify: `docs/superpowers/specs/2026-10-16-playbook-volcado-y-perfeccionamiento-design.md` (decisión del tope; pregunta abierta 1 resuelta; mensaje a Dani punto 1)
- Test: `backend/tests/playbooks/test_structured_editor.py`, `src/lib/playbook-editor.test.ts`, `backend/tests/playbooks/test_assistant_flags.py`

**Interfaces:**
- Produces: `PLAYBOOK_ASSISTANT_ENABLED`, `PLAYBOOK_SUCCESS_RATE_ENABLED` (`Settings` bool, default `False`); tupla `PLAYBOOK_ASSISTANT_FLAGS` incluida en `CLIENT_FLAGS` (llega al frontend como `user.company.features`).

- [ ] **Step 1: Baseline.** `cd backend && $PY -m pytest tests/playbooks -q` y `node --experimental-strip-types --test src/lib/playbook-editor.test.ts`. Anotar fallos previos (no son nuestros).
- [ ] **Step 2: Tests que fallan.** `test_guidance_accepts_1200_and_rejects_1201` (`normalize_objections` acepta 1200 y lanza `PlaybookDraftError("guidance_too_long")` con 1201); en TS, `validateDraft` devuelve `"guidance_too_long"` solo para 1201; `test_assistant_flags_are_client_flags` (`PLAYBOOK_ASSISTANT_ENABLED` y `PLAYBOOK_SUCCESS_RATE_ENABLED` están en `CLIENT_FLAGS` y valen `False` por defecto). Ejecutar: FAIL.
- [ ] **Step 3: Implementar** los cambios de constantes y flags; actualizar cualquier test existente que asuma 600.
- [ ] **Step 4: Ejecutar** los tres bloques de tests: PASS.
- [ ] **Step 5: Spec.** Marcar la decisión (tope 1.200) en la tabla de decisiones, quitar la pregunta abierta 1 y ajustar el punto 1 del apéndice A ("subimos el tope a 1.200").
- [ ] **Step 6: Commit** en `staging`: `git add` de los archivos de este task; `feat(playbooks): answer cap 1200 and assistant flags`.

### Task 2: Almacenamiento (migración 081 y `AssistantStore`)

**Files:**
- Create: `backend/migrations/081_playbook_assistant.sql`, `backend/migrations/081_playbook_assistant.down.sql`, `backend/081_playbook_assistant_APPLY_IN_SUPABASE.sql`, `backend/app/services/playbooks/assistant_store.py`
- Test: `backend/tests/playbooks/test_assistant_store.py`

**Interfaces:**
- Produces (`assistant_store.py`): `class AssistantUnavailable(Exception)` con `code = "not_activated"`; `class AssistantStore(Protocol)` con `create_session(company_id, user_id, kind, state) -> dict`, `get_session(company_id, session_id) -> dict | None`, `latest_open_session(company_id, kind) -> dict | None`, `save_session(company_id, session_id, *, state, status=None) -> dict`, `add_model_call(company_id, user_id, row) -> dict`, `get_model_call(company_id, id) -> dict | None`, `update_model_call(company_id, id, **fields) -> dict`, `add_moment(company_id, row) -> dict`, `list_moments(company_id, *, status=None) -> list[dict]`, `update_moment(company_id, id, **fields) -> dict`, `upsert_outcome(company_id, row) -> dict` (clave `event_id`), `list_outcomes(company_id, *, since) -> list[dict]`, `judged_event_ids(company_id, event_ids) -> set[str]`; `InMemoryAssistantStore`, `SqlAssistantStore(supabase)`, `set_assistant_store(store | None)`, `get_assistant_store(supabase) -> AssistantStore`.
- Tablas: `playbook_assistant_sessions(id, company_id, user_id, kind in ('gaps','trial'), state jsonb, status in ('open','done'), created_at, updated_at)`; `playbook_model_calls(id, company_id, user_id, sales_motion_key, name, transcript, scope jsonb, note, proposals jsonb, status in ('proposed','applied','dismissed'), created_at)`; `playbook_review_moments(id, company_id, source in ('trial','real'), sales_motion_key, entry_id, objection_type, client_text, suggestion_text, rep_text, outcome jsonb, status in ('open','kept','corrected','dismissed'), created_at, resolved_at)`; `playbook_suggestion_outcomes(id, event_id unique, company_id, capture_id, sales_motion_key, entry_id, source_id, objection_type, used in ('used','adapted','not_used','unknown'), resolved in ('resolved','not_resolved','unknown'), resolved_by in ('extraction','judge','admin'), judged_at)`. RLS activada y permisos de `anon`/`authenticated` revocados, como `078_live_assist_events.sql`; cabecera con "Rollback: 081_playbook_assistant.down.sql".

- [ ] **Step 1: Tests que fallan.** Contrato común (parametrizado sobre `InMemoryAssistantStore`): crear y recuperar sesión, `latest_open_session` ignora las `done`, `upsert_outcome` es idempotente por `event_id`, `list_moments(status="open")` filtra, y todo está aislado por `company_id`. Test del `Sql`: con un cliente falso que lanza al hacer `.table(...).execute()`, la operación lanza `AssistantUnavailable`.
- [ ] **Step 2: Ejecutar:** FAIL.
- [ ] **Step 3: Implementar** el módulo (el `Sql` usa `supabase.table(...)`; cualquier excepción de tabla inexistente se traduce a `AssistantUnavailable`).
- [ ] **Step 4: Escribir los SQL** (migración, down y `APPLY_IN_SUPABASE`, idempotentes con `IF NOT EXISTS`). Los números 081 deben acordarse con Dani (hay dos `080_*`): dejar nota en la cabecera.
- [ ] **Step 5: Ejecutar:** PASS.
- [ ] **Step 6: Commit** `feat(playbooks): assistant storage and migration 081`.

---

## FASE 1: volcar con ayuda

### Task 3: Extraer preguntas técnicas y ramas al estructurar

**Files:**
- Modify: `backend/app/services/playbooks/structure.py` (`_shape_split`, `_split_messages`), prompt nuevo `backend/app/prompts/playbook_split_v3.md` (copia de `playbook_split_v2.md` con instrucciones nuevas)
- Test: `backend/tests/playbooks/test_structure.py` (añadir casos con `FakeLLM`)

**Interfaces:**
- Consumes: `split_source(text, candidates, lang, *, llm=None, by_titles=True) -> dict` y `FakeLLM` de `tests/playbooks/test_structure.py`.
- Produces: cada tipo de la respuesta de `split_source` puede traer `objections` con entradas `{"category": "custom", "label", "trigger", "guidance"}` nacidas de `questions` del modelo (`{label, trigger, answer, quote}`), y respuestas de objeción con ramas `"… Si X: …. Si Y: …."` dentro de `guidance` (≤1.200).

- [ ] **Step 1: Tests que fallan.** (a) Una `question` cuyo `quote` aparece literal en el documento se convierte en entrada `custom` con `label` ≤60, `trigger` ≤200 y `guidance` ≤1.200. (b) Una `question` cuyo `quote` NO aparece en el documento se descarta. (c) Más de 200 preguntas: se conservan 200. (d) Un documento sin preguntas deja `objections` como antes (regresión).
- [ ] **Step 2: Ejecutar:** FAIL.
- [ ] **Step 3: Implementar** `playbook_split_v3.md` (pide `questions` y ramas dentro de la misma respuesta, nunca inventar) y el uso de `_literal_in(quote, folded_source)` en `_shape_split`; seleccionar v3 en `_split_prompt()`.
- [ ] **Step 4: Ejecutar** `tests/playbooks/test_structure.py tests/playbooks/test_company_intake.py`: PASS.
- [ ] **Step 5: Commit** `feat(playbooks): intake extracts product questions and branches`.

### Task 4: Detector de huecos y lector de eventos

**Files:**
- Create: `backend/app/services/playbooks/gaps.py`
- Test: `backend/tests/playbooks/test_gaps.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class Gap(key: str, kind: str, question: str, request: str, seen: int, example: str | None, motion_key: str | None)` con `kind in {"topic","real","conflict"}`; `TOPICS: tuple[tuple[str, tuple[str, ...], dict[str, str]], ...]` (clave, palabras que cuentan como cubierto, pregunta ES/EN) con los temas: precio y planes, integraciones, seguridad y datos, plazos de implantación, soporte, límites, contrato y renovación, quién decide, comparación con competidores; `build_gaps(*, entries: list[dict], knowledge: dict, events: list[dict], lang: str, limit: int = 10) -> list[Gap]`; `recent_suggest_events(supabase, company_id, *, days: int = 28, limit: int = 500) -> list[dict]` (lee `live_assist_events` kind `suggest`; devuelve `[]` si falla).
- Regla de orden: reales por `seen` descendente, luego conflictos, luego temas. Un tema está cubierto si alguna entrada `custom` (label, trigger o guidance) contiene alguna de sus palabras. Un hueco real es un evento con `is_objection` verdadero y sin `source_id`, agrupado por `latest_turn` normalizado (minúsculas, 80 primeros caracteres).

- [ ] **Step 1: Tests que fallan.** Empresa vacía → solo temas, 10 como máximo, orden estable. Una entrada `custom` "¿Se integra con Salesforce?" cubre "integraciones". Tres eventos iguales sin `source_id` → un hueco real con `seen == 3` por delante de cualquier tema. Eventos con `source_id` no generan hueco. Dos valores con cifras distintas para el mismo campo (`pricing`) generan un `conflict`. `recent_suggest_events` con cliente que lanza → `[]`. Cada `Gap.question` sale en ES o EN según `lang`.
- [ ] **Step 2: Ejecutar:** FAIL.
- [ ] **Step 3: Implementar** `gaps.py` (puro salvo `recent_suggest_events`).
- [ ] **Step 4: Ejecutar:** PASS.
- [ ] **Step 5: Commit** `feat(playbooks): gap detector`.

### Task 5: Servicio del asistente de huecos

**Files:**
- Create: `backend/app/services/playbooks/assistant.py`
- Test: `backend/tests/playbooks/test_assistant.py`

**Interfaces:**
- Consumes: `build_gaps`, `AssistantStore`, `PlaybookRepository` (`editor_snapshot`, `save_draft`), `fill_playbook(motion_key, request, current, company_text, scope=None)`, `read_source(StructureRequest)`, `editor_view`, `StaleDraftError`.
- Produces: `class AssistantError(Exception)` (`code`: `session_not_found | gap_not_found | nothing_to_undo`); `async start_gaps_session(store, repository, supabase, membership, *, motion_key: str, lang: str) -> dict` (reutiliza la sesión abierta si existe; estado `{"gaps": [...], "answered": {}, "skipped": [], "motion_key": str}`); `public_session(session) -> dict` (`{id, status, total, answered, skipped, current}`); `async answer_gap(store, repository, supabase, membership, *, session_id, gap_key, source) -> dict` (`{saved_line, session, editor}`); `skip_gap(store, membership, *, session_id, gap_key) -> dict`; `undo_gap(store, repository, membership, *, session_id, gap_key) -> dict`.
- Comportamiento: `answer_gap` lee la fuente (texto, PDF o audio), construye la petición para `fill_playbook` a partir de `gap.request` y la respuesta, aplica al contenido del borrador del `motion_key` del hueco (o de la sesión), guarda con `save_draft`, guarda en la sesión el contenido previo para `undo_gap`, y devuelve en `saved_line` la etiqueta de la entrada guardada. Ante `StaleDraftError` reintenta **una vez** con la base nueva. La sesión pasa a `done` al agotarse los huecos.

- [ ] **Step 1: Tests que fallan.** Con `InMemoryPlaybookRepository`, `InMemoryAssistantStore` y `FakeLLM`: (a) responder un hueco añade una entrada `custom` al borrador y marca el hueco como respondido; (b) `undo_gap` restaura el borrador anterior; (c) saltar no cambia el borrador; (d) audio sin voz (`read_source` lanza 422 `audio_has_no_speech`) deja la sesión intacta; (e) `StaleDraftError` una vez → reintenta y guarda; dos veces → propaga y la respuesta del jefe sigue en la sesión (`pending_text`); (f) responder el último hueco deja `status == "done"`; (g) una segunda llamada a `start_gaps_session` devuelve la misma sesión abierta.
- [ ] **Step 2: Ejecutar:** FAIL.
- [ ] **Step 3: Implementar** el módulo.
- [ ] **Step 4: Ejecutar:** PASS.
- [ ] **Step 5: Commit** `feat(playbooks): gap assistant service`.

### Task 6: Llamadas modelo

**Files:**
- Create: `backend/app/services/playbooks/model_calls.py`, `backend/app/prompts/model_call_extract_v1.md`
- Test: `backend/tests/playbooks/test_model_calls.py`

**Interfaces:**
- Consumes: `FakeLLM`, `_ask`/`_client` de `structure.py`, `MAX_EXAMPLE`, `MAX_GUIDANCE`.
- Produces: `MAX_TRANSCRIPT_CHARS = 60_000`; `speaker_warning(transcript: str) -> bool` (verdadero si hay una sola etiqueta de hablante o ninguna reconocible); `async propose(transcript, scope, note, current, lang, *, llm=None) -> dict` → `{"proposals": [Proposal], "speaker_warning": bool}` con `Proposal = {"id", "kind": "step_example" | "objection_branch", "step_index"?: int, "category"?: str, "label"?: str, "when"?: str, "text": str, "excerpt": [{"speaker": "rep"|"client"|"unknown", "text": str}]}`; `scope = {"kind": "whole"} | {"kind": "moment", "text": str}`; `apply_proposals(current: dict, proposals: list[dict]) -> dict` → `{"steps", "objections", "qualification", "applied": [ids], "skipped": [{"id", "code"}]}`.
- Reglas: cada `excerpt` debe aparecer literal en la transcripción o se descarta la propuesta; `step_example` se recorta a `MAX_EXAMPLE`; `objection_branch` añade `" Si {when}: {text}"` a la respuesta y, si pasa de `MAX_GUIDANCE`, esa propuesta queda en `skipped` con `guidance_too_long`; la categoría debe existir en el borrador o se crea como `custom` con `label`.

- [ ] **Step 1: Tests que fallan.** (a) propuesta con extracto literal se acepta; (b) extracto inventado se descarta; (c) `step_example` de 400 caracteres se recorta a 300; (d) rama que desborda 1.200 → `skipped` con `guidance_too_long` y la respuesta intacta; (e) transcripción de un solo hablante → `speaker_warning True`; (f) `scope.kind == "moment"` pasa el fragmento al prompt; (g) transcripción de más de 60.000 caracteres se rechaza con `ValueError("transcript_too_long")`.
- [ ] **Step 2: Ejecutar:** FAIL.
- [ ] **Step 3: Implementar** el servicio y el prompt (JSON con `step_examples` y `objection_branches`, cada uno con `excerpt`).
- [ ] **Step 4: Ejecutar:** PASS.
- [ ] **Step 5: Commit** `feat(playbooks): model call proposals`.

### Task 7: API del asistente y las llamadas modelo

**Files:**
- Create: `backend/app/api/playbook_assistant.py`
- Modify: `backend/app/api/router.py` (incluir el router)
- Test: `backend/tests/playbooks/test_assistant_api.py`

**Interfaces:**
- Produces (prefijo `/api/v1/playbook-assistant`, solo owner/admin vía `require_manager`; 404 si `PLAYBOOK_ASSISTANT_ENABLED` está apagado para la empresa; 503 `not_activated` si el almacén no existe): `POST /gaps/session` `{motion_key?, lang?}`; `GET /gaps/session/current`; `POST /gaps/session/{id}/answer` `{gap_key, kind, payload, name?}`; `POST /gaps/session/{id}/skip` `{gap_key}`; `POST /gaps/session/{id}/undo` `{gap_key}`; `POST /model-calls` `{motion_key, name?, transcript? | memo_id?, scope, note?}`; `POST /model-calls/{id}/apply` `{proposal_ids}` (devuelve el editor del borrador); `POST /model-calls/{id}/dismiss`. Para `memo_id` solo se admiten llamadas de la propia empresa.
- Errores: `AssistantError` → 404/409/422 con `detail.code`; `FillError` → 422 `fill_failed`; `AssistantUnavailable` → 503 `not_activated`.

- [ ] **Step 1: Tests que fallan** (con el helper `_client` de `test_company_intake.py` y `InMemoryAssistantStore`): flag apagado → 404; rol `member` → 403; sesión nueva devuelve `total <= 10` y `current`; responder devuelve `saved_line` y `editor`; llamada modelo por `memo_id` de otra empresa → 404; `apply` de una propuesta válida deja el ejemplo en el paso; almacén no activado → 503 `not_activated`.
- [ ] **Step 2: Ejecutar:** FAIL.
- [ ] **Step 3: Implementar** el router y registrarlo.
- [ ] **Step 4: Ejecutar** `tests/playbooks/test_assistant_api.py` y `tests/test_api_names_defined.py`: PASS.
- [ ] **Step 5: Commit** `feat(playbooks): assistant API`.

### Task 8: Base del frontend (cliente, helpers, copy, portada y vistas)

**Files:**
- Create: `src/features/playbooks/assistantApi.ts`, `src/lib/playbook-assistant.ts`, `src/lib/playbook-assistant.test.ts`, `src/features/playbooks/components/ImproveHub.tsx`, `src/pages/dev/PlaybookAssistantPreview.tsx`
- Modify: `src/lib/product-catalog.ts` (bloque `pb2.improve` ES y EN), `src/features/playbooks/components/PlaybookList.tsx` (portada y vistas), `src/App.tsx` (ruta `/__preview/playbook-assistant` solo con `import.meta.env.DEV`)
- Test: `src/lib/playbook-assistant.test.ts`

**Interfaces:**
- Produces (`playbook-assistant.ts`, puro): `type ImproveView = "assistant" | "trial" | "improve"`; `viewFromParams(params: URLSearchParams): ImproveView | null`; `rateLabel(good: number, total: number, min?: number): { kind: "rate"; text: string } | { kind: "count"; text: string }` (porcentaje solo con `total >= 3`); `intakeSummary(results: IntakeResultLike[]): { types: number; objections: number; questions: number; steps: number; proofs: number }`; `savedLine(label: string, answer: string): string` (recorta a 90 caracteres); `trialMeter(verdicts: string[], total: number): ("approved" | "corrected" | "unknown" | "pending")[]`.
- Produces (`assistantApi.ts`): `assistantApi` con un método por endpoint de T7, T15 y T18 y el tipo `ApiNotActivated` detectable con `isNotActivated(error)`.
- `ImproveHub`: tarjeta de papel con la línea de estado (una frase), un `Button` principal con el siguiente paso, `Segmented` de tres vistas que escribe `?view=`, y un aviso tranquilo si `isNotActivated`. Solo se muestra a owner/admin con `PLAYBOOK_ASSISTANT_ENABLED` en `user.company.features`.

- [ ] **Step 1: Tests que fallan** (`node --test`): `rateLabel(2, 2)` → `count` "2 de 2"; `rateLabel(3, 4)` → `rate` "75%"; `rateLabel(0, 0)` → `count` "0 de 0"; `viewFromParams("view=trial")` → `"trial"`, `view=xyz` → `null`; `intakeSummary` suma tipos sin duplicar claves; `savedLine` recorta a 90 con "…"; `trialMeter(["approved","corrected"], 4)` → 2 llenos y 2 `pending`.
- [ ] **Step 2: Ejecutar:** FAIL.
- [ ] **Step 3: Implementar** helpers, cliente, copy ES/EN (frases cortas y cálidas; "vuestro"), `ImproveHub` y su montaje en `PlaybookList` (la vista activa sustituye al detalle; "Volver" con `Button variant="outline"` como en Coaching).
- [ ] **Step 4: Ejecutar** tests, `npm run lint:ui` y `npm run build`: PASS.
- [ ] **Step 5: Commit** `feat(playbooks): improve hub and assistant client`.

### Task 9: Entrada con varios archivos y "lo que he entendido"

**Files:**
- Modify: `src/features/playbooks/components/PlaybookStart.tsx`, `src/features/playbooks/components/IntakePanel.tsx`, `src/features/playbooks/hooks/useIntake.ts`
- Create: `src/features/playbooks/components/UnderstoodSummary.tsx`
- Test: `src/lib/playbook-assistant.test.ts` (partes puras)

**Interfaces:**
- `PlaybookStart` gana `multiple?: boolean` y `submitMany?: (sources: SourceInput[]) => Promise<void>`; con `multiple` muestra los archivos como chips con su quitar (como adjuntos de Inicio) y acepta arrastrar varios. Sin `multiple` se comporta como hoy.
- `useIntake` gana `submitMany(inputs: SourceInput[]): Promise<{ failed: { name: string; code: string | null }[] }>`: llama a `playbooksApi.intake` en serie, **continúa tras un fallo** y devuelve los fallidos; acumula el resumen con `intakeSummary`.
- `UnderstoodSummary`: tarjeta con 4 cifras ("3 tipos de llamada · 5 objeciones · 14 preguntas del producto · 2 casos"), lista de archivos fallidos por nombre y dos botones: principal "Responder lo que falta (≈10 min)" y quieto "Más tarde".

- [ ] **Step 1: Test que falla** (puro): `intakeSummary` con dos resultados cuenta preguntas `custom` en `questions` y no duplica tipos; con un resultado `fallback` no suma nada.
- [ ] **Step 2: Ejecutar:** FAIL → implementar → PASS.
- [ ] **Step 3: UI.** Chips de archivo, estado "leyendo 2 de 3" con `VocifySpinner`, resumen al terminar, errores por archivo con `copy.readErrors[code]`.
- [ ] **Step 4: Verificar** `npm run lint:ui`, `npm run build`.
- [ ] **Step 5: Commit** `feat(playbooks): multi-file intake and understood summary`.

### Task 10: Pantalla "Lo que falta" (asistente)

**Files:**
- Create: `src/features/playbooks/components/GapAssistant.tsx`, `src/features/playbooks/hooks/useAssistant.ts`
- Modify: `src/pages/dev/PlaybookAssistantPreview.tsx` (estados de ejemplo)

**Interfaces:**
- `useAssistant(motionKey)`: `{ session, answer(source), skip(), undo(), status: "loading" | "ready" | "saving" | "done" | "error" | "not_activated" }` sobre `assistantApi`; invalida la query del editor del tipo tras guardar.
- `GapAssistant` (vista pura `GapAssistantView` con props; contenedor con el hook): columna centrada `max-w-2xl`; cabecera "Lo que falta" con `text-xs tabular-nums` "3 de 10" y el medidor de segmentos; tarjeta de pregunta con la frase real del cliente en burbuja de cita y, si procede, "Sale en 3 de las últimas 40 llamadas"; campo de respuesta con micro y adjuntar (`VoiceComposer`, `playbooksApi.transcribe`); `Button` principal "Guardar" (⌘/Ctrl+Enter), `variant="quiet"` "Lo respondo luego"; tras guardar, burbuja verde con `savedLine` y "Deshacer" y la siguiente pregunta entra deslizando; estado final con resumen y botón principal "Probar cómo responde Vocify" que cambia a `?view=trial`. Foco automático en el campo; `aria-live="polite"` en la confirmación.

- [ ] **Step 1: Preview.** Añadir los estados `loading`, `question`, `question-real`, `saving`, `saved`, `done`, `error`, `not_activated` a la ruta de preview.
- [ ] **Step 2: Implementar** vista y contenedor.
- [ ] **Step 3: Verificar visualmente** (ver T11 Step 4: capturas de cada estado en claro, oscuro y móvil) y `npm run lint:ui`, `npm run build`.
- [ ] **Step 4: Commit** `feat(playbooks): gap assistant screen`.

### Task 11: Importar una llamada modelo y revisar propuestas

**Files:**
- Create: `src/features/playbooks/components/ModelCallImport.tsx`, `src/features/playbooks/components/ModelCallProposals.tsx`
- Modify: `src/features/playbooks/hooks/useAssistant.ts` (acciones de llamada modelo), preview

**Interfaces:**
- `ModelCallImport`: `Sheet` lateral (cristal solo por ser flotante) abierto desde un enlace quieto "Subir una llamada modelo" en la caja de entrada y en la portada; pestañas `Segmented` "Pegar o subir" / "Elegir una llamada"; `Segmented` "Toda la llamada" / "Un momento" (con campo para el fragmento); nota opcional con voz.
- `ModelCallProposals`: una tarjeta por propuesta con el extracto en burbuja de cita (etiqueta "Comercial"/"Cliente"), el texto propuesto, y acciones "Usar" (principal), "Editar", "Descartar" (quieto); aviso arriba si `speaker_warning` ("¿Esto lo dijo el comercial?") con botón "Intercambiar hablantes"; las propuestas `skipped` por `guidance_too_long` ofrecen "Crear objeción propia".

- [ ] **Step 1: Preview** con 3 propuestas, aviso de hablantes y una desbordada.
- [ ] **Step 2: Implementar** componentes y acciones del hook.
- [ ] **Step 3: Verificación de fase (Fase 1).** Backend: `cd backend && $PY -m pytest tests/playbooks -q`. Frontend: tests, `npm run lint:ui`, `npm run build`. Visual: abrir `/__preview/playbook-assistant` en el navegador integrado y capturar cada estado de T9–T11 en claro, oscuro (`resize_window colorScheme`) y móvil (375 px); corregir lo que no esté al nivel de Inicio y Coaching. Con login de pruebas disponible, repetir con Reticle el flujo real; si no, decir que no se verificó contra la app real.
- [ ] **Step 4: Commit** `feat(playbooks): model call import` y push de la fase: `git pull --rebase && git push origin staging`.

---

## FASE 2: la prueba

### Task 12: Casos de prueba

**Files:**
- Create: `backend/app/services/playbooks/trial.py` (primera parte), `backend/app/prompts/playbook_trial_cases_v1.md`
- Test: `backend/tests/playbooks/test_trial.py`

**Interfaces:**
- Produces: `TYPICAL_OBJECTIONS: dict[str, list[str]]` (ES/EN, una frase del cliente por objeción fija); `async build_cases(*, events: list[dict], source_texts: list[str], entries: list[dict], lang: str, motion_key: str, limit: int = 12, llm=None) -> list[dict]` con `{"id", "source": "real" | "document" | "typical", "client_text", "motion_key"}`.
- Orden y reparto: hasta 8 reales (frases distintas de al menos 20 caracteres de `events`), el resto del modelo a partir de los documentos (sin respuestas, solo frases que diría un cliente), y objeciones típicas si faltan; nunca más de 12 ni menos de 10 cuando hay material para ello; sin duplicados.

- [ ] **Step 1: Tests que fallan.** Empresa vacía → 10 casos `typical`; 20 eventos reales → 8 `real` y el resto `document` o `typical`; duplicados y frases de menos de 20 caracteres se descartan; el modelo que falla no rompe (se completa con típicas); ningún caso contiene una respuesta.
- [ ] **Step 2: Ejecutar:** FAIL → implementar → PASS.
- [ ] **Step 3: Commit** `feat(playbooks): trial cases`.

### Task 13: Ejecutar un caso con el borrador

**Files:**
- Modify: `backend/app/services/playbooks/trial.py` (segunda parte)
- Test: `backend/tests/playbooks/test_trial_runner.py`

**Interfaces:**
- Consumes: `read_turn(conversation, latest, custom)` (`copilot/turn.py`), `custom_entries(snapshot)` (`copilot/playbook_objections.py`), `stream_objection_suggestion(...)` (`copilot/suggest.py`), `SuggestGrounding` (`copilot/grounding.py`), `_matched_entry(grounding, entry_id)` (`api/copilot.py`, importado, no modificado).
- Produces: `draft_snapshot(editor: dict, motion_key: str) -> dict` (`{"sales_motion_key", "version_id": "draft", "steps", "entries"}` con el formato publicado); `async run_case(case: dict, *, snapshot: dict, knowledge: dict | None, product_context: str, lang: str) -> dict` → `{"detected": str, "entry_id": str | None, "card": dict | None, "grounded": bool}`. Orquestación idéntica al endpoint: `read_turn` con `custom_entries(snapshot)`, `objection_type` solo si está en `turn.OBJECTIONS`, `entry=_matched_entry(...)`, `call_mode="softphone"`, y se toma el evento `result` de `stream_objection_suggestion`.

- [ ] **Step 1: Tests que fallan** (con `read_turn` y `stream_objection_suggestion` sustituidos): (a) el `playbook_snapshot` que recibe la función es el del borrador, con sus entradas; (b) `custom` se calcula del borrador; (c) un tipo no listado en `turn.OBJECTIONS` llega como `None`; (d) sin `result` en el flujo → `card is None`; (e) test de equivalencia: para el mismo snapshot, los argumentos que `run_case` pasa a `stream_objection_suggestion` coinciden con los del endpoint `/copilot/suggest` (capturados con el mismo doble) en `objection_type`, `entry`, `call_mode` y `grounding.playbook_snapshot`; (f) si `_matched_entry` deja de existir con esa firma, el test lo dice.
- [ ] **Step 2: Ejecutar:** FAIL → implementar → PASS.
- [ ] **Step 3: Commit** `feat(playbooks): run trial cases against the draft`.

### Task 14: Veredictos, resultado y activación

**Files:**
- Modify: `backend/app/services/playbooks/trial.py` (tercera parte)
- Test: `backend/tests/playbooks/test_trial_verdicts.py`

**Interfaces:**
- Produces: `add_branch(guidance: str, when: str, text: str) -> str` (añade `" Si {when}: {text}"` y lanza `ValueError("guidance_too_long")` si pasa de `MAX_GUIDANCE`); `apply_verdict(editor: dict, case: dict, entry_id: str | None, verdict: str, text: str | None) -> dict` con `verdict in {"approve","corrected","unknown","never_say","branch"}` que devuelve el `editor` nuevo (`corrected` fija la respuesta; sin entrada crea una `custom` con `label` de las 8 primeras palabras del cliente y `trigger` la frase; `never_say` añade `" No digas: {text}."`; `branch` usa `add_branch`); `trial_result(verdicts: list[dict]) -> dict` → `{"approved", "total", "percent": int | None, "weak_topics": [str], "warn": bool, "can_activate": True}` (`percent` solo con `total >= 3`; `warn` si `percent < 80`); `async similar_phrase(case, lang, *, llm=None) -> str`; `async activate(repository, membership, motion_keys: list[str]) -> list[str]` (publica los borradores tocados).

- [ ] **Step 1: Tests que fallan.** `corrected` sobre entrada existente cambia solo su `guidance`; sin entrada crea una `custom` válida; texto de 1.201 caracteres → `ValueError("guidance_too_long")` y el editor devuelto es el original; `never_say` añade la regla; `trial_result` con 9 aprobadas de 12 → `percent 75`, `warn True`; con 2 casos → `percent None`; `activate` publica y propaga `PublishError`.
- [ ] **Step 2: Ejecutar:** FAIL → implementar → PASS.
- [ ] **Step 3: Commit** `feat(playbooks): trial verdicts and activation`.

### Task 15: API de la prueba

**Files:**
- Modify: `backend/app/api/playbook_assistant.py`
- Test: `backend/tests/playbooks/test_trial_api.py`

**Interfaces:**
- Produces: `POST /trial` `{motion_key?, lang?}` (crea o reanuda la sesión `trial`, devuelve casos y el primero ejecutado); `GET /trial/{id}`; `POST /trial/{id}/cases/{case_id}/run`; `POST /trial/{id}/cases/{case_id}/verdict` `{verdict, text?}` (aplica al borrador con `save_draft`, vuelve a ejecutar el caso y devuelve además `similar: {text, card}`); `GET /trial/{id}/result`; `POST /trial/{id}/activate`. Errores: `guidance_too_long` → 422 con `detail.code`; `stale_draft` → 409.

- [ ] **Step 1: Tests que fallan** con dobles de `run_case`: crear la prueba devuelve entre 10 y 12 casos; veredicto `corrected` guarda en el borrador y devuelve la tarjeta nueva y `similar`; `guidance_too_long` → 422 y borrador intacto; `result` tras 12 veredictos devuelve `percent`; `activate` publica y devuelve las claves; sin activar el almacén → 503.
- [ ] **Step 2: Ejecutar:** FAIL → implementar → PASS.
- [ ] **Step 3: Commit** `feat(playbooks): trial API`.

### Task 16: Pantalla de la prueba

**Files:**
- Create: `src/features/playbooks/components/TrialRunner.tsx`, `ReviewCase.tsx`, `TrialResult.tsx`, `src/features/playbooks/hooks/useTrial.ts`
- Modify: `src/lib/playbook-assistant.ts` (si hace falta un helper), preview

**Interfaces:**
- `ReviewCase` (reutilizable en T19): `{ clientText: string; card: { sayThis: string } | null; source: "real" | "document" | "typical"; actions: ReviewAction[]; onAction(action, text?) }`. Muestra la frase del cliente en burbuja de cita, "Lo que vería tu comercial" en la burbuja de resaltado con el texto de la tarjeta, o "Vocify aún no tiene respuesta" si `card === null`, y la fila de acciones: **Vale** (`Button` principal, tecla 1), **Yo diría…** (`variant="outline"`, 2; abre el campo de voz/texto inline), **No lo sé** (`variant="quiet"`, 3), **Nunca digas esto** (`variant="dangerGhost"`, 4). Tras "Yo diría…" y guardar, la tarjeta nueva aparece con un destello suave y debajo "¿Y si el cliente dijera «…»?" con la tarjeta de esa frase y botones "Sirve igual" / "Es otra situación" (esta última pide la rama y llama a `branch`). `guidance_too_long` muestra "No cabe: crear objeción propia".
- `TrialRunner`: cabecera con `trialMeter`, "4 de 12" y "Salir y retomar luego"; un caso a la vez; teclas 1–4.
- `TrialResult`: frase grande ("9 de 12 aprobadas sin cambiar"), medidor, lista de temas flojos como filas de Coaching, y botones: principal "Activar para el equipo", outline "Otra ronda sobre {tema}"; si `warn`, texto ámbar "Está por debajo del 80%. Puedes activarlo igualmente." Con menos de 3 casos muestra recuento.

- [ ] **Step 1: Preview** con estados `case-real`, `case-no-answer`, `editing`, `corrected`, `similar`, `too-long`, `result-good`, `result-warn`, `result-few`.
- [ ] **Step 2: Implementar** componentes y hook (`useTrial`).
- [ ] **Step 3: Verificación de fase (Fase 2).** Backend `tests/playbooks`; frontend tests, `lint:ui`, `build`; capturas de todos los estados (claro, oscuro, móvil) y ajuste fino hasta que se lea como parte de Inicio/Coaching. Intentar el flujo real con Reticle si hay login de pruebas.
- [ ] **Step 4: Commit** `feat(playbooks): trial screen` y push de la fase a `staging`.

---

## FASE 3: perfeccionar con el uso

### Task 17: Núcleo del success rate y comprobación de viabilidad

**Files:**
- Create: `backend/app/services/playbooks/outcomes.py`, `backend/app/prompts/suggestion_outcome_v1.md`, `backend/evals/outcomes/run.py`, `backend/evals/outcomes/README.md`
- Test: `backend/tests/playbooks/test_outcomes.py`

**Interfaces:**
- Consumes: `memo["extraction"]["intelligence"]["objections"]` (`category`, `objection_id`, `resolution`, `quote`, `response`), `live_assist_events` (`id`, `capture_id`, `latest_turn`, `objection_type`, `entry_id`, `source_id`, `say_this`, `is_objection`).
- Produces: `match_objection(event: dict, objections: list[dict]) -> dict | None` (por solapamiento de texto entre `latest_turn` y `quote` ≥ 0,6 y misma categoría cuando `objection_type` es una categoría fija); `async judge_use(say_this: str, rep_reply: str | None, *, llm=None) -> str` (`used | adapted | not_used | unknown`; sin respuesta del comercial → `not_used`; por intención, no por palabras); `async judge_question(window: str, latest_turn: str, say_this: str, *, llm=None) -> {"used": str, "resolved": str}`; `async outcome_for_event(event: dict, memo: dict, *, llm=None) -> dict` → `{"event_id", "used", "resolved", "resolved_by": "extraction" | "judge"}`; `success_stats(rows: list[dict], *, min_cases: int = 3) -> dict` → `{"resolved", "clear", "unknown", "rate": float | None, "used", "use_rate": float | None, "sample": int}`.
- Reglas: para objeciones emparejadas, `resolved` sale de `resolution` (`resolved → resolved`, `open → not_resolved`, `unknown → unknown`); para preguntas o sin emparejar, de `judge_question`. `success_stats`: `rate = resolved / (usadas+adaptadas con veredicto claro)`, `rate` es `None` con `clear < 3`; los `unknown` se cuentan aparte.
- Script: `python -m evals.outcomes.run --email <rep> --limit 20 --out sheet.csv` genera la hoja (cliente, sugerencia, lo que dijo el comercial, veredicto de Vocify, columna vacía "etiqueta de Toni"); `--score sheet.csv` calcula acuerdo y % de "no se sabe" y dice "SIGUE" o "DETENER" con los umbrales de la spec. Solo lectura.

- [ ] **Step 1: Tests que fallan.** `match_objection` acierta con la misma frase y rechaza categorías distintas; `outcome_for_event` usa `resolution` de la extracción y marca `resolved_by == "extraction"`; sin emparejar usa el juez (doble); `judge_use` sin respuesta → `not_used`; `success_stats`: 2 casos → `rate None`; 4 usadas con 3 resueltas → `0.75`; los `unknown` no entran en el denominador.
- [ ] **Step 2: Ejecutar:** FAIL → implementar → PASS.
- [ ] **Step 3: Generar la hoja** de 20 sugerencias reales (solo lectura) si hay credenciales en `backend/.env`; si no, dejar el script probado con datos de ejemplo y decirlo. **Decisión de Toni:** puntuar las etiquetas; hasta que el acuerdo sea ≥80% y los "no se sabe" ≤30%, `PLAYBOOK_SUCCESS_RATE_ENABLED` queda apagado.
- [ ] **Step 4: Commit** `feat(playbooks): suggestion outcomes core and feasibility script`.

### Task 18: Cola, cobertura y estadísticas (servicio y API)

**Files:**
- Create: `backend/app/services/playbooks/review_queue.py`
- Modify: `backend/app/api/playbook_assistant.py`
- Test: `backend/tests/playbooks/test_review_queue.py`, `backend/tests/playbooks/test_improve_api.py`

**Interfaces:**
- Produces (`review_queue.py`): `failing_by_answer(outcomes: list[dict], *, min_cases: int = 3, days: int = 30, now=None) -> list[dict]` (`{"answer_key", "failing", "cases": [...]}` con respuestas con ≥3 casos `not_used` o `used`+`not_resolved`); `coverage_stats(events: list[dict], *, days: int = 28, min_cases: int = 3, now=None) -> dict` (`{"detected", "answered", "rate": float | None}`); `async refresh_outcomes(store, supabase, company_id, *, limit: int = 40, llm=None) -> int` (juzga eventos nuevos con `capture_id`, nunca vuelve a juzgar los ya juzgados); `async refresh_moments(store, company_id, groups) -> int` (copia los casos a `playbook_review_moments`, sin duplicar).
- API (mismo router): `GET /improve/stats` (cobertura siempre; `success` solo con `PLAYBOOK_SUCCESS_RATE_ENABLED`); `POST /improve/refresh`; `GET /improve/queue`; `POST /improve/queue/{moment_id}/action` `{action: "keep" | "correct" | "branch" | "new_objection", text?}` (reutiliza `apply_verdict`/`add_branch`; guarda en el borrador); `POST /improve/publish` (publica los borradores tocados); `POST /improve/outcomes/{event_id}/verdict` `{resolved: "resolved" | "not_resolved"}` (el jefe corrige un veredicto: `resolved_by = "admin"`).

- [ ] **Step 1: Tests que fallan.** Empresa sin eventos → estadísticas vacías con recuentos y sin error; 3 casos fallidos de la misma respuesta → un grupo; 2 → ninguno; `refresh_outcomes` no vuelve a juzgar un evento ya juzgado; la acción `correct` cambia la respuesta en el borrador y marca el momento como `corrected`; `success` ausente con el flag apagado; corrección de veredicto cambia el `success_stats`.
- [ ] **Step 2: Ejecutar:** FAIL → implementar → PASS.
- [ ] **Step 3: Commit** `feat(playbooks): improvement queue and stats`.

### Task 19: Pantalla "Mejoras"

**Files:**
- Create: `src/features/playbooks/components/ImproveStats.tsx`, `ImproveQueue.tsx`, `src/features/playbooks/hooks/useImprove.ts`
- Modify: preview

**Interfaces:**
- `ImproveStats`: dos cifras sobrias en la parte superior, estilo Inicio (número grande `tabular-nums`, etiqueta de 13px): **Cobertura** ("31 de 40 preguntas con respuesta") y **Success rate** (solo con el flag; "13 de 19 resueltas" o `rateLabel`); botón "Actualizar" quieto.
- `ImproveQueue`: lista tipo Coaching de respuestas a mejorar (fila con nombre de la respuesta, medidor de segmentos por veredicto y "3 casos"); cada fila se abre con `Collapsible` y muestra los casos con `ReviewCase` en modo real: frase del cliente (burbuja), lo sugerido (burbuja de resaltado), lo que dijo el comercial y qué pasó (chip "Resuelta"/"No resuelta"/"No se sabe", con enlace "No es así" que corrige el veredicto), y acciones: **Mantener**, **Yo diría…**, **Añadir rama**, **Crear objeción**. Botón principal fijo al pie "Publicar mejoras (3)" cuando hay borradores pendientes. Vacío: "Todo en orden esta semana" (patrón `CoachEmpty`).

- [ ] **Step 1: Preview** con estados `stats-few`, `stats-ok`, `queue`, `queue-open`, `empty`, `not-enabled`.
- [ ] **Step 2: Implementar** componentes y hook.
- [ ] **Step 3: Verificación de fase (Fase 3).** Backend `tests/playbooks`; frontend tests, `lint:ui`, `build`; capturas (claro, oscuro, móvil); Reticle si hay login de pruebas.
- [ ] **Step 4: Commit** `feat(playbooks): improvement screen`.

### Task 20: Bloque en el informe semanal y enlace

**Files:**
- Modify: `backend/app/services/reporting/weekly.py` (clave opcional `playbook_improvement` en `team_snapshot`), el renderizado del informe de equipo en `backend/app/services/reporting/presentation.py`/`digest_email.py` si procede
- Test: `backend/tests/reporting/test_weekly.py` (caso nuevo)

**Interfaces:**
- Consumes: `failing_by_answer`, `AssistantStore`.
- Produces: `playbook_improvement_block(store, company_id, *, limit: int = 5) -> dict | None` → `{"items": [{"label", "failing", "total"}], "link": "/dashboard/playbook?view=improve"}`; `None` si el flag está apagado, el almacén no existe o no hay casos. `team_snapshot` lo añade solo si no es `None`.

- [ ] **Step 1: Test que falla.** Con 6 respuestas con ≥3 casos fallidos, el bloque trae 5; sin casos → la clave no aparece y el resto del snapshot es idéntico al actual (regresión).
- [ ] **Step 2: Ejecutar:** FAIL → implementar → PASS; ejecutar `tests/reporting -q`.
- [ ] **Step 3: Comprobar con Dani** (la zona de informes cambia a menudo): si `team_snapshot` o su renderizado cambiaron desde que se escribió este plan, adaptar el enganche sin tocar su contrato; si el cambio es mayor, dejar el task como pendiente y decirlo.
- [ ] **Step 4: Commit** `feat(reports): playbook improvements in the weekly report`.

### Task 21: Cierre

**Files:**
- Create: `docs/superpowers/plans/2026-10-16-activacion-playbook-asistente.sql` (copia del `APPLY_IN_SUPABASE` con instrucciones de activación y de flags)
- Modify: spec (estado y decisiones finales)

- [ ] **Step 1: Pasadas completas.** `cd backend && $PY -m pytest -q` (anotar fallos previos frente a los nuevos), `make test-js`, `npm run lint:ui`, `npm run build`.
- [ ] **Step 2: Comprobar que no se tocó lo prohibido:** `git diff --stat staging~N -- backend/app/services/copilot backend/app/api/copilot.py src/features/desktop backend/app/services/coaching` vacío.
- [ ] **Step 3: SQL de activación** con orden: tablas 081 → flags (`PLAYBOOK_ASSISTANT_ENABLED` para la empresa de prueba; `PLAYBOOK_SUCCESS_RATE_ENABLED` solo tras la comprobación de viabilidad).
- [ ] **Step 4: Resumen para el dueño:** qué hay en staging, qué falta por activar (SQL, flags, números `081` acordados con Dani), qué no se pudo verificar y la decisión pendiente del success rate.
- [ ] **Step 5: Commit** `docs(playbooks): activation SQL and spec status` y push a `staging`. No se mergea a `main`.
