# Live call assistant, "Qué decir" view: build contract — 2026-10-20

The design is `2026-10-16-live-call-assistant-design.md` (revised 2026-10-19). This file fixes the wire between the
three pieces so they can be built at the same time:

- **Backend** (`backend/`, lands on `staging`): the brain's new outputs and one events endpoint.
- **Dashboard** (`src/`, `shared/live-call/`, lands on `staging`): state, the island payload, the island's actions, the
  flag, the contact brief, the placement setting UI, event logging.
- **Desktop** (`~/getvocify-desktop/app`, lands on its `main`): the new recording view, the closed-island marker, the side
  strip, the placement setting.

Everything here is additive: the tabs view keeps working until the flag is on for a company.

## 1. The flag

`LIVE_SAY_VIEW_ENABLED` (company feature flag, in `CLIENT_FLAGS`, default **off**; on for Vocify's own company to test).
On: the dashboard pushes `liveBrain.view = "say"` and the island draws the new view; off: `view` is absent or `"tabs"`
and the island draws today's tabs. The backend outputs below are produced whatever the flag (they are cheap and only
read when asked), except the "go deeper" trigger, which is behind the same flag so it can be measured first.

## 2. Backend (`/api/v1/copilot`, all behind `LIVE_BRAIN_ENABLED`)

### 2.1 `LiveReading` additions (`live_models.py`)

- `reason` gains `"rewrite"` and `"ask_step"`.
- `target`: `{ point_id?: str, kind?: "step" | "data", id?: str, version?: int } | None`.
  - `rewrite`: `point_id` (an existing point) and `version` (how many versions the rep has seen, 1 = only the first).
  - `ask_step`: `kind` + `id` (a pending step or data item).
- `say_view: bool` (the flag, sent by the dashboard): enables the "go deeper" trigger.

### 2.2 `POST /live/points` result additions (SSE `result` event)

- **Go deeper** (`say_view` only): a point may have `kind: "deepen"`. Fields as any point; `answer` is the one question to
  go deeper (≤ 20 words, the playbook's ladder "una causa, un caso, una cifra", in the prospect's words), `source` the
  step it serves (`{id: step_id, label}`), `decision: null`. One open deepen point at a time; never when the rep is
  already following up; never on a statement that already gave the figure (that updates progress instead). Closed as
  `answered` when the rep asks it in their own words (the "✓ Preguntado" moment).
- **Responder with nothing** (`reason: "responder"`, no new point): `next: { kind: "step" | "data", id, label,
  question } | null` — the missing item that matters most for the call's goal, its question in the call's words.
- **Rewrite** (`reason: "rewrite"`): no new points; `rewrite: { point_id, version, answer }` — the same point answered
  from another angle of the **same source** (a playbook entry or knowledge item), never a new fact; for an unknown
  point, a question back about what they need. ≤ 20 words. `rewrite: null` when there is no other honest angle.
- **Question for a step** (`reason: "ask_step"`): `step_question: { kind, id, question } | null` — one question for that
  pending item, from the last minutes of the call, what is already known and what the item still needs (its first
  missing part for a step with parts), in the prospect's words. Latency target: p90 ≤ 1.1 s like points.
- Every point carries `turn_ids` (already in the model output; keep it in the result) so the island can outline the
  bubble it came from.

### 2.3 `POST /live/progress` result additions

- `steps[].parts`: `[{ id, label, done, quote }]` and `steps[].need: int` for a step whose criterion lists parts ("al
  menos tres de estos datos: …"); absent otherwise. The parts list is generated once per published playbook version
  (with the aids); `done` needs evidence like data. A step with parts is done when `need` parts are done.

### 2.4 `POST /live/events` (new)

Body `{ call_id, events: [{ kind, at, point_id?, step_kind?, step_id?, detail? }] }`, max 50 per request, written to
`live_assist_events` with `kind = "ui"` and the event in `detail` (`detail.event = kind`). Kinds: `shown`, `dismissed`,
`reopened`, `rewrite`, `ask_step`, `tick`, `untick`, `responder`, `bubble`, `open_recap`, `open_steps`, `open_brief`,
`marker_shown`, `marker_seen`. A migration widens the `kind` check to include `ui`. 204 on success; never blocks the call.

## 3. Shared state (`shared/live-call/state.js`)

- `LivePoint.kind` adds `"deepen"`; `LivePoint.turn_ids: string[]`.
- `LivePoint.versions: string[]` — `[first answer or fallback, ...rewrites]`; `applyRewrite(state, rewrite)` appends.
  The shown version is the island's choice (it cycles), not stored in state.
- `progress.parts: { [step_id]: { [part_id]: { quote, by? } } }` (only accumulates; the rep's marks are final).
- `LiveStep.parts?: {id,label,done,quote}[]`, `LiveStep.need?: number` (merged like data: done only accumulates).
- `asks.step: { seq, kind, id, status: "reading" | "ready", question: string | null } | null`.
- `asks.rewrite: { seq, point_id, status: "reading" | "ready" | "none" } | null`.
- `asks.responder` adds `next: { kind, id, label, question } | null`.

## 4. Island payload (`shell.setState({ liveBrain })`, snake_case on the wire as today)

Exact wire, additions to `liveBrainPayload` (everything else unchanged):

```jsonc
{
  "view": "say",                                  // "say" | "tabs"; absent = "tabs"
  "state": {
    "points": [{
      "kind": "deepen",                           // also "question" | "objection" as today
      "turn_ids": ["t12", "t13"],                 // same ids as the overlay's turns
      "versions": ["first answer", "rewrite 1"]   // [answer ?? fallback, ...rewrites]; [] while thinking
    }],
    "progress": {
      "parts": { "<step_id>": { "<part_id>": { "quote": "…" } } }   // parts heard, with evidence; rep marks: by:"rep"
    }
  },
  "playbook": {
    "steps": [{ "parts": [{ "id": "crm_que_usan", "label": "CRM" }], "need": 3 }]   // only steps whose criterion lists parts
  },
  "asks": {
    "responder": { "seq": 4, "status": "nothing", "point_id": null,
                   "next": { "kind": "data", "id": "volumen", "label": "Visitas al día", "question": "¿…?" } },
    "step":      { "seq": 2, "kind": "step", "id": "cualificar_el_encaje", "status": "reading" | "ready", "question": "¿…?" | null },
    "rewrite":   { "seq": 3, "point_id": "pt-1a2b", "status": "reading" | "ready" | "none" }
  },
  "contact": { "name": "Marta Ruiz", "company": "Distribuciones Norte", "first": false, "lines": ["…", "…"] }  // or null
}
```

- `contact` is who they are **before** this call (HubSpot activity and earlier calls via `GET /contacts/{id}/recent-activity`,
  or the brief already shown before the call, `islandBrief`); `first: true` when there is no earlier interaction; `null`
  when there is no contact. Only what really exists: never a made-up line.
- `asks.rewrite.status: "none"`: the brain had no other honest angle; the island keeps cycling the versions it has.
- Overlay turn ids and `turn_ids` must come from the same source (the meeting view's turn ids).

## 5. Island actions (`livebrain:action`, island → dashboard)

Existing: `responder`, `preguntar`, `resumen`, `tick`, `untick`, `dismiss`. New:

- `{ type: "rewrite", id, version }` — `version` = how many versions the island already has. The island shows the next
  version itself when `versions` has it (cycling back to the first after the last); it sends `rewrite` only when it
  needs one that does not exist yet, and shows "Otra forma…" until `versions` grows or `asks.rewrite` says `none`.
- `{ type: "ask_step", kind, id }` — Pasos tap.
- `{ type: "responder_turn", turn_id }` — Responder about one tapped bubble (`focus_from` = that turn, the reading only
  that sentence).
- `{ type: "event", kind, ... }` — UI events to log (§2.4); the dashboard batches them to `/live/events`.

## 6. Placement (desktop setting)

`islandPlacement: "notch" | "side"` in the desktop's `settings.json`, default `"notch"`. Bridge ops `island:get` /
`island:setPlacement` exposed in `dashboard-preload.ts` as `vocifyDesktop.island.{get, setPlacement}`; the dashboard's
`IslandSettings.tsx` gets a "Dónde aparece: Arriba (notch) | Al lado" row. Also a tray submenu next to "Show island on".
Side: the island window becomes the strip + panel described in the design; drag position saved as
`islandSideOffset` (fraction of the screen height).

## 7. Not in this build

- Dealt-with accuracy against labelled moments: needs Dani's labels (the 18 proposed are unconfirmed).
- Natural-language rules in evals (order of work 5).
- The after-call (unanswered and promised points into email, tasks and notes) and Siguiente.
- `setContentProtection`: only needed before any text appears unasked while closed (not in this design).
