# Live call assistant: one brain, look in the tabs, ask in the bar — design

Date: 2026-10-16 · Follows `2026-10-15-live-call-type-signals-design.md` (the type decides the playbook) ·
Prototype: `~/getvocify-desktop/app/island/prototype/` (local, not committed; see the last section)

## Intent (Dani, 2026-10-16)

Live help today answers objections. What reps found most useful is help that **follows the conversation**: which
playbook steps are done, what is still missing, what to ask next built from what the prospect just said, and answers
to their questions and objections. It must be **one coherent system** across the backend, the island and the dashboard,
**pull, not push** (it is ready when the rep looks, it does not grab their attention), **seamless** and clean: it must
not overwhelm the rep or pull them out of the conversation. The same assistant serves cold calls and meetings.

## The brain's principle

The brain does not ask "what did they say and what do I answer?". It asks:

> **What does this rep need to do right now to get closer to the goal of this conversation?**

It takes commercial decisions in context, not generic answers. Example: "We use Salesforce and don't want to change"
in a discovery call where the pain is not found yet. A basic copilot shows a battlecard. The brain says: don't compare
features yet; ask which process is hardest with their setup today.

For each point the brain returns a **decision** and **what to say**:

| Decision | When | Example |
|---|---|---|
| **Responder** | A direct question whose answer is in the company's knowledge | "¿Se integra con HubSpot?" → the fact |
| **Reconducir** | Answering now does not move toward the goal; a step is missing first | Salesforce, no pain yet → "¿Qué proceso os cuesta más hoy?" |
| **Aplazar** | Not needed for this call's goal, or someone else must confirm it | "Usamos un CRM propio" → note name and version; Dani validates it before the meeting (the playbook's own guidance) |
| **Cerrar** | The goal is within reach | "Vale, hablemos" → propose a day and time |

Rules:
- **The company's playbook wins.** Where an entry's guidance says what to do, the brain does that; the table above is
  the default only where the playbook says nothing (e.g. the discovery playbook says to give the price honestly, so price
  is never "Aplazar" for this company).
- The decision comes from the **call's state** (what is missing, from Conversación) and the **playbook** (steps,
  guidance, goal), never from generic sales advice. No state or playbook to justify it → no decision, only the answer.
- A direct question is never dodged: the fact in one sentence, then the question that redirects.
- "Probability" is a way of ranking, not a number shown or computed. It is measured after the fact (below).
- **Source or silence**: every suggestion comes from the playbook, the company's knowledge or the prospect's words.
  Nothing else is shown. Not in the knowledge → "No está en tu conocimiento" plus an honest line to say meanwhile.

The goal per call type exists (`GOAL_FOR_MOTION` in `playbooks/motion.py`). The discovery playbook already reasons this
way in places (competitor: "No pedir que cambien de herramienta…"; status quo: "No discutir… repreguntar con algo
medible"); the principle makes it the brain's rule instead of something each entry must spell out.

## What is true today (read from the code and the data, 2026-10-16)

- **Live help is reactive only.** The dashboard renderer runs it (`src/features/desktop/assist/useLiveAssist.ts`,
  `src/lib/live-assist.ts`): `/copilot/turn` (Jev System One, ~0.3 s: finished? objection kind?) then
  `/copilot/suggest` writes one card. The island only renders `assist` / `lastHelp` pushed by the dashboard through the
  shell (`getvocify-desktop/app/main/src/controller.ts`). One card at a time; a 6 s cooldown; `skipAnswered`.
- **"The latest" is one prospect bubble**, only its words not yet covered, cut to 280 chars (`assistContext`). In a real
  call the prospect's point spans bubbles split by the rep's "Vale" ("mándame un email" → "Vale" → "se lo reenviaré a la
  directora comercial"): today the email is lost.
- **Playbook checklist is post-call only and meetings only**: `/copilot/checklist` builds it from the memo's extraction
  (`playbook_observations` with `step_id` + `evidence_refs`); `call_mode != "meeting"` → empty.
- **Playbook shape** (`playbook_versions`): `steps` (ordered: `step_id`, `label`, `criterion`, optional literal
  `example`, max 15), `entries` (objections by category + the company's own `custom` ones with `trigger` and
  `guidance`), `qualification` (max 8: `criterion_id`, `label`, `good`). There is no FAQ entry type, no "short phrase"
  per step and no "order matters" flag. Vocify ships qualification templates (`playbooks/catalog.py`).
- **Bridge lines** are fixed empathy fillers per kind (`BRIDGES`, e.g. "Te entiendo…"); in test calls reps read them
  aloud word for word.
- **Events**: `live_assist_events` (migration 078) logs turn checks and cards. **`capture_id` is never filled**: 0 of
  2,804 events in the last 14 days carry it, so no event can be tied to a call today.
- **Speed today** (those 14 days, production path `direct:deepseek-ai/DeepSeek-V4.1-Flash`, 291 of 296 cards): turn check
  p50 316 ms / p90 487 ms (2,507 checks); card `latency_ms` p50 652 ms / p90 1,093 ms; no suggest errors.
- **Island post-call card** already has CRM / Email / Notes tabs (`PostCallCard.tsx`) and holds one call at a time.

## What two real calls showed (Toni, 15 Oct; read-only from production)

- Several points in one turn (email + decision maker) and bursts of questions (how long, founder, how many).
- Steps skipped: meetings were booked without pain or qualification; when booking, the rep did not know reps or CRM.
- The best moment for a question was a prospect's question ("¿cómo puedo mejorar?") answered with a monologue.
- A second call carried the cold-call type: opening and reason steps made no sense there.
- Reps talk 1–2 minutes straight: nothing useful can be shown live then (that is coaching).

## Design

### Two modes: look in the tabs, ask in the bar

| Piece | Owns | Never |
|---|---|---|
| **Transcripción** (tab, the default) | What was said | — |
| **Ayuda** (tab) | What the prospect said that needs handling: the points, open and "Antes", each with its outcome | Playbook progress |
| **Conversación** (tab) | Where the call is against the playbook: Ahora, Falta, Hecho | Answering anything |
| **Bar** (fixed, every tab) | Asking: **Responder · Preguntar · Resumen**, and one chip with what waits outside the open tab | Showing content itself |
| **Peek** (slides up over the open tab) | Showing what was asked for | Being a copy: it is a window onto the same object |
| **Tabs** | Navigation, with counts | Changing on their own |
| **Controls** | Recording and call: pause, stop, **Siguiente**, type, live help switch | — |

- **Nothing changes tab on its own**, not even an objection. Attention is a count on the tab and one soft pulse (the
  type tag's pulse). The rep's free will comes first.
- **Peek, one truth**: Responder's card *is* the Ayuda point (same component, same state: dismissing it there dismisses it
  everywhere). Preguntar's card *is* Conversación's "Ahora" (ticking it there ticks it in Conversación). Resumen is
  computed on request and stored nowhere. One peek at a time; a new one replaces it, the old object stays in its tab.
- **The chip** in the bar: "● N por responder ›" (taps up the newest point) or "● Falta ›" (taps up Ahora); hidden when
  what it would show is the open tab.
- Asking from the tab that owns the thing does not slide anything up: in Ayuda, Responder pulses the point in place.
- Transcript scroll stays where the rep reads while words arrive, survives switching tabs, "Latest" returns to the end
  (the island's `TranscriptScroll`); every list scrolls inside its own block with soft edge fades.
- The open recording island may grow slightly when a view needs it (the prototype used 460 px for Conversación).

### Ayuda: the point

**What Responder reads**: the call from about one minute before the tap up to the tap (both sides), with the whole call
as context; the brain decides what in there needs an answer. The automatic check reads from the previous check to now,
with a little overlap. (Today's "one bubble, 280 chars" is replaced.)

**One point per thing said** (no duplicates, no race):
- A point is identified by the stretch of the call it came from; one reading in flight per point.
- Automatic reading in flight + rep taps Responder → joins it ("Leyendo…" on the same card).
- Automatic already showed it → Responder points at it (pulse; slides it up if in another tab).
- Automatic decided "nothing" + rep taps → **the rep wins**: an answer is written anyway, past any cooldown.
- Rep tapped first, automatic finishes later → it lands in the rep's card.
- They say it again later → the same point reopens ("Lo repite"), not a new one.

**Every point ends in an outcome** (it never just fades), visible in "Antes" (header warns "N sin responder"):

| What happens | Outcome | Then |
|---|---|---|
| The rep deals with it (own words or the suggestion) | Respondido | — |
| "Te lo confirmo" | Prometido | After-call: task / follow-up email |
| The conversation moves on, nobody deals with it | Sin responder | After-call: email and notes ("preguntó X y no se respondió") |
| The prospect answers it themself or withdraws it | Ya no aplica | — |
| Not a real question or objection | Descartado (rep's X) | Logged to improve detection |

Answered partly → stays open. "Answered" means the point was dealt with, however the rep did it; the brain reads the
rep's turns after the point to decide. Points keep through a type change and while offline.

**The card has three layers, one prominent**: the tag and their words (small); **what to say** (one or two sentences,
~20 words, the only large text; its length follows what was asked: a fact, a sentence + the question back, or the
"not in your knowledge" warning + an honest line); the source only on hover. At most **two cards open**; older open ones
wait as one line, tap to open. New ones enter below; nothing moves above what the rep is reading; text is never
replaced. Points are prepared during long turns (~15 s, at a breath) and shown when the prospect finishes. A point the
rep answers before its answer is written never shows (today's `skipAnswered`).

Wording: "Aquí aparecen las respuestas a sus preguntas y objeciones." · "No encuentro una pregunta ni una objeción en el
último minuto." Never "pega". Tag a question as "Pregunta" and an objection by its kind or the playbook entry's name.

### Conversación: Ahora, Falta, Hecho

- Header: the playbook's name (follows the detected type), a thin progress bar, "N de M".
- **Ahora**: the one thing that matters most now and has something to say, with its step name small above and the line
  to say (the step's `example`, or a question for a data point). It has its own tick.
- **Falta**: one list mixing steps (circle), data to find out from the qualification (square) and the goal (flag),
  ordered by what matters now (the brain's picks first, then the steps in order, then unknown data, the goal last).
  Three visible, "+N más". Tapping the **shape ticks it by hand**; tapping the **name opens what to ask for it**.
- **Hecho**: folded; each item with the prospect's words that prove it, its value, or "Marcado por ti".
- **The rep's tick is final**: the brain never unticks or re-ticks it. Unticking something the brain ticked moves it back.
- **It draws whatever the playbook has**: ordered steps → the list above; no steps → what to find out is the list and
  Ahora is the first unknown data point; no playbook for the type → "X no tiene playbook · La ayuda solo usa tu
  conocimiento" (answers still work). Steps about how the rep talks (e.g. "Explicar Vocify en 30 segundos") stay for
  coaching and are not shown live; the brain decides that per step from its `criterion`, no list in code.
- **Type change mid-call** (the 2026-10-15 spec's "Cambia a … · Deshacer"): the new type's playbook comes in as a
  whole; its steps are read again against the call so far; what the prospect said is re-read under the new playbook's
  names (e.g. "Quién decide" → "Capacidad de decisión", marked "leído de nuevo"); open points stay; Deshacer restores
  the previous playbook and the rep's pick is final.
- **An earlier call with the contact** contributes, before the rep says hello: where they left off, what the prospect
  already said (dated, for the rep to confirm, never ticked by force) and what was promised. The island already shows
  the brief before the call (`BeforeThisCall`).

### Resumen

The other side's situation up to the tap, in their words where it matters (who they are, what they asked for, who
decides, what they agreed), 3–4 lines, then "Aún no sabes: …" from the qualification. A still picture of that moment:
tapping Resumen again closes it; tap once more to read the new moment.

### Siguiente and what is pending

- **Siguiente** (subtle icon next to Stop, tooltip "Guardar y grabar la siguiente"): saves this call and starts
  recording the next one at once; the previous call's review (CRM, email, notes) is written in the background.
- The pending count shows on the island; it opens a short list of today's calls to review, and a pick opens the same
  post-call card (CRM / Email / Notas). Full editing stays in the dashboard. The island holds one post-call card today:
  it must be able to load an earlier one.

### Organisation and settings

- The island's sections and their order: the company sets the starting point, each rep can change theirs; it lives in
  the dashboard's Settings. Hiding a section only hides it; the brain keeps reading everything (after-call needs it).
- Each rep's use of sections and asks is logged, mainly for us, and visible in Settings.

## UI specification (exact; the prototype is the source of truth)

**Where the prototype and this text differ, the prototype wins** (`~/getvocify-desktop/app/island/prototype/`:
`src/views.tsx` structure and behaviour, `src/proto.css` every value, `src/store.ts` the UI state, `src/timeline.ts` the
brain's output shape and timings, `src/frame.tsx` how a frame is fed). The numbers below were measured from the running
prototype on 2026-10-16 (island 460 wide, screen 982 high, vibrancy material). The prototype draws the real island (its
components and CSS), so everything not listed here is today's island, unchanged. In production the `proto-` class prefix
becomes `live-`; values do not change.

### Frame and vertical stack

The recording island, open: **460 px wide**, **400 px high** (today's `min(400, 50% of the screen)`); **460 px high while
Conversación is open** (the island resizes with today's 340 ms `--ease` transition). From the island's top:

| y (px) | Height | What | Notes |
|---|---|---|---|
| 0 | 32 | Top bar | Today's: recording dot, elapsed, voice wave, open arrow. Unchanged |
| 32 | 38 | Controls | `.controls`: padding 0 14, gap 6 |
| 70 | 34 | Tabs row | padding 0 12 8; track 26 high (436 wide) |
| 104 | 0.5 | Hairline | `rgba(255,255,255,0.07)` |
| 104.5 | 255.5 (315.5 in Conversación) | Views | the three tabs stacked, plus the peek |
| 360 | 40 | Bar | padding 0 12, gap 6, top border 0.5 `rgba(255,255,255,0.07)` |

### Tokens (all from `island.css`; nothing new)

Beige `#dbc09a`; warning `#f2bb5c`; text `rgba(255,255,255,0.92)`; secondary `rgba(255,255,255,0.72)`; the dim greys used
here are white at 0.55, 0.50, 0.45, 0.42, 0.35 and 0.25; boxes are white at 0.04 / 0.05 / 0.06, beige boxes are beige at
0.08 (with an inset 0.5 px beige ring at 0.24) or 0.10 (ring 0.26); `--ease` = `cubic-bezier(0.32,0.72,0,1)`. Text sizes:
9.5 (section labels, uppercase, 0.6 letter-spacing, weight 600) · 10 (chip labels) · 10.5 (tags and outcomes, 600/500) · 11
· 11.5 · 12 · 12.5 (what to say, weight 500). Radii: 12 (tabs 11, track 13), 10 (cards), 9 (inner boxes), 4 (data node).
Icons: the island's drawing rules (24-grid, round caps, stroke 2), lucide shapes, sizes 7–12.

Reused as they are: `.island` `.column` `.controls` `.circle-button` `.stop-button` `.icon-button` `TypeControl` `CopyButton`
`LiveHelpToggle` `.postcall-tabs` `.postcall-tab` `.tab-badge` `.hairline` `TranscriptScroll` `.small-action` `.group-label`
`.help-say` `.help-empty` `.help-drafting` `TypingDots` `.dim` `.lost-line` `.badge` `FloatMenu`/`MenuRow`
`.type-note-pulse` and the keyframes `turn-in`, `offer-brief-in`.

### Controls row (additions to today's)

Order: pause (28 circle) · Stop (28 high, 65.6 wide) · **Siguiente** · type tag · **pending badge** · grow · copy ·
live help switch · open Vocify.
- **Siguiente**: `.icon-button`, 24×24, margin-left −2, icon "skip-next" (triangle + bar, 11 px, stroke 2.2), secondary
  colour. Tooltip "Guardar y grabar la siguiente". Tap: this call is saved, a new recording starts at once (clock, transcript
  and state empty), the previous call's review is written in the background.
- **Pending badge**: `.badge` (18 px, beige) with the count, appears after the first Siguiente; tooltip "1 llamada por
  revisar: email, CRM y notas". Tap: a `FloatMenu` (230 wide, label "Por revisar") with one row per call ("{nombre} · {empresa}
  · hace un momento"); a row opens today's post-call card for that call.
- The type tag keeps today's behaviour, including "Cambia a {tipo} · Deshacer" for 6 s after a type change.

### Tabs

A segmented track (the post-call card's `.postcall-tabs`: padding 2, radius 13, white 0.06) with three equal tabs (22 high,
radius 11, 11.5 px weight 500, gap 5, icon 12 px at 0.9 opacity): **Transcripción** (speech bubble with two lines) ·
**Ayuda** (sparkle 10.5) · **Conversación** (list with two ticks). Active: white 0.14 and text colour; idle: secondary,
hover white 0.06.
- **Count** (`.tab-badge`: 16 high, radius 8, 10 px/600, white 0.14; on the active tab beige with dark text): Ayuda = open
  points not folding; Conversación = the brain's picks still missing that the rep has not ticked (at most 2); Transcripción
  none; hidden at 0; always 0 when live help is off. Tooltip "{Tab} · N por responder" / "N por hacer".
- **Pulse**: when a count goes **up**, one `.type-note-pulse` (900 ms, ease-out, once) behind that tab (inset −2 −3, radius
  12). A count that goes down does nothing. The tabs never change on their own.
- **Switching** keeps every pane mounted: the open one fades in over the others (opacity 160 ms ease-out, translateY 3 → 0
  in 220 ms `--ease`, hidden panes are `visibility: hidden` after 160 ms and not clickable). Each pane keeps its own scroll.

### Scroll (every list, and the transcript)

- Transcript: today's `TranscriptScroll`, untouched (glide to the latest line, lets go when the rep scrolls up, "Latest").
- Ayuda and Conversación: `FollowScroll`: scrolls inside its own block (`overflow-y: auto`, `overscroll-behavior:
  contain`), 8 px thumb (white 0.16, radius 4), a **14 px fade** at the top and/or bottom edge only while there is more in
  that direction (mask), position kept when tabs switch. Ayuda follows its end when the reader is within 80 px of it
  (exponential glide, time constant 60 ms, whole pixels, stops when the rep wheels up); Conversación never auto-scrolls.

### Ayuda

List: padding 10 14 12, gap 8, in this order from the top: **Antes**, then the open points oldest to newest.
- **Card** (a point): bg white 0.06, radius 10, padding 9 11 10, internal gap 4, selectable text. Head row (baseline, gap 6):
  tag (10.5/600 beige; "Pregunta" in text colour; "Lo repite" when they came back to it) · their words (11.5 secondary,
  one line, ellipsis) · **X** (18×18, radius 9, `margin-left: auto`, hidden until the card is hovered or focused, 120 ms;
  tooltip "No es una pregunta ni una objeción", aria "Descartar"). Body: what to say (12.5/500, line-height 1.36) and
  nothing else. With no answer in the knowledge: above it `No está en tu conocimiento` (11 px, warning, info icon 10 px) and
  the honest line below. **The source is only a tooltip on the card** (the source, or "{fuente}. Puedes decir esto mientras
  lo confirmas." when there is no answer).
- **Phases of a card**: *thinking* (`Leyendo…` + typing dots, 17 high) → *writing* (the text is appended, never replaced,
  with a 1.5×12 beige caret blinking at 900 ms `steps(2,start)`; the prototype writes 16 ms per character after a 850 ms
  think; production streams the model's real tokens) → *ready* → *closing* (the card folds: grid rows 1fr → 0fr in 380 ms
  `--ease` plus opacity 260 ms, lasting 420 ms) → it is in **Antes**. A card enters with `turn-in` (220 ms).
- **At most two cards open in full** (the newest two). Older open points are a **one-liner**: 26 high, radius 10, white
  0.04 (hover 0.08), padding 0 11, tag + words + chevron-down 7 px at the right; tooltip "Abrir"; a tap opens it in full (it
  stays open).
- **Pulse on a card** (`Responder` pointing at it): the card's own `.type-note-pulse`, for 1.2 s.
- **Antes**: collapsed by default. Toggle row: `Antes · N` (9.5/600 uppercase, white 0.45, hover secondary) and, when any
  ended unanswered, `N sin responder` in warning (not uppercase) and a chevron 7 px that turns 180°. Open: 240 ms grid-rows
  fold, rows gap 4: tag (text colour) · words (flex 1, ellipsis) · **outcome** at the right (10.5/500): Respondido beige,
  Prometido text colour, Sin responder warning, Ya no aplica and Descartado white 0.45. Row tooltip: what was answered.
- **Empty** (no points at all): centred, padding-top 26, `Aquí aparecen las respuestas a sus preguntas y objeciones.`
- **Live help off**: the whole pane shows `La ayuda en vivo está apagada en esta llamada.`

### Conversación

Body padding 10 14 14. It draws whatever the playbook has (steps, no steps, no playbook) and is keyed by playbook so a type
change enters it as a whole (`offer-brief-in`, 220 ms), not row by row.
- **Header** (15 high): playbook name (12/600) · progress bar (flex 1, max 120 wide, 3 high, radius 2, track white 0.10,
  beige fill, width animates 400 ms `--ease`) · `N de M` (11 secondary, tabular numbers; M counts steps, data and the goal).
- **Ahora** (margin-top 10): beige card (bg beige 0.08 + ring 0.24, radius 10, padding 9 11 10, gap 4). Head: `Ahora`
  (10.5/600 beige) · the step name or `Averiguar · {dato}` (11.5 secondary, ellipsis) · **tick** (18×18, beige check 8 px,
  `margin-left: auto`; tooltip "Marcar como hecho"). Body: `«{what to say}»` (12.5/500, lh 1.36). It is the first pending
  item that has something to say; it changes only when it is done, ticked, or the conversation clearly moved on.
- **Falta** (margin-top 12): label `Falta · N` (`.group-label`, padding-bottom 4); rows min-height 22, gap 9. **Node** 13 px,
  border 1.2 white 0.28: a **circle** for a step, a **rounded square** (radius 4) for data to find out, a **dashed beige
  circle with a 8 px flag** for the goal. Hover: beige border and beige 0.14 fill. Tapping the node **ticks** it (tooltip
  "Marcar como hecho"). The name (12 secondary, hover text colour) opens **what to ask** when there is something to ask
  (chevron 7 px, white 0.35, turns 180°): a box at margin 2 0 6 22, padding 6 9 7, radius 9, white 0.05, `«…»` 12 px; one
  open at a time; a name with nothing to ask is not a button (its tooltip is the step's few words and criterion, or the
  data's "good answer"). Three rows visible, then `+N más` (11 px, white 0.45, margin 3 0 0 22) / `Ver menos`.
- **Hecho** (margin-top 12): folded, same toggle as Antes (`Hecho · N`). Rows: filled beige node (13 px, no border, check
  8 px; tapping it **unticks**, tooltip "Desmarcar") · label (white 0.55) · detail at the right (11 px, white 0.45,
  ellipsis): the prospect's words that prove it, or the value and words for data, or `Marcado por ti`.
- **Order of Falta**: the brain's picks first, then steps in playbook order, then unknown data, the goal last.
- **No steps** → the data to find out is the list and Ahora is the first unknown data point. **No playbook** → one box
  (white 0.06, radius 10, padding 9 11): `{tipo} no tiene playbook` (`.lost-title`) and `La ayuda solo usa tu conocimiento.`
  (`.lost-body`); the bar's Preguntar is disabled. **Live help off** → the same empty line as Ayuda.
- **After a type change**: the new playbook's steps start unticked; data re-read under the new names keeps the prospect's
  words and the tooltip says `leído de nuevo para este tipo`.

### The bar (every tab)

40 high. Left to right: **Responder** (shield) · **Preguntar** (speech bubble with a question mark) · **Resumen** (clock with
a counter-clockwise arrow), each a `.small-action` (24 high, radius 12, padding 0 9, white 0.09, hover 0.17, 11.5/500, icon 11 px
beige, gap 5); while its card is up the button is **on** (beige 0.18, beige text); disabled at 0.4 opacity (Preguntar also when
there is no playbook; all three when live help is off). Then, pushed right, the **chip**.
- **Chip**: 24 high, radius 12, padding 0 8 0 9, beige 0.10 + ring 0.26 (hover 0.17); a 5 px beige dot · lead (11.5/600
  beige) · chevron-right 9 px. The words are its tooltip only (every waiting point's words, or the missing items' names,
  joined with ` · `). It enters with `offer-brief-in` (200 ms). Lead and rule, first match: `1 por responder` / `N por
  responder` when there are open points and the open tab is not Ayuda (tap: slide up the newest point); else `Falta` when
  something that matters is still missing and the open tab is not Conversación (tap: slide up Ahora); else hidden.
- Asking: **Responder** reads the last minute (RESPOND_WINDOW 60 s). Result: a point already up or being read → shown (pulse
  in Ayuda, slid up elsewhere); a closed one → it comes back (the rep wins); nothing → the peek says `No encuentro una
  pregunta ni una objeción en el último minuto.` **Preguntar** toggles Ahora's peek. **Resumen** toggles the recap peek (tapping
  it while it is up **closes** it; closing and tapping again reads the new moment).

### The peek

Inside the views block, bottom-anchored over the open tab: padding 0 10 8, a backdrop gradient (to top, `rgba(14,14,16,0.92)`
at 55% to transparent, 24 px taller than the card, not clickable), then the card: bg `rgba(28,28,31,0.97)`, radius 12, padding 8,
shadow `0 -8px 24px rgba(0,0,0,.35)` + inset 0.5 `rgba(255,255,255,.10)`, max-height 220 (scrolls, scrollbar hidden), a **close**
(18×18, top 9 right 9). It enters with `proto-peek-in` (260 ms `--ease`, from translateY 14 px and transparent); there is no exit
animation. One at a time: a new one replaces it. Contents, each the same piece as in its own tab (margins 0, no entrance):
- a point: the Ayuda card (its X hidden), or `✓ {tag} · {resultado}` when it is closed; `Leyendo el último minuto` + dots (900 ms)
  while Responder reopens a closed one;
- Ahora: the Conversación card; its tick keeps 22 px clear of the close;
- Resumen: the beige card with the title `Resumen · hasta el {mm:ss de la llamada}`, `Resumiendo` + dots (800 ms), then up to 4
  lines (12 px, lh 1.38, bullets 4 px beige, each line entering `turn-in` staggered 60 ms) and a last line in secondary:
  `Aún no sabes: {a, b, c…}`; `Aún no hay nada que resumir.` when empty;
- Responder with nothing: `Leyendo el último minuto` + dots (900 ms), then the line above.

### Other states

- **Offline** (the brain stopped answering): a `.lost-line` at the top of Ayuda and of Conversación, info icon in warning:
  `Sin conexión con Vocify` / `Lo que ves es de hace N s. Reintentando.`; what is on screen stays; nothing is invented.
- **Reduced motion**: no pane fade, no folds animating, no entrances, no pulses (hidden), a static caret; the island resize is
  today's 120 ms.
- **Accessibility**: tabs are `role="tab"` in a `tablist` with `aria-selected`; every icon button has `aria-label` and a tooltip;
  nodes are buttons; anything shown only on hover (sources, evidence, a step's few words) must also be reachable by click or
  focus (open item: a tap on a Hecho/Falta row's name already shows it in the row; sources need a place).

### Motion (all in one place)

| What | Duration and curve |
|---|---|
| Island resize | 340 ms `--ease` (today's) |
| Pane fade / lift | 160 ms ease-out / 220 ms `--ease` |
| Card enters | `turn-in` 220 ms `--ease` |
| Card folds away | 380 ms `--ease` + 260 ms opacity |
| Folds (Antes, Hecho, a question) | 240 ms `--ease`; chevron 200 ms |
| Peek enters | 260 ms `--ease`, 14 px |
| Count pulse / card pulse | 900 ms ease-out, once |
| Progress bar | 400 ms `--ease` |
| Node, chip, box colour changes | 160–300 ms |
| Conversación entering (type change) | 220 ms ease-out |
| Typing dots | today's 1.57 s loop |
| Caret | 900 ms steps |

### Interactions (control → effect)

| Control | Effect |
|---|---|
| Tab | Opens that pane; scroll kept; never automatic |
| Responder / Preguntar / Resumen | Slides up the peek over the open tab (in Ayuda, Responder pulses the point instead) |
| Chip | Slides up the newest waiting point / Ahora |
| Peek close | Closes the peek; the object stays in its tab |
| Card X (Ayuda) | The point ends as Descartado and moves to Antes |
| One-liner | Opens that point in full |
| Antes / Hecho / `+N más` | Fold toggles |
| Falta node / Ahora tick | Ticks it by hand (final; the brain never reverses it) |
| Hecho node | Unticks it (back to Falta) |
| Falta name | Opens or closes what to ask |
| Siguiente | Saves this call and starts the next recording |
| Pending badge | Lists the calls to review; a row opens the post-call card |

### Data each piece reads (the brain's contract with the UI)

- **Point**: `id`, `kind` (question | objection), `tag` (the kind or the playbook entry's name), `title` (their words, short),
  `answer` (null when not in the knowledge) and `fallback` (the honest line), `source`, `phase`, `outcome`, `repeated`, the
  time it was said and the turn ids it comes from, and (new, not drawn in the prototype) the decision.
- **Progress**: playbook `{key, name}`; steps `{id, label, concept (few words), criterion, example, status, quote}`; data
  `{id, label, good, value, quote, reread, question}`; the brain's `missing` picks (ordered); goal `{label, value, quote}`;
  `hasPlaybook`; offline age.
- **UI-only state** (never leaves the island/renderer): active tab, open peek, expanded/dismissed/reopened points, the rep's
  marks, which folds are open, `liveHelp`.

### States to port as fixtures (island `fixtures/index.mjs` + `npm run test:island`)

Each at 460 × 400 (Conversación 460 × 460): transcript with and without the chip; Ayuda empty, thinking, writing, two
cards, three points (one-liner), a card folding, Antes open with an unanswered point, no-knowledge card, repeated point;
Conversación (Ahora + 3 + `+N más`), `+N más` open, Hecho open, a question open, no steps, no playbook, after a type change
(tag note); the peek as point, Ahora, recap reading, recap, Responder reading, Responder with nothing, a closed point;
offline; live help off; Siguiente with the pending badge and its list; reduced motion for writing and folding. Compare
against screenshots of the prototype in the same state.

### What the prototype fakes or leaves out (not part of the spec)

- The brain's output (`timeline.ts`) is written by hand from the playbook's guidance and the call's words; the typewriter,
  the 850 ms "reading" and the recap lines stand in for the real stream.
- The sample copy quotes a real prospect (name and company): **anonymise it before the prototype is committed** and keep
  `call.local.json` out of the repository.
- `proto.css` still holds the styles of two discarded layouts (a left rail, a dock, an insights block, a numbered steps
  path, a "Resumen" button in Conversación's header): none of it is part of this spec.
- Not drawn yet: the decision line (Reconducir / Aplazar / Cerrar) on a card, the source as something clickable, the
  post-call card beyond its "writing" state, the type list, Settings.

## Backend: one brain

- **One brain means one state and one set of rules, not one model call.** Two producers, each owning its part:
  the **fast** one writes points (detect + decide + what to say), the **slow** one writes progress (steps, data, the
  "now" pick) and the recap on request. Both read the same inputs and write into the same state.
- **Latency budget**: a point's answer must not be slower than today's card (p90 ≈ 1.1 s after the reading starts);
  progress may follow 1–3 s later. Measured per reading in the events log.
- **Readings** happen at each checkpoint: end of a prospect turn;
  every ~15 s during a long turn (at a breath: the turn check already runs at every 300 ms pause); after the rep's turns
  (to close points and tick steps; nothing new shows then); and on Responder / Preguntar / Resumen. The fast turn check
  stays only to decide *when* to read.
- **Inputs**: the window above plus the whole call (head + tail as `windowOf` does), the pinned playbook version of the
  detected type (with the company's other types' answers, as `with_company_answers` does), the company's knowledge and
  product text, contact history, the current state (points, ticks, the rep's marks), today's date.
- **Outputs, separate parts, each with one producer**: points (decision + what to say + source), progress (steps and
  qualification with evidence quotes, the "now" pick), recap (only on request).
- **Concurrency**: one reading of each producer in flight; a checkpoint that arrives meanwhile is coalesced into the next
  one (latest words win), and a reading with no new words is skipped. Every reading carries the state version it read;
  a result for an older version is merged by id, never replacing newer data. Evidence only accumulates (a done step stays
  done unless the rep unticks it); the rep's marks are final.
- **Point identity**: turns are sent with ids; the brain returns, for each point, the turn ids it comes from and either
  a new point or the id of an existing one it updates (a repeat, an outcome). The open and recent points go in with their
  ids, so the brain updates instead of duplicating.
- **When a point becomes "Sin responder"**: the brain marks it once the conversation has clearly moved on (another topic
  for two prospect turns, or about 90 s); it can still turn into Respondido later; outcomes are final at the end of the
  call.
- **Ahora is stable**: it changes only when it is done, ticked, or the conversation has clearly moved to another step;
  never between two readings for no reason.
- **Speakers and language**: on calls each side is its own channel; in meetings speakers are diarized and there may be
  several people on the other side, so a point names who said it. The brain never answers the rep's own words (echo or a
  wrong speaker label); in doubt, no point. Answers are written in the call's language, whatever the island's language.
- **Same identities as after the call**: steps by `step_id`, data by `criterion_id`, done only with evidence. At the end
  the state is saved with the call; the memo checklist and coaching start from it and the post-call reading confirms or
  corrects it. A step the rep ticked by hand counts as done but is marked "marcado por el comercial" (no evidence), so
  coaching never treats it as proven.
- **Generated once per published playbook version, editable by the company**: a short phrase per step ("Di por qué le
  llamas a él") and a question per qualification item (from its `good`).
- **Shared shape** in `shared/`: the dashboard renderer holds the state and pushes it to the island, as `assist` travels
  today; the dashboard's live view (`MeetingLiveView`) renders the same pieces with more room.
- **The island's payload**: the renderer pushes the state to the island through the shell, as `assist` travels today,
  throttled and as changes. `IslandState` gains the live state; the recording view in `Island.tsx` (`Body`, recording
  case) and its open height in `geometry.ts` change (the prototype's two build-time patches mark exactly those places).
  The open height grows only to `min(460, 50% of the screen)`.

## Logging and measuring

**First, fill `capture_id`** (today it is never set): without it nothing below can be tied to a call. Then extend
`live_assist_events`: point shown / joined / reopened / dismissed and its outcome; ticks and unticks by the rep;
peeks opened (which ask); tab opened; the playbook version that served each reading. This is how we learn which decisions
help (used, and did the call reach its goal), how many readings a call costs, and tune detection. Prospect words keep
the current limits (at most 300 characters per event, 90-day purge).

## Edge cases

Several points in one turn; a burst of questions; the rep answers before the card is ready; the prospect repeats a
point; a point answered partly; a point that arrives while the rep talks; nothing detected but the rep asks; a playbook
with no steps or no playbook; the type changes mid-call; the brain is slow or offline ("Sin conexión con Vocify · Lo que
ves es de hace N s", what is on screen stays, nothing invented); live help switched off; Siguiente in the middle of a call;
a long call (window + head/tail); a second call with the same contact; reduced motion (nothing slides or pulses, it just
appears); a point that started more than a minute before Responder (the open points and the whole call are in the input,
so the brain can still reach it); several people on the other side; a wrong speaker label; a Vocify dialer call vs a
recorded meeting for Siguiente; the Mac app pointing at the staging backend while the call is processed by production
(log which backend served each reading). Anything shown only on hover (sources, evidence quotes) must also open on click.

## Knowledge the brain needs (found while designing; the sections are guidance, not a form)

- No place for "frequent prospect questions → approved answer" (entries can only be objections).
- No "who we are" facts for trust questions (since when, team, where, data/RGPD), and no product limits ("what Vocify
  does not do"), the cause of the false "Vocify no llama".
- The saved content contradicts itself (bad fit "no HubSpot" vs the entry "CRM propio no es motivo de descarte"; the
  price only inside the price objection; differentiators about another business; empty value fields). Live help repeats
  what is saved, so content quality decides whether it says true things.
- Setup stays minimal: every piece is optional and unlocks only its own part.

## Order of work

0. Fill `capture_id` in `live_assist_events` and ship it, so today's live help starts producing a baseline per call.
1. Behind a per-company flag (today's live help stays as the fallback): the brain's state shape in `shared/` and its two
   producers (points with decisions + progress), with evals in
   `backend/evals/copilot` against real calls. Gates: invented facts 0; duplicate points 0; decisions agree with the
   ones Dani labels on a set of real moments; the latency budget above.
2. Dashboard live view on the new state (easiest to test, with the demo buyer).
3. Island: tabs + bar + peek, Ayuda outcomes, Conversación Ahora / Falta / Hecho, manual ticks.
4. After-call: save the state, memo checklist and coaching from it, unanswered and promised points into email, tasks
   and notes.
5. Siguiente and reopening pending post-call cards from the island; Settings for the island's organisation.
6. Remove the bridge lines. Without them the rep has nothing to say for ~0.6–1.1 s while the answer is written; the
   tag shows at once. Decide after measuring whether reps miss them.

## Open

- An "order matters" flag per playbook (unordered topics would render as the same list without a "now" line). Proposed:
  yes, on by default.
- Where the step phrase and the data questions are edited (playbook editor), and their names there.
- The automatic window's exact overlap and the long-turn interval (15 s proposed) after measuring on real calls.
- The company's default island organisation for a new account.
- Island strings: the island is in English today; the prototype used Spanish.
- **Prototype behaviours to decide** (the prototype does them; the spec records them as is): (a) a peek stays when the rep
  switches tabs, so a point can show both in the peek and in Ayuda — proposed: switching to the tab that owns the object
  closes its peek; (b) the island grows to 460 px only while Conversación is open and animates when tabs switch — check it
  does not feel jumpy on a real screen, else keep 400 everywhere and scroll; (c) the peek has no exit animation; (d) the
  Conversación tab count is the brain's picks (at most 2), not the length of Falta.
- The decision line on a card (Reconducir / Aplazar / Cerrar): one small line above "what to say", only when it is not a plain
  answer (e.g. "Antes de comparar: falta el dolor"); not designed yet.
- Where the source of a point can be read on click (it is hover-only today).
- Siguiente during a Vocify dialer call: hang up and record the next contact, or only for recordings? And where does "the
  next contact" come from?

## Prototype

`~/getvocify-desktop/app/island/prototype/` renders the **real island** (its components, CSS and icons; two build-time
patches, no source edited) next to today's island, playing Toni's real call with Javier and the real discovery and
closing playbooks. The brain's output there is written by hand from the playbook's guidance and the call's words. The
UI specification above is written from it value by value; check a build against it by stepping the prototype and the
build through the same states (see "States to port as fixtures").
`call.local.json` holds the real transcript: never commit it. Build with
`node ~/getvocify-desktop/app/island/prototype/build.mjs`; serve with the `island-live-help-prototype` entry in
`.claude/launch.json` (port 5181).
