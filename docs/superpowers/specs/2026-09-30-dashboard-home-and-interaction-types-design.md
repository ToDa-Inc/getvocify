# Dashboard home, interaction types and settings — design

Date: 2026-09-30 · Branch: `feat/home-dashboard` (worktree `~/getvocify-home`, from `staging`)

## Intent (Dani, 2026-09-30)

The staging dashboard shows team KPIs, playbooks and a top-bar Ask, but is not interactive and
does not serve the product's four objectives: **Capture, Automate, Assist, Coach**. Reps and the
Head of Sales both hit friction. Goal: one home that answers "what should I look at or do next to
move the number?", with recorded interactions visible and organised by type, Ask as a real chat
in the main panel, Today condensed on the side, and Settings reorganised.

## Decisions (answered by Dani)

- D1. One home for both roles; content scoped by role.
- D2. Two tags per interaction: **Channel** (fixed: call, meeting, visit, voice note; auto) and
  **Type** (the company's own list, from the existing `interaction_types`/playbooks: Discovery,
  Demo, Closing, Interna…). A type with no playbook is never scored.
- D3. "Interna" is detected by AI (no customer present) and retaggable in one click.
- D4. Head of Sales side column = team signals only (max 3). Own Hoy, calls-to-review and a KPI
  strip are out of scope.
- D5. Types and playbooks are configured in Settings (Proceso de venta leaves the sidebar).
- D6. Language and theme move to the avatar menu; real dark mode.
- D7. Chat: the home is the chat. Composer centred on Inicio, thread takes over the main column
  on send, top-bar Ask pill removed. The floating sheet stays for ⌘K and "Ask about this".

## Rulings (mine; Dani can undo)

- R1. **Type storage = existing `memos.sales_motion_key`.** No new column. `internal` is a
  reserved key: no playbook, never scored, never proposed to the CRM. Cost if wrong: a later
  migration to split "type" from "playbook pin".
- R2. **Type labels come from `GET /playbooks`** (already returns each type with its label). No
  new types endpoint.
- R3. **No backfill.** Memos without a `sales_motion_key` show the channel chip only.
- R4. **Voice-note fix:** the web recorder sends `interaction_kind=voice_note` to
  `/memos/upload`; the extension keeps today's `call`. Cost if wrong: extension voice memos stay
  "call".
- R5. **Manager KPI tiles move to Equipo → Resumen**; ProcessHealth and ObjectionBreakdown move
  to Equipo too, since Proceso de venta disappears. Cost if wrong: moving them back.
- R6. **Rep's Playbook page becomes a tab of Coaching.**
- R7. **Team signals** are built client-side from `GET /team/adherence` with the existing
  `summaryDiagnosis` rules plus a per-rep adherence-drop rule. No AI-written signals.
- R8. **Dark mode** ships last (own task); the `.dark` variables already exist.
- R9. **Dark mode is dashboard-only, with a custom `DashboardThemeProvider`, not next-themes.**
  next-themes is built for the app root and never removes its class on unmount, and its anti-FOUC
  script does not run in this client-only SPA. The provider wraps `/dashboard`, stores the choice
  under `vocify-theme` (light, dark, system; garbage or blocked storage gives system) and removes
  `.dark` on leaving. Login, marketing and auth pages stay light. `next-themes` is now an unused dependency.

## Design

### Navigation
- Manager: Inicio · Interacciones · Equipo · Ajustes.
- Rep: Inicio · Interacciones · Coaching · Ajustes.
- Top bar: Llamar (reps who can dial) and avatar menu (Perfil, Idioma, Tema, Cerrar sesión). No Ask pill.
- Old routes keep working via redirects: `/dashboard/memos`→`/dashboard/interactions`,
  `/dashboard/process`→`/dashboard/settings/playbooks`, `/dashboard/playbook`→`/dashboard/coach?tab=playbook`.
  `/dashboard/today` (full RepHome) stays as is.

### Inicio (`/dashboard`)
Main column: greeting, composer (voice + text), ≤3 suggestion chips from `GET /ask/suggestions`,
then "Últimas interacciones" (8 rows, channel filter). Right rail 320px:
rep → condensed Hoy (today's meetings ≤3 with brief, count rows Falta tu OK / Tareas /
Seguimiento / Nuevos → `/dashboard/today`); manager → ≤3 team signals (click prefills a question).
Sending a question: composer moves to the bottom, thread fills the main column (200ms
transform, respects `prefers-reduced-motion`), URL `?c=<id>`; Esc / "Nuevo" returns.

### Interacciones (`/dashboard/interactions`)
Replaces MemosPage. Rows: channel chip, type chip (or none), title, person→contact, duration,
status, age. Filters: channel, type, author (manager). Server pagination, page size 20.
Type chip is a menu: retag to any active type or "Interna" (one click).

### Ajustes
Tabs: CRM · Llamadas · Oferta · Glosario · Resúmenes · Equipo · Playbooks e interacciones
(types list with playbook status, rule, pause/delete — the current PlaybooksSection) · Uso ·
Facturación. Language/theme controls leave the settings side nav.

### Backend
- `GET /memos` gains `interaction_kind` and `sales_motion_key` filters; `Memo` gains `salesMotionKey`.
- `/memos/upload` accepts optional `interaction_kind`; `voice_note` is stored.
- `internal` type: extraction reports `customerPresent`; false → `sales_motion_key='internal'`
  unless the pin source is `manual`; scoring and CRM proposals skip `internal`.
- Retag reuses `POST /memos/{id}/playbook` (accepts `internal`).

### Density map
Surface: composer, ≤3 chips, 8 interactions, ≤3 meetings/signals. Hover: full title, signal
evidence. One click: `/today`, memo detail, Equipo. Never on Inicio: KPI tiles, charts.

### States and volume
New account: composer only, no invented suggestions, one line "Graba tu primera llamada". Nothing
due: "Todo al día". Feed capped at 8 on Inicio at any volume; Interacciones paginates (0, 12, 80,
400 rows). No page scroll on Inicio; only the thread scrolls.

## Shipped differently from the design above
- Signal click prefills the composer without sending, so the manager can edit the question.
- The rep rail is hidden for reps whose company has the rep workspace off (its reads are gated and would 404). Managers keep the signals rail.
- The retag menu offers only published types plus Interna, since a draft or paused type cannot score.
- The adherence-drop rule uses `/team/adherence/trend` (last 4 weeks against the 4 before, adherence as summed met over summed applicable steps), because `/team/adherence` has no per-rep previous period.
- Rail meetings and counts link to `/dashboard/today`; Inicio's Esc/"Nuevo" leaves a home question and every home question starts a new conversation.

## Out of scope
Calls-to-review, KPI strip, manager's own Hoy, memo-type backfill, calendar-attendee detection,
new capture sources.
