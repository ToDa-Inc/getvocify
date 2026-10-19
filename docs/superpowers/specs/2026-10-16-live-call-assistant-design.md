# Live call assistant: one brain, one list of what to say, the rest on request — design

Date: 2026-10-16, design revised 2026-10-19 · Follows `2026-10-15-live-call-type-signals-design.md` (the type decides the playbook) ·
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

## Design (revised 2026-10-19: replaces the tabs design)

The tabs design (Transcripción / Ayuda / Conversación, a bar to ask, a peek) was built on 2026-10-16 and tested by Dani and
his partner on a real call: "sobrecargado", the three tabs "chirrían", an answer behind a tab is an answer not seen. What
replaced it was worked out from first principles over a day of prototypes; this section is that result.

### The principle

During a call the rep looks at the screen for a second, when they do not know what to say. So the screen answers one
question on its own, **"what do I say now?"**, and everything else is there only when the rep asks for it.

| Piece | Its one job | Appears |
|---|---|---|
| **Qué decir** (top) | What to say to what the prospect just said | On its own, only when there is something to say |
| **Transcripción** (middle) | What was said | Always |
| **Responder** (bar) | "I'm stuck": answer what was said, or give the next question | When tapped |
| **Resumen** (bar) | This call: what you know, what is missing, what happened | When tapped |
| **Pasos** (bar) | The playbook's steps, ticking themselves | When tapped |
| **The contact's name** (bar) | Who they are, before this call | When tapped |

- **Nothing changes view on its own and nothing is hidden behind a tab or a counter.** What is asked for rises from the
  bottom over the transcript, one at a time, and never covers Qué decir.
- **No checklist, steps or progress on screen during the call.** The playbook works through what Qué decir suggests (its
  approved answers, its "una causa, un caso, una cifra") and through coaching after the call. Pasos is there for whoever
  wants to look. "The checklist is memory; the suggestion is judgement."
- **The playbook is a compass, not an examiner.** Vocify respects the rep's style (talking a lot, another order, time spent
  building trust, skipping what does not apply) and never corrects how they converse; it helps them use the opportunities
  that come up inside their own way of selling. No special "intervention" mode: what decides whether something shows is its
  relevance and its moment (a prospect who says "tengo cinco minutos" makes "concretad el siguiente paso" relevant), and it
  is offered, never ordered. Covering the playbook is not a measure of the rep's quality.
- **The rep configures nothing about when Vocify speaks.** No "imprescindible" flag, no end-of-call trigger (both were
  considered and rejected by Dani): when to intervene is the brain's job.

### Qué decir: one list, like a chat

- **It speaks in two cases only**:
  1. The prospect **asks something or objects** → the answer, from the playbook's approved answer or the company's
     knowledge; where it fits, a question that brings the call back to what is still missing. Not in the knowledge →
     "No está en tu conocimiento" and an honest line to say meanwhile.
  2. The prospect **says something important** (a pain, how they work today) → **one** question to go deeper, the next
     rung of the playbook's own ladder (the discovery playbook's step "Dejar hablar y profundizar": "una causa, un caso,
     una cifra"; its "Dolor con causa propia": "Añade una causa, caso o cifra suyos"), in the prospect's words.
- **A list in the order things were said, the newest at the bottom.** Several things in one turn (Javier: "mándame un
  email" … "se lo reenviaré a la directora comercial") appear one under the other, in the order said. Nothing replaces
  anything; there is no "N más".
- **Two kinds of card, told apart without headings.** An **answer** (they asked or objected) is a full card and comes
  first: it resolves an immediate need and must be fast. An **opportunity to go deeper** is quieter (no box, a thin beige
  line on the left, no tick): it is available, never a task; it never takes the place of an answer.
- **No card when the prospect already said it concretely.** "Perdemos unas ocho horas semanales" updates what Vocify knows
  (Resumen, Pasos) silently and Resumen pulses once; only a vague "perdemos muchísimo tiempo" gets a question to go deeper.
  One question per topic: three minutes on the same problem never gives five variations of it.
- **What Vocify knows, what it suggests and what the rep does are kept apart**: a suggestion the rep follows in their own
  words counts as followed (logged, to learn which suggestions help).
- **A card is two lines, always in the same order**: first the kind of help (or how it ended) and the prospect's words
  (small); then what to say (the one thing to read). One fixed map, so the rep learns it once:

  | Kind (first line) | When | Look | Ends as |
  |---|---|---|---|
  | ↩ **Respuesta** | They asked or objected and the playbook or the knowledge has the answer | Full card | ✓ Respondido |
  | ⓘ **No está en tu conocimiento** | They asked something Vocify cannot answer; the line is an honest one to say meanwhile | Full card, amber | ✓ Apuntado para el seguimiento (if the rep promised) |
  | ? **Puedes preguntar** | An opportunity to go deeper | Outlined card, lighter, no ✓ | ✓ Preguntado |
  | ? **Te falta saber** | Responder with nothing to answer | Outlined card | Closed by the rep |

  The brain's decision (Responder / Reconducir / Aplazar / Cerrar) shapes the line but is not shown (it was tried as a
  headline: jargon).
- **When a point is dealt with** (the brain sees the rep answered it, or the rep taps the ✓ that appears on hover): a light
  sweeps across the card, "✓ Respondido" pops in ("✓ Preguntado" for an opportunity the rep took, "Apuntado para el
  seguimiento" when the rep promised to confirm it), and the card fades where it is. The ✓ is never claimed without
  confidence: when the brain is not sure, the card just goes into the history when the conversation moves on. A point the conversation simply moved on from fades with no check (it goes to the
  after-call as unanswered).
- **Cards are thoughts, not notifications or tasks**: they appear, evolve (a point said again moves down as "Lo repite"),
  and lose relevance. An opportunity stays available without bothering while the rep talks about something else; when the
  rep takes it up in their own words, Vocify notices and it fades, without the rep touching anything; if the rep ignores it,
  nothing happens. **Visual memory without debt**: the "✓" shows only for a moment (~2 s) as acknowledgement; then the card
  is history like any other (faded, its kind, no mark), so the history never keeps score of what was not taken. The live
  bar shows no playbook count ("Pasos", not "Pasos 2/6"); progress lives in the Pasos list, on request.
- **While the prospect is still saying something that will need an answer**, a faint "Preparando · {tema}" line shows at
  the end of the list; the answer comes when they finish.
- **A fixed height**: one card and a glimpse of the one before. It never grows with what has been said; the transcript
  keeps its room. Older cards stay inside, above; the rep scrolls up to read them.
- **Where the list looks**: a new open point comes into view at once; an answer being written stays in view as it grows;
  when a point is dealt with, its check stays in view about a second, then the list moves to what is still open. If the rep
  scrolled up to read, the list never moves under them: a small "Nuevo ↓" appears, and a tap (or scrolling back down) takes
  them to the newest.
- **Long answers**: what appears on its own is one or two sentences (~20 words). A longer version on request is open (the
  "Más" and "Si insiste" variants were tried and rejected: too large, or playbook instructions that are not sayable).

### Responder

- Reads the last minute and answers what needs it; a point that has only just appeared is brought into view and pulses;
  one that had closed comes back (the rep wins).
- **Pressed on a card already on screen** (pointed at by an earlier press, or there for more than 5 s since it was said):
  that version did not help, so the card is **written again in place** from another angle of the same playbook entry
  (price: anchor on the hours lost before the figure; integration: ask what must not be touched; an unknown: a question
  back about what they need, never a fact). It reads "Otra forma…" with typing dots, then writes in; the kind line says
  "Respuesta · otra forma". Pressed again: the next version, cycling back to the first. Never a new card, so the list
  never fills with near-copies. Something new said since then is answered as usual instead.
- **Nothing to answer** → the next best question: the first thing the playbook says to find out that is still unknown
  ("Nada que responder · te falta saber: N.º de comerciales" + its question).
- **Tapping a prospect bubble in the transcript** = Responder about that sentence only ("Leyendo esa frase"), for when the
  prospect talked for minutes and "the last minute" is not what the rep means. The bubble a point came from carries a
  thin beige outline.

### Resumen (this call only)

- **Lo que sabes**: the playbook's qualification items found in this call, each with its value (the prospect's words on
  hover).
- **Aún no sabes**: the ones still unknown.
- **Lo que ha pasado**: a few short lines of what happened, up to the tap ("Resumen · hasta el mm:ss").

### The contact's name: the brief

- Who they are **before** this call: company, last interaction, what they said in earlier calls (dated, "de antes", for
  the rep to confirm; never counted as found in this call). Source: today's brief (HubSpot activity, earlier calls).
- First contact → it says so. No contact (some meetings, a test recording) → no button.
- CRM properties are never shown or edited live: the post-call card does that, as today.
- What this call found becomes the next call's brief.

### Pasos

- The playbook's steps in its order, each ticking itself with evidence (the prospect's words beside it) or by the rep's
  tap (final). Done steps are struck through with a line drawn left to right and the circle fills with a small pop.
- The bar's "Pasos" (no count: a live "2/6" reads as a score of the rep) pulses once when a step is done while the list is
  closed.
- **Hovering a pending item says what it still needs**, on one fixed line at the foot of the list (so hovering never
  moves anything): a step with parts lists the ones not heard yet ("Aún no sabes: visitas al día, quién decide · bastan 3
  de 5"); any other step, what it asks for. Instant and read from the playbook: nothing is generated on hover (the pointer
  crosses rows by accident during a call). With nothing hovered the line says "Toca un paso pendiente y te preparo una
  pregunta con lo que ha dicho". The steps scroll above it, so the line is in view at any height.
- **Tapping a pending item asks for help with it, right there**: the list stays open and the question appears under the
  tapped item, first "Preparando una pregunta con lo que ha dicho" (about 1 s, the measured p90 of the brain's answers),
  then it writes in. Nothing closes and nothing moves elsewhere: the answer is where the rep looked (closing the list and
  showing it in Qué decir was tried and confused). Tapping the item again closes it, another item moves it there, and
  closing Pasos clears it. The question is **generated from the call** (the last minutes, what is already known, what
  that item still needs), so it uses the prospect's own words; in the prototype it is written by hand. The playbook is not
  only something to check against: it is a natural way to ask for help, with no setup.
- A step whose criterion lists parts shows them as chips struck as they are said (Cualificar el encaje: "bastan 3 de 5
  datos"). In the prototype the parts are written by hand from the criterion; the brain must produce them.

### Controls and the bar

- **Controls row** (the island's own controls, icons with short tooltips): pause, Stop, the call type, then Siguiente
  llamada, Copiar, the live-help switch, Abrir Vocify. No "⋯" menu.
- **Bar**: Responder · Resumen · Pasos · then, at the right, the contact's name.
- **Call type**: the tag reads "Llamada · Llamada en frío". Tapped, it opens the island's own type menu: Llamada | Reunión
  first (switching keeps the menu open), then **only the types of that channel**, as the dashboard offers them (each type
  belongs to the channels its rule names; `channel_types.candidates`). Switching the channel drops a type of the other
  one: the tag says "Reunión · Tipo" until one is picked. With the catalog's default rules a call lists Llamada en frío,
  Lead inbound, Discovery, Propuesta y negociación, and a meeting lists Discovery, Demo y cierre, Propuesta y negociación;
  a company's own rules change these lists. Picking a type switches the live help to its playbook (in the prototype only
  Llamada en frío and Demo y cierre have one; other picks change the tag only). A Vocify call has a fixed channel, so its
  menu shows the types only. Proposed: the channel as an icon instead of the word.

### Where it lives: the notch island or the side

Both, the rep's choice in Settings.
- **Notch**: today's island, recording open at 460 × 400.
- **Side**: a small rounded strip near the right screen edge (40 × 104, 12 px from the edge) that says what the closed
  notch says: recording dot and time, the island's voice wave, the same dot and line when something new waits. It **never changes size
  or place**: a tap opens the panel out of it, to its left, centred on it (8 px gap, 460 wide, 460 high or less on a short
  screen); the same tap closes it and the panel shrinks back into the strip. Opening: the panel grows (340 ms, the island's
  curve), then its content fades in; closing: the content goes first. Drag the strip up or down (4 px separates a drag
  from a tap); it can only sit where the open panel fits whole, so opening never moves it; it is put back on a resize.
  **Look**: dark glass (a vertical gradient, a soft highlight at the top, a deep shadow) with a **metal rim**: a real
  CSS border of 1 px, lighter at the top, one colour for both sides. It must be a border: the browser snaps a border to
  whole screen pixels, so both sides are equal at any zoom or screen scale; a ring cut with a mask (and a gradient turning
  around the centre before it) came out thicker on one side on a fractional scale, and the turning light raced round the
  ends and crawled down the sides, which read as stutter. Two soft highlights travel along the edge itself at a **constant speed** (a CSS motion path,
  `offset-path: inset(0 round r)`, 12 s a lap), on opposite sides; brighter on hover; they stop while open. CSS only: a
  WebGL "liquid metal" shader was considered and left out, because it would keep the GPU busy for the whole call in an
  always-on-top window. Reduce motion: the highlights stand still.

### When the island is closed

No macOS notification, no opening by itself: closing it means "not now", and that is respected. The closed notch and the
side strip show one signal (no AI icon) with one meaning only: **there is something new in Qué decir that you have not
seen**. It is drawn twice at once: a solid beige **dot** where the sparkle was (7 px, one pulse when it appears) and a beige
**line around the whole closed island** (a real 1.5 px border in **warm metal**, snapped like the strip's: an even beige base and the
strip's travelling light in a warm white, a little faster: 6 s a lap on the strip, 14 s on the much longer notch so both
read at the same pace; it glows once on arrival; on the notch it fades out under the top screen edge). No animation with reduce motion; no kinds, no
"preparing" state. "Seen" means the item was live while the island (or the side panel) was open, so opening it clears the
dot and closing it again does not bring it back for the same item; the next new item lights it again. An item that ends
before the rep looks (answered, gone stale) takes the dot with it: nothing is waiting any more.
Opening the island shows the list as it is. A short text
"peek" while closed is left as a possible setting, off by default, only if reps miss answers (to be measured); before any
text appears unasked, check that the island window is not captured when the rep shares their screen.

### Siguiente and what is pending

Unchanged from the 2026-10-16 design: Siguiente saves this call and starts the next recording; the pending count opens
today's calls to review in the post-call card.

## UI specification (from the prototype, 2026-10-19)

The prototype draws the real island (its controls, transcript, glass, icons); values below are its CSS. Tokens: those of
`island.css` (beige `#dbc09a`, warning `#f2bb5c`, text white 0.92, secondary 0.72, `--ease` `cubic-bezier(0.32,0.72,0,1)`).

| Piece | Values |
|---|---|
| Qué decir zone | fixed 100 px high (padding 6 0), list padding 0 14, gap 6, own scroll (8 px thumb, 14 px edge fades) |
| Card | bg white 0.06, radius 10, padding 7 11 8, gap 2; words 11.5 secondary, one line, ellipsis; say 12 / 500, lh 1.36 |
| Card dealt with | opacity 0.36, bg 0.03, say clamped to 2 lines; fade 420 ms after a 650 ms delay (none when unanswered); sweep 700 ms; check pop 460 ms |
| Preparando | 11.5, beige 0.75, breathing 1.6 s |
| Transcript | today's `TranscriptScroll`; the source bubble of a point: inset 1 px beige 0.5 ring; prospect bubbles hoverable |
| Bar | 40 high; `.small-action` buttons (24 high, radius 12); contact chip max 130 wide, person icon beige, chevron |
| Peek (Resumen, contact, Pasos) | bottom-anchored over the transcript only, card `rgba(28,28,31,0.97)`, radius 12, close at top right |
| Side strip / panel | strip 40 × 104, radius 20, `rgb(24,24,27)`; panel radius 22; open/close as above |
| Reduced motion | no sweep, no pops, no breathing, no fades; instant scroll |

**Gotcha found building it**: `island.css` presses every button with `transform: scale(0.93)`. A button positioned with
a `transform: translate…` loses its translate while pressed and jumps; position buttons with top/left.

### What the prototype fakes

The brain's output for the two recordings is written by hand from the playbook's entries and steps: the answers, the
"profundiza" questions, the step parts, the Resumen lines, which points end answered. The real brain produces none of it
yet in this shape.

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
  The open height grows only to `min(460, 50% of the screen)`. (Written for the tabs design: the 2026-10-19 view replaces the
  recording view's tabs with Qué decir + transcript + bar; the island stays 400 high.)

### What the 2026-10-19 design asks of the brain (new)

- **One reply per prospect turn.** The points of one turn come back together, in the order said, each with a short
  `answer` (one or two sentences, ~20 words, capped in code as well as in the prompt). Today each point is written alone.
- **"Something important" is a trigger**, not only questions and objections: a statement on a topic the playbook cares
  about (a pain, how they work today) gets one question to go deeper, the next rung of the playbook's own ladder, in the
  prospect's words. Never when the rep is already following up, never on every sentence, one at a time. It needs its own
  reading of how far each thread has gone (cause, case, figure). **The main risk is noise**: measure on real calls first.
- **Dealt with, reliably.** The point's outcome (answered, promised, moved on) drives the "✓ Respondido" moment; it must be
  measured against labelled moments before the UI leans on it.
- **Parts of a step.** Where a step's criterion lists parts ("al menos tres de estos datos: …"), the brain returns them and
  which are covered (generated once per published version, like the short phrase per step).
- **The next best question** for Responder with nothing to answer: the missing item that matters most for the call's goal
  (the prototype takes the playbook's order).
- **Rules in natural language** in the playbook ("no pases a la demo sin entender el problema") are followed as guidance;
  to be checked in evals.
- **The brief and this call's facts**: what a call finds is stored so the next call's brief can show it as "de antes".
- The decision (Responder / Reconducir / Aplazar / Cerrar) stays in the data and shapes the line; it is not shown.

## Logging and measuring

**First, fill `capture_id`** (today it is never set): without it nothing below can be tied to a call. Then extend
`live_assist_events`: point shown / joined / reopened / dismissed and its outcome; ticks and unticks by the rep;
Responder, Resumen, Pasos and the contact opened, bubbles tapped, points ticked by the rep; the playbook version that served each reading. This is how we learn which decisions
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

Done (2026-10-16): `capture_id` filled in the events; the brain's state and its two producers behind `LIVE_BRAIN_ENABLED`
(now on for everyone); the dashboard's live view on it; the island's tabs view (`getvocify-desktop` e95af9e), now replaced
by the design above.

Next, the backend first, each piece with its eval on real calls (`backend/evals/copilot`):
1. **One reply per prospect turn**, short, in the order said; caps in code.
2. **Go deeper on something important** (the new trigger and the thread's depth). Gate: it does not fire on ordinary
   sentences (measured), one at a time.
3. **Dealt with**: outcome accuracy against labelled moments (Dani labels; today's 18 labels were proposed by Claude and
   are unconfirmed).
4. **Parts of a step** and **the next best question**.
5. **Natural-language rules** in the playbook, in the evals.
Then the island: Qué decir as a list, Responder / Resumen / Pasos / the contact in the bar, the side strip, behind the
flag; tested by Toni on real calls with what is shown, used and dismissed logged. Then the after-call (unanswered and
promised points into email, tasks and notes) and Siguiente.

**Built 2026-10-20** (wire: `2026-10-20-live-say-view-build-contract.md`):
- Desktop (`getvocify-desktop` main): the Qué decir view, shown when the dashboard pushes `liveBrain.view = "say"`
  (7e97088); the closed-island marker (d5540dd); the side placement with its tray choice and `vocifyDesktop.island`
  bridge (82ac939). Fixtures and click tests for every state (`npm run test:island`, 233 checks), logic and shell tests
  green. Not yet run on a real call: it needs the dashboard piece (the flag and the new payload) and a desktop build.
- Backend (deepen, rewrite, ask_step, next, parts, `/live/events`) and dashboard (flag `LIVE_SAY_VIEW_ENABLED`, payload,
  actions, contact brief, placement setting): proposed as their own sessions, against the contract.
- Until the backend pieces exist the island degrades on its own: Responder past the last version goes back to the
  first after 8 s; a Pasos question falls back to the playbook's own question after 4 s; with nothing to answer, the
  playbook's next item.

## Open

- The long version of an answer, on request: how it looks and what it says (two attempts rejected).
- The call-type selector: channel as an icon + Llamada | Reunión then the types (proposed).
- Whether reps miss the decision headline or the bridge lines (measure after building).
- Where the step parts and the next-best-question are edited in the playbook editor.
- The company's default (notch or side) for a new account.
- Island strings: the island is in English today; the prototype is in Spanish.
- Siguiente during a Vocify dialer call (unchanged open item).

## Prototype

`~/getvocify-desktop/app/island/prototype/` (local, not committed). The page shows only this design: the notch island and
the side strip, a switch between two recordings and a "Qué mirar" list that plays each moment. Build with
`node ~/getvocify-desktop/app/island/prototype/build.mjs`; serve with the `island-live-help-prototype` entry in
`.claude/launch.json` (port 5181). Files: `src/say.tsx` (the view), `src/feed.tsx` (Qué decir), `src/side.tsx` (the side
strip), `src/timeline.ts` (the recordings and the hand-written brain), `src/zones.tsx` and `src/slot.tsx` (transcript marks
and taps, Pasos, Responder). Recording 1: Toni's real call with Javier (`call.local.json`); recording 2 (`?call=2`): an
internal test recording from the evals (`call2.local.json`, evals 512ea713 turns 37–61), the only one with something to dig
into. **Both hold real speech: never commit them.** Earlier variants (tabs, one slot, fixed zones, hybrid) remain in the
code under `?option=` but are off the page.
