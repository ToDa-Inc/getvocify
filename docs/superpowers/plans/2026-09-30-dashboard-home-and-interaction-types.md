# Dashboard home, interaction types and settings — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One Inicio for every role (chat + condensed Today/team signals + latest interactions), interactions tagged by channel and type, Settings reorganised, dark mode.

**Architecture:** Types reuse `memos.sales_motion_key` (label from `GET /playbooks`); channel stays `memos.interaction_kind`. Backend adds list filters, `salesMotionKey`, the voice-note channel and an `internal` type. Frontend replaces MemosPage with Interacciones, lifts Ask's thread out of the floating sheet, and composes a new Inicio from small units (pure logic in `src/lib`, tested with `node:test`).

**Tech Stack:** FastAPI + Supabase (pytest, venv `~/.venvs/vocify-backend/bin/python`), React/Vite/Tailwind, TanStack Query, `node --test` for `src/lib/*.test.ts`.

**Spec:** `docs/superpowers/specs/2026-09-30-dashboard-home-and-interaction-types-design.md`

## Global Constraints

- Work only in worktree `/Users/danizal/getvocify-home` (branch `feat/home-dashboard`). Never touch `/Users/danizal/getvocify` (another session's uncommitted work) or the backend on port 8888.
- **Never apply migrations or write to the shared DB.** Staging and production share it. No new migration is needed by this plan.
- Reuse the kit: `Button` (`default`/`ghost`/`link`/`icon`), `IconAction`, `Tabs`, `Tooltip`, `Pagination`, `DropdownMenu`, `Sheet`, `ScrollArea`; tokens in `THEME_TOKENS` (`src/lib/theme/tokens.ts`). Icons have tooltip + `aria-label`. `PAGINATION.DEFAULT_PAGE_SIZE` = 20.
- All user copy lives in `src/lib/product-catalog.ts`, ES **and** EN (`t.product.*`). No hardcoded strings. Spanish copy: short, direct, no "IA", no filler.
- One primary action per screen; empty, loading and error states designed; no page scroll on Inicio (only the thread/feed block scrolls); transitions ≤200ms and disabled under `prefers-reduced-motion`.
- Pure logic goes in `src/lib/*.ts` with a `node:test` file beside it. Run: `node --test src/lib/<name>.test.ts`. Backend: `cd backend && ~/.venvs/vocify-backend/bin/python -m pytest tests/<path> -q`.
- Type check: `npx tsc -p tsconfig.app.json --noEmit` must not add errors. Never weaken a check to pass.
- Tables and lists are alphabetical or chronological, never ranked by person (no-ranking rule).
- Commit per task, message `feat(<scope>): …`, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- A memo with `interaction_kind` NULL (legacy) must still match the channel filter it derives to.
- A memo whose `sales_motion_key` is NULL or names a deleted/paused type: chip shows channel only / the raw label, never crashes.
- Manual retag (`playbook_pin.source="manual"`) must never be overwritten by the AI `internal` detection.
- Composer sends on Enter, not on Shift+Enter or during IME composition; empty/whitespace never sends.
- Inicio with 0 interactions, 0 suggestions, CRM not connected, and a manager with no team data: each renders a designed state.
- Old URLs (`/dashboard/memos`, `/dashboard/process`, `/dashboard/playbook`, `/dashboard/ask`) still land somewhere useful.

---

### Task 1: Memo list filters, `salesMotionKey`, voice-note channel (backend)

**Files:**
- Modify: `backend/app/services/captures.py` (add `interaction_kind_filter`), `backend/app/api/memos.py` (`list_memos`, `_memo_from_row`, upload endpoint near `:604-649`), `backend/app/models/memo.py` (`Memo`)
- Test: `backend/tests/memos/test_list_filters.py`, `backend/tests/captures/test_interaction_kind_filter.py`

**Interfaces:**
- Produces: `interaction_kind_filter(kind: str) -> str` — a PostgREST `or_` expression matching stored `interaction_kind == kind` **or** (NULL stored and `interaction_kind_for(source, source_type, None) == kind`). `GET /memos?interaction_kind=<kind>&sales_motion_key=<key>`; `Memo.salesMotionKey: Optional[str]`; `/memos/upload` optional form field `interaction_kind` (one of `INTERACTION_KINDS`) stored on the row.

- [ ] **Step 1: Write failing tests.** `test_interaction_kind_filter_matches_derivation`: for each of `call|meeting|visit|voice_note`, and each `(source, source_type)` sample from `interaction_kind_for`'s cases (`vocify_call`, `hubspot_call`, `whatsapp`, `web/meeting_transcript`, `recall/recall_bot`, `web/voice_memo`), assert a row with NULL stored kind is selected by exactly the filter of its derived kind (evaluate the expression with a tiny in-test interpreter or assert on the generated clauses). `test_list_memos_rejects_unknown_interaction_kind` → 422. `test_list_memos_filters_by_sales_motion_key`. `test_memo_exposes_sales_motion_key`. `test_upload_stores_voice_note_kind` and `test_upload_rejects_unknown_kind` (422).
- [ ] **Step 2: Run** the two files; expect FAIL (names undefined).
- [ ] **Step 3: Implement** the filter helper, the two query params in `list_memos` (mirror the existing `status` validation style), `salesMotionKey=memo_data.get("sales_motion_key")` in `_memo_from_row`, and the `interaction_kind` form field on upload (default unchanged when absent).
- [ ] **Step 4: Run** `pytest tests/memos tests/captures -q`; expect all pass.
- [ ] **Step 5: Commit** `feat(memos): filter by channel and type, expose the type, store voice notes`.

---

### Task 2: `internal` type — detection and skip rules (backend)

**Files:**
- Modify: `backend/app/models/memo.py` (`MemoExtraction`), the extraction/intelligence step that produces `MemoExtraction` (find via `grep -rn "MemoExtraction(" backend/app`; prompts in `backend/app/prompts/`), the post-extraction pin logic near `playbook_fields_for_capture`/`repin_before_c04` (`backend/app/services/playbooks/routing.py`), the scoring entry point (`grep -rn "scoring_v1" backend/app`), `backend/app/api/playbook_rules.py` (`POST /memos/{id}/playbook`)
- Test: `backend/tests/playbooks/test_internal_type.py`

**Interfaces:**
- Produces: `INTERNAL_KEY = "internal"` in `backend/app/services/playbooks/catalog.py`; `MemoExtraction.customerPresent: Optional[bool] = None` (null = unknown, never coerced to false); `apply_internal_detection(memo_row: dict, extraction: dict) -> dict` returning the fields to update (`sales_motion_key`, `pipeline_meta` with `playbook_pin.source="internal"`) or `{}`.

- [ ] **Step 1: Write failing tests.** `test_customer_absent_tags_internal` (`customerPresent=False`, pin source `role_default` → `sales_motion_key=="internal"`); `test_unknown_never_tags_internal` (`None`); `test_manual_pin_is_never_overwritten` (source `manual`, `False` → `{}`); `test_internal_memo_is_not_scored`; `test_internal_memo_makes_no_crm_proposals`; `test_manual_retag_accepts_internal` (POST with key `internal` sets a manual pin, clears the scoring version, and does not require a live playbook).
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement.** Add `customerPresent` to the extraction schema and to the intelligence prompt as a new prompt version (copy the latest `intelligence_vN.md` to `vN+1`, add one rule: true only if someone outside the team spoke; null if unsure; keep all else identical) and select it where the version is chosen. Call `apply_internal_detection` where extraction lands. Skip scoring and CRM sync proposals for `internal`.
- [ ] **Step 4: Run** `pytest tests/playbooks tests/memos -q`; expect pass, no regressions.
- [ ] **Step 5: Commit** `feat(playbooks): internal calls are detected, tagged and never scored`.

---

### Task 3: Interaction feed logic (frontend, pure)

**Files:**
- Create: `src/lib/interactions.ts`, `src/lib/interactions.test.ts`
- Modify: `src/features/memos/types.ts` (`Memo`: `interactionKind`, `salesMotionKey`; `MemoFilters`: `interactionKind`, `salesMotionKey`), `src/features/memos/api.ts` (`list` sends `interaction_kind`, `sales_motion_key`; add `memosApi.setType(id, key)` → `POST /memos/{id}/playbook`)

**Interfaces:**
- Produces:
  - `type Channel = "call" | "meeting" | "visit" | "voice_note"`
  - `type TypeOption = { key: string; label: string; scored: boolean }`
  - `typeOptions(playbooksPayload: unknown): TypeOption[]` — from `GET /playbooks` (skip deleted; `internal` always last with `scored:false`)
  - `typeChip(memo: {salesMotionKey?: string|null}, options: TypeOption[]): { key: string; label: string } | null` — null when no key; unknown key → `{key, label: key}`
  - `feedQuery(state: {channel: Channel|"all"; typeKey: string|"all"; authorUserId?: string; page: number}, pageSize: number): MemoFilters` — asks for `pageSize + 1` rows and `offset = page*pageSize`
  - `pageOf<T>(rows: T[], pageSize: number): { items: T[]; hasMore: boolean }`

- [ ] **Step 1: Write failing tests** for each function: `typeOptions` orders types alphabetically with `internal` last and drops deleted; `typeChip` null / unknown-key / known; `feedQuery` page 0 → `limit 21, offset 0`, page 2 → `offset 40`, `all` omits the filter; `pageOf` with exactly `pageSize+1` rows → `hasMore true`, items trimmed; 0 rows → empty.
- [ ] **Step 2: Run** `node --test src/lib/interactions.test.ts`; expect FAIL.
- [ ] **Step 3: Implement** the module and the types/api edits.
- [ ] **Step 4: Run** the test file; expect pass; `npx tsc -p tsconfig.app.json --noEmit` adds no errors.
- [ ] **Step 5: Commit** `feat(interactions): feed logic and API filters`.

---

### Task 4: Interacciones page and row (frontend)

**Files:**
- Create: `src/features/interactions/components/InteractionRow.tsx`, `TypeChip.tsx` (menu that retags via `memosApi.setType`, includes "Interna"), `InteractionFilters.tsx`, `src/features/interactions/hooks/useInteractionFeed.ts`, `src/pages/dashboard/InteractionsPage.tsx`
- Modify: `src/App.tsx` (route `/dashboard/interactions`; `/dashboard/memos` → `<Navigate>`; `memos/:id` stays), `src/lib/product-catalog.ts` (ES+EN keys: channel labels, "Tipo", "Interna", empty/error/retag-toast copy), delete `src/pages/dashboard/MemosPage.tsx` once unreferenced

**Interfaces:**
- Consumes: Task 3 exports; `GET /playbooks` (already used by playbooks feature — reuse its query hook, do not duplicate).
- Produces: `useInteractionFeed(opts: { scope: "me" | "company"; pageSize: number; initialChannel?: Channel | "all" })` → `{ items: Memo[]; hasMore: boolean; page: number; setPage; channel; setChannel; typeKey; setTypeKey; authorUserId; setAuthorUserId; isLoading; isError; retry }`; `<InteractionRow memo options />`; `<InteractionsPage />`.

- [ ] **Step 1:** Add ES/EN copy keys; hardcoded EN/ES status badge strings from the old page move into the catalog.
- [ ] **Step 2:** Build the hook (TanStack Query, `keepPreviousData`, refetch interval 10s only while any row is `uploading|transcribing|extracting`), row, chip menu, filters (Tabs for channel; `Select` for type and, for managers, author) and the page with `Pagination`. Row layout: channel chip, type chip, title, `persona → contacto`, duration, status, age. Designed empty ("Aún no hay interacciones" + mic action), error (retry) and loading (skeleton rows).
- [ ] **Step 3:** Wire routes and redirect; remove `MemosPage`.
- [ ] **Step 4: Verify** with Reticle (project rule): run the dev server via `preview_start`, open `/dashboard/interactions`, drive one flow (change type filter → list narrows; retag chip → chip updates) using `reticle_act_and_wait` with a declared `until`; report the verdict honestly (`unknown`/`no-fault` ≠ pass). Login: use the local test account from memory note `reference-local-test-account.md`.
- [ ] **Step 5:** `npx tsc` clean; commit `feat(interactions): one list of every capture, by channel and type`.

---

### Task 5: Navigation, routes and avatar menu (frontend)

**Files:**
- Modify: `src/lib/nav.ts`, `src/components/dashboard/DashboardLayout.tsx` (remove Ask pill and `askOpen` toggle from the top bar; keep the sheet for ⌘K and `state.ask`; add avatar `DropdownMenu`), `src/App.tsx` (redirects), `src/lib/product-catalog.ts`
- Create: `src/components/dashboard/AvatarMenu.tsx`
- Test: `src/lib/nav.test.ts` (extend the existing one if present)

**Interfaces:**
- Produces: `navItemsFor({role, …})` → manager `[home("Inicio"), interactions("Interacciones"), insights("Equipo"), settings]`, rep `[home, interactions, coach, settings]`; new `NavItemId` `"interactions"`. `<AvatarMenu />` with Perfil, Idioma (ES/EN via `useLanguage`), Cerrar sesión (Tema is added in Task 9). Redirects: `/dashboard/process`→`/dashboard/settings/playbooks`, `/dashboard/playbook`→`/dashboard/coach?tab=playbook`.

- [ ] **Step 1: Write failing tests** for `navItemsFor` for owner, admin, member (with and without `repWorkspace`): item ids/order, `showPlans` unchanged.
- [ ] **Step 2: Run**; FAIL. **Step 3: Implement** nav, layout, avatar menu, redirects; `⌘K`/`Ctrl+K` opens the sheet. Keep `topBarActions` for Llamar only.
- [ ] **Step 4: Run** the nav test; `tsc` clean; Reticle: open `/dashboard`, the sidebar shows the new items and the avatar menu switches language (`until`: a text signal in the new language).
- [ ] **Step 5: Commit** `feat(nav): Inicio, Interacciones, Equipo and a profile menu`.

---

### Task 6: `AskThread` lifted out of the floating panel (frontend)

**Files:**
- Create: `src/features/ask/components/AskThread.tsx`
- Modify: `src/features/ask/components/AskPanel.tsx` (becomes a thin shell around `AskThread`), `src/features/ask/components/Composer.tsx` only if needed for placement

**Interfaces:**
- Produces: `<AskThread conversation={ReturnType<typeof useAskConversation>} composerPlacement="bottom" />` — thread (turns, activity, confirm cards, coverage note) plus composer, no header/chrome, fills its parent's height, scrolls internally. `AskPanel` keeps its header (history, new, delete, close) and renders `AskThread`. State is owned by the caller so Inicio and the sheet can share one conversation.

- [ ] **Step 1:** Extract with no behaviour change; **Step 2:** existing Ask tests (`node --test src/lib/ask-*.test.ts`) still pass; the floating sheet still works (Reticle: ⌘K opens it, send a question, a turn appears — `until` on the answer signal).
- [ ] **Step 3: Commit** `refactor(ask): the thread stands alone so the home can host it`.

---

### Task 7: Inicio — composer, feed, rep rail, team signals (frontend)

**Files:**
- Create: `src/lib/team-signals.ts` + `team-signals.test.ts`, `src/lib/home-rail.ts` + `home-rail.test.ts`, `src/features/home/components/InicioPage.tsx`, `HomeComposer.tsx`, `LatestInteractions.tsx`, `RepRail.tsx`, `SignalsRail.tsx`, `src/features/home/hooks/useHomeChat.ts`
- Modify: `src/pages/dashboard/DashboardHome.tsx` (render `InicioPage` for every role once onboarding is done; keep the onboarding and paywall redirects), `src/lib/product-catalog.ts`; reuse `useAskSuggestions`, `useInteractionFeed`, `src/features/today/api.ts` reads

**Interfaces:**
- Consumes: Tasks 3, 4, 6.
- Produces:
  - `type TeamSignal = { id: string; tone: "warn" | "neutral"; textKey: string; params: Record<string,string|number>; question: string }`
  - `teamSignals(input: { reps: {userId: string; name: string; adherence: number|null; prevAdherence: number|null; attempts: number}[]; diagnosis: Diagnosis[] }): TeamSignal[]` — max 3; rules in order: process diagnosis (existing `summaryDiagnosis`), a rep whose adherence dropped ≥15 points with ≥30 scored calls in both periods, a rep with 0 attempts. Sorted by rule order then name — never by score across people.
  - `railCounts(today: TodayResponse): { meetings: TodayItem[]; needsOk: number; tasks: number; followups: number; fresh: number }` (meetings ≤3, soonest first)
  - `useHomeChat()` → `{ mode: "home" | "chat"; conversation; send(text); reset() }`; `?c=` mirrors the conversation id; Esc calls `reset`.
  - `<InicioPage />`: `md+` two columns (main flex, rail 320px), below `md` the rail stacks under the feed.

- [ ] **Step 1: Write failing tests** for `teamSignals` (drop rule fires at exactly 15 points and not at 14; min-sample rule; cap 3; no ranking across people; empty input → `[]`) and `railCounts` (cap 3 meetings sorted soonest; counts by section; empty).
- [ ] **Step 2: Run**; FAIL. **Step 3: Implement** the two libs.
- [ ] **Step 4: Build the components.** Composer: Enter sends, Shift+Enter newline, ignore during IME composition, empty/whitespace no-op, mic reuses `VoiceComposer`. On send: composer moves to the bottom and the thread fills the main column (CSS transform ≤200ms; none under reduced motion); feed fades out. Suggestions: render exactly what `/ask/suggestions` returns (≤3), none for a new account. States: no interactions → "Graba tu primera llamada" with the mic; rail nothing due → "Todo al día"; CRM not connected → the existing connect-CRM card in the rail; manager without data → one neutral signal linking to Ajustes.
- [ ] **Step 5: Run** both lib tests; `tsc` clean. Reticle as rep and as manager: `/dashboard` renders composer + feed + rail; typing a question and pressing Enter switches to chat mode (`until`: thread present and composer at bottom); Esc returns. Check 0-item state by using the fresh test company if available, else say it was not exercised.
- [ ] **Step 6: Commit** `feat(home): one Inicio — ask, today and the latest interactions`.

---

### Task 8: Settings reorganisation (frontend)

**Files:**
- Modify: `src/lib/settings-nav.ts` (add `playbooks` tab, manager only, after Team; remove language from the side nav), `src/pages/dashboard/settings/SettingsLayout.tsx`, `src/App.tsx` (`settings/playbooks` renders `PlaybooksSection` instead of redirecting), `src/pages/dashboard/SalesProcessPage.tsx` (split), `src/pages/dashboard/HeadOfSalesTeamPage.tsx` (gains `ProcessHealth` + `ObjectionBreakdown`), `src/pages/dashboard/HeadOfSalesSummaryPage.tsx` (Resumen content is reachable at `/dashboard/insights` — add a "Resumen | Personas" `Tabs` there), `src/pages/dashboard/CoachPage.tsx` (tab `playbook` renders `PlaybookPage` content; `?tab=` selects it), `src/components/dashboard/settings/InterfaceLanguageSettings.tsx` (delete when unreferenced)
- Test: `src/lib/settings-nav.test.ts`

**Interfaces:**
- Produces: `SETTINGS_TABS` entry `{ id: "playbooks", … }` visible to managers; Equipo route shows Resumen and Personas tabs (Resumen = today's `HeadOfSalesSummaryPage` body, Personas = `HosPeopleTable` + process health); `/dashboard/insights?tab=summary|people`.

- [ ] **Step 1: Write failing test:** manager sees `playbooks`, rep does not; language is not a tab.
- [ ] **Step 2: Run**; FAIL. **Step 3: Implement.** Move — do not rewrite — `PlaybooksSection` (label: "Playbooks e interacciones"; each type row shows its playbook status or "sin playbook · no se puntúa" for `internal`).
- [ ] **Step 4:** `node --test src/lib/settings-nav.test.ts`, `tsc` clean; Reticle as manager: Ajustes shows the tab and it lists types; Equipo shows both tabs; `/dashboard/process` redirects to the settings tab; as rep, Coaching → Playbook tab renders.
- [ ] **Step 5: Commit** `feat(settings): types and playbooks live in Ajustes; process health moves to Equipo`.

---

### Task 9: Theme control and dark mode (frontend)

**Files:**
- Create: `src/lib/theme-mode.ts` + `theme-mode.test.ts`, `src/components/ThemeProvider.tsx`
- Modify: `src/main.tsx`/`App.tsx` (mount provider; `next-themes` is already a dependency — use it with `attribute="class"`, `defaultTheme="system"`), `AvatarMenu.tsx` (Tema: Claro / Oscuro / Sistema), `src/index.css` and `src/lib/theme/materials.css` (fix contrast/hardcoded colours found in the audit), `src/lib/product-catalog.ts`

**Interfaces:**
- Produces: `type ThemeMode = "light" | "dark" | "system"`; `parseThemeMode(raw: unknown): ThemeMode` (invalid → `"system"`); storage key `vocify-theme`; all reads/writes wrapped in try/catch.

- [ ] **Step 1: Write failing tests** for `parseThemeMode` (valid values, `null`, garbage, non-string → `"system"`).
- [ ] **Step 2: Run**; FAIL. **Step 3: Implement** the provider and menu.
- [ ] **Step 4: Audit dark mode** on: Inicio (chat and home), Interacciones, Equipo, Ajustes tabs, memo detail, login. Fix hardcoded light-only colours by switching to tokens. Text contrast ≥4.5:1.
- [ ] **Step 5:** Reticle `resize_window` with `colorScheme:"dark"` and the menu toggle; screenshot Inicio, Interacciones, Ajustes in dark and report anything left unfixed.
- [ ] **Step 6: Commit** `feat(theme): light, dark and system`.

---

### Task 10: Whole-flow verification and docs

**Files:**
- Modify: `docs/features/HEAD_OF_SALES_DASHBOARD_PLAN.md` (record nav, Equipo tabs and the tag model), `docs/PENDIENTES.md`

- [ ] **Step 1:** Run `node --test src/lib/*.test.ts`, `cd backend && ~/.venvs/vocify-backend/bin/python -m pytest -q`, `npx tsc -p tsconfig.app.json --noEmit`, `npm run lint`; record failures that exist on `staging` separately from new ones.
- [ ] **Step 2:** Reticle end-to-end as rep and as manager: record/open an interaction → appears in Inicio feed with chips; filter in Interacciones; retag to Interna; ask a question from Inicio; toggle language and theme. Each with a declared `until`; report verdicts as they are.
- [ ] **Step 3:** Update the two docs; commit `docs: home, interaction types and settings`.
