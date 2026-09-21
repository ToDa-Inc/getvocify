# Copilot Spine — UX-first Engineering Design

**Date**: 2026-09-21
**Author**: Dani Zal & Senior AI Assistant
**Status**: Draft for review — slices 0–1 are planned in `docs/superpowers/plans/2026-09-21-copilot-spine-foundation-and-followup.md`

---

## 1. Overview & Objectives

What each surface does and how it looks is settled in `docs/features/PLAN_INTEGRACION.md`; the experience is in `docs/EXPERIENCIA_PRODUCTO.md`; the data model is in `docs/features/ESTRUCTURA_INTELIGENTE.md`. This document is the code-level design: module boundaries, contracts, state machines, algorithms and budgets.

Every decision below serves four promises to the rep:

1. **Never wait for work we could have done earlier.**
2. **Never lose what they typed.**
3. **Never see the same nudge twice.**
4. **Read the same sentence on every surface.**

All code in this document and in the slice 0–1 plan was run on 2026-09-21 in a scratch copy that mirrors the repo paths: 29 JS tests (`node --test`) and 29 Python tests (`unittest`), all green. None of it is in the repo yet.

---

## 2. Six UX superpowers — and what each one forces in code

### 2.1 Work arrives before you do (latency hiding)
- **Follow-up draft** starts when extraction completes, in the background — not when the review opens (§4.2).
- **Queue mode** prefetches the next contact's brief while the rep is still on the current one (`prefetchTarget`, §6.1).
- **Hoy** paints from the last cached payload instantly and revalidates behind it: `chrome.storage.session` in the extension, `localStorage` in the desktop, React Query in the web.
- **Measure**: first paint of Hoy from cache ≤ 100 ms; share of reviews where the draft is `ready` at first paint (target set after two weeks of data, not guessed).

### 2.2 Undo, never confirm
- *Posponer*, *Ya no aplica* and every hand-off apply immediately, with a 5 s undo toast. No modal on the rep's path.
- Consequence: every write endpoint is idempotent and keyed (signals by `dedupe_key`, drafts by memo), so undo is a PATCH back to the previous state inside the window.

### 2.3 Nothing jumps
- Loading states share the final component's box: `.v-followup` reserves its ready footprint (`min-height`) from the first paint, and the skeleton sits inside the real card, not in a placeholder of a different size.
- Height changes (pill second row, a card leaving Hoy) animate measured heights; `prefers-reduced-motion` gets opacity only.

### 2.4 Keyboard first in the queue
- One map for every surface (`QUEUE_KEYS`): `Enter` call · `S` skip · `N` next after review · `Esc` exit · `⌘/Ctrl+Enter` send the follow-up.
- On every step focus moves to the primary action, and a polite live region announces *"2 de 7 · Marina Ortiz"*.

### 2.5 Quiet by contract
- The server only marks a suggestion `grounded` when it comes from the team's playbook or proven patterns (§6.2); the client shows nothing else.
- The client reducer (`pillReducer`) holds a line ≥ 4 s so it can be read, hides it at 10 s or when the rep starts answering, and never repeats a category within 60 s.
- The live region is `polite`, never `assertive`, because the rep is mid-conversation.

### 2.6 One sentence, one place
- Reasons and due labels are written on the server by deterministic templates (§5.3), never assembled in a client and never produced by the LLM.
- Chrome strings for shared components live in `shared/ui/i18n.js`. Components never compose content; they render what they receive.

---

## 3. Architecture

### 3.1 Module map

```
shared/
  tokens/tokens.json          single source: colors, radii
  ui/html.js                  escaping template — the only way markup is built
  ui/v-element.js             light-DOM base: .data in, one 'v-action' event out
  ui/i18n.js                  chrome strings for shared components (es, en)
  ui/compose.js               where "Enviar" goes: mailto / Gmail / Outlook / wa.me (pure)
  ui/queue.js, ui/pill.js     interaction state machines (pure) — slices 2 and 5
  ui/components/<name>.js     pure render(view, lang) → markup
  ui/components/v-<name>.js   custom element (browser only), thin shell over the render
  ui/vocify-ui.css            component styles, --v-* tokens only
scripts/build-tokens.mjs      tokens.json → one CSS file per surface (+ --check for CI)
scripts/sync-shared.mjs       copies shared/ui into extension and desktop (+ --check)
```

Rule: everything with logic is a pure module with tests in `node --test`; custom elements are thin shells that do not need a DOM test.

### 3.2 Why light-DOM custom elements

| Option | Why not |
|---|---|
| Rewrite extension and desktop in React | `popup.js` is 160 KB of working vanilla code; weeks of risk for zero user value |
| Embed the web app (iframe/webview) in extension and desktop | Two auth models, CSP, latency, offline, and the side panel's width constraints fighting a desktop layout |
| Compile shared React to vanilla | Adds a bundler to the extension and desktop builds, which have none today |
| **Custom elements, light DOM** | Native in all three runtimes, no build step, tokens and CSS apply directly, and the render is a pure function we can test in Node |

Light DOM rather than shadow DOM: the shared stylesheet and the surface's tokens must reach inside, and Tailwind never touches `v-` classes.

### 3.3 The element contract

- **Data in**: `el.data = view` (a property, never attributes). The view is exactly what the server returns.
- **Intent out**: one bubbling `v-action` event with `{action, value, element}`.
- **Hosts own effects.** Elements never fetch and never navigate. Auth differs per surface (extension `api` in `lib/api.js`, desktop `request()` through the main process, web `api-client`), and so do navigation and the clipboard:
  - Extension: `chrome.tabs.create`. A `mailto:` goes through `location.href`, because a new tab would stay blank.
  - Desktop: `vocifyDesktop.shell.openExternal`.
  - Web: `window.open`, or `location.href` for `mailto:`.
- **Edits are sacred.** `VElement.shouldRepaint(prev, next)` lets a component refuse background repaints. While the rep is editing, `v-followup` repaints only when the server says something new: another status (for example `sent`) or another draft. Comparing status alone would leave memo A's edited draft on screen for memo B, because the desktop and the web reuse the element. The rule is a pure function (`followupNeedsRepaint`) with its own test.
- **Escaping is structural.** Transcripts are user-controlled text, so markup is only ever built with `html\`\``, which escapes every interpolation. There is no other path to `innerHTML`.

### 3.4 React 18 bridge

```ts
// src/hooks/use-v-element.ts
import { useEffect, useState } from "react";

export type VAction = { action: string; value: string | null; element: HTMLElement };

/** Shared custom element in React: data in as a property, v-action out as a callback.
 *  Returns a callback ref. The element is held in state, not in useRef, so both effects
 *  re-run when it mounts: a component that renders null until its data arrives would
 *  otherwise never attach the listener. */
export function useVElement<T>(data: T, onAction?: (detail: VAction) => void) {
  const [element, setElement] = useState<HTMLElement | null>(null);

  useEffect(() => {
    if (element) (element as HTMLElement & { data?: T }).data = data;
  }, [element, data]);

  useEffect(() => {
    if (!element || !onAction) return;
    const handler = (event: Event) => onAction((event as CustomEvent<VAction>).detail);
    element.addEventListener("v-action", handler);
    return () => element.removeEventListener("v-action", handler);
  }, [element, onAction]);

  return setElement;
}
```

If this bridge ever causes friction, the web can reimplement a component in React against the same `vocify-ui.css` classes. That keeps the visual contract and gives up only the single implementation.

### 3.5 Tokens: one source, two layers per surface

Every generated file carries:

1. **The surface's legacy names, in its own format** — triplets for web and desktop (`hsl(var(--beige))`, what shadcn expects), full colors for the extension (`var(--beige)`, what its 53 KB `styles.css` already uses). This is why no stylesheet needs rewriting.
2. **The shared `--v-*` namespace** (full colors), the only thing `vocify-ui.css` reads.

The layers matter because the names collide in meaning: web `--muted` is a surface color, extension `--muted` is a text color. The shared kit depending on `--v-*` avoids inheriting that ambiguity.

Canonical values follow `PLAN_INTEGRACION.md` §2.3: they change only where accessibility requires it (muted text `30 6% 42%` at 4.86:1 on cream; success `#346538` at 6.85:1 on white). Motion is not tokenized yet: the desktop uses a shorthand with its own easing, and unifying it is a separate change.

### 3.6 Where the desktop lives

`Makefile` already runs `cd desktop && node --test lib/*.test.js` — the monorepo was the intended layout. Slice 0 moves the Electron app into `desktop/` with history (plan Task 1). Until then, both scripts accept `VOCIFY_DESKTOP_DIR=../getvocify-desktop`.

---

## 4. Follow-up engine (slice 1)

### 4.1 Lifecycle

```
(none) ──extraction done──▶ generating ──draft ok──▶ ready ──Enviar──▶ sent
                                │                      └──Copiar──▶ ready (+copied_at)
                                ├──LLM error / empty──▶ unavailable
                                └──stale > 2 min──▶ reclaimed by the next attempt
```

`ready`, `sent` and `unavailable` are final: a draft is never regenerated behind the rep's back.

### 4.2 Trigger — and a correction to `PLAN_INTEGRACION.md` §3.4

Three code paths complete an extraction today:

1. `api/memos.py:291` (pipeline)
2. `api/memos.py:1999` (re-extract)
3. `services/whatsapp/processor.py:2193` (voice note insert)

`services/telephony/call_processor.py:328` also writes `pending_review`, but it is the voicemail / no-conversation path, which skips extraction. It gets no draft by design (`is_eligible` excludes `voicemail` and `no_response`), and the SDR queue skips straight to the next contact (§6.1).

`PLAN_INTEGRACION.md` said to generate the draft before flipping the memo to `pending_review`. With three writers, that means changing status semantics in three places and delaying every review, including the ones where nobody sends an email. Decision:

- The status flips exactly as today.
- `schedule_followup(supabase, memo_id)` fires right after each of the three writes. It follows the pattern of the existing `schedule_transcript_polish`, which already runs at two of those three points.
- The card reserves its space and shows *"Escribiendo el seguimiento…"* for the few seconds it takes.
- `GET /api/v1/memos/{id}/followup` is the safety net: if a memo is eligible and has no draft, the GET schedules one. This also covers any path added later and any process that died mid-generation.
- The GET answers `generating` only when `schedule_followup` reports that a run actually started. With the kill switch off it answers `unavailable`, so no client polls for a draft that will never come.

If the "ready at first paint" rate turns out low, the next step is drafting from the transcript in parallel with extraction — still without blocking the flip.

### 4.3 Single-flight

It mirrors `services/pipeline_lease.py` instead of inventing a second pattern:

- An in-process guard for same-instant bursts (writer + GET).
- A DB lease on `memos.followup_run_started_at`, compare-and-set with `or_(followup.is.null, followup_run_started_at.lt.<cutoff>)`, guarded by `hasattr(q, "or_")` as `pipeline_lease.py:97` does.
- **Ownership confirmed by primary key**, because PostgREST re-applies the PATCH filter to RETURNING (documented in `pipeline_lease.py:44`). The test fake reproduces that quirk on purpose.
- The final write is filtered on `followup->>run_id`, so a reclaimed lease is never overwritten.

### 4.4 Prompt, model and evals

- `backend/app/prompts/followup_v1.md`, versioned in the repo per `MASTER_PLAN.md`. The output is JSON `{subject, body, language}`.
- The rules that matter:
  - First person, in the rep's voice.
  - Only what was agreed; never invent prices, dates or attachments.
  - The language of the conversation.
  - 60–120 words, no filler openers.
  - A subject specific to the call.
- `FOLLOWUP_MODEL` (default: the router's model) at temperature 0.4: warmer than extraction's 0.0 because it is writing, but still close to the facts.
- **Evals before the prompt changes**: `backend/evals/followup/` with ~20 consented beta transcripts, scored by an LLM judge on four criteria: invented facts, every next step covered, language match, length. Built in the eval harness of `MASTER_PLAN.md` F0.3.

### 4.5 Voice learning and metrics

- `edit_ratio(draft, final)`: whitespace-insensitive, from 0 to 1. "Sent as drafted" means ≤ 0.02 — fixing a typo still counts as unedited. This gives B3's *% no-edit* metric for free.
- Voice samples keep only bodies the rep reshaped (≥ 0.05). Unedited drafts are our voice, not theirs, and learning from them would reinforce our own style. The last five are kept, and three go into the prompt.

### 4.6 Hand-off honesty

Without mail OAuth we can open the rep's mail client pre-filled, but we cannot know the email was sent. The card says *"Abierto en tu correo"* (*"Opened in your mail app"* on today's English surfaces), never *"Enviado"*. Only the memo's author records a hand-off: a manager can read a rep's draft, but never sends it from their own mailbox (the POST answers 403). A `mailto:` longer than 1,800 characters falls back to the subject only, with the body copied to the clipboard. WhatsApp is offered only when the phone number has a country code; a number without one is never guessed.

### 4.7 Not in slice 1

- Logging the sent email to the CRM: HubSpot, Salesforce and Pipedrive each need their own engagement write (slice 1b).
- Sending the draft back to field reps on WhatsApp.
- Gmail/Outlook OAuth.
- A *Reescribir* button.

---

## 5. Hoy engine (slice 2 — designed here, planned after slice 1 ships)

### 5.1 Signals are derived state

The engine never "creates tasks". For each contact it recomputes signals from the latest captured interaction, and a reconcile step compares them with what is stored:

- New keys are inserted.
- Pending keys that no longer apply resolve themselves.
- A key the rep already acted on (done, dismissed or snoozed) is never resurrected.

**A new call with a contact is what clears their card.** Hoy cleans itself, which is why it does not turn into another task backlog.

Triggers:
- **Per event**: after each extraction for that contact.
- **On a schedule**: a morning job per company time zone for the time-based signals. On Railway it is a cron service running `python -m app.jobs.morning`.

### 5.2 Data it needs that does not exist yet

| Input | Source |
|---|---|
| `interest` (high / medium / low / none) | New enum field, classified by the existing fast classifier (`services/llm/jev.py`), the same way it already classifies CRM dropdowns |
| Commitment due dates | Already derived from next steps (`services/hubspot/tasks.py` → `detected_task_due_iso`) |
| Commitment `origin` (the prospect asked vs the rep promised) | New enum, same classifier. It decides between *"Pidió que le llamaras"* and *"Quedaste en llamarle"* |
| Objection category | The copilot's existing taxonomy (`services/copilot/prompts.py:39`), reused as-is |

### 5.3 Engine and reasons (validated: 14 tests)

```python
# backend/app/services/hoy/signals.py
"""Hoy engine. Pure rules over a contact's captured interactions: no I/O."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal, Optional

Interest = Literal["high", "medium", "low", "none"]
SignalType = Literal["commitment_due", "going_cold", "objection_open"]
CommitmentKind = Literal["call", "email", "send", "meeting", "other"]

COLD_AFTER = timedelta(days=10)
WARM: frozenset[str] = frozenset({"high", "medium"})
TIER: dict[str, int] = {"commitment_due": 0, "going_cold": 1, "objection_open": 2}
DEFAULT_LIMIT = 7


@dataclass(frozen=True)
class Commitment:
    kind: CommitmentKind
    origin: Literal["prospect_request", "rep_promise"]
    text: str
    due_at: datetime


@dataclass(frozen=True)
class Touch:
    """One captured interaction (a memo), as the engine sees it."""

    memo_id: str
    contact_id: Optional[str]
    deal_id: Optional[str]
    at: datetime
    interest: Optional[Interest] = None
    objections: tuple[tuple[str, str], ...] = ()  # (category, quote)
    commitments: tuple[Commitment, ...] = ()
    deal_closed: bool = False


@dataclass(frozen=True)
class Signal:
    type: SignalType
    contact_id: Optional[str]
    deal_id: Optional[str]
    source_memo_id: str
    due_at: Optional[datetime]
    payload: dict = field(compare=False)
    dedupe_key: str = ""


@dataclass(frozen=True)
class Card:
    primary: Signal
    supporting: tuple[Signal, ...] = ()


def signals_for_contact(touches: list[Touch], *, now: datetime, day_end: datetime) -> list[Signal]:
    """All touches for ONE contact, any order. `day_end` is the end of the rep's local day."""
    if not touches:
        return []
    last = max(touches, key=lambda t: t.at)
    if last.deal_closed:
        return []

    base = {"contact_id": last.contact_id, "deal_id": last.deal_id, "source_memo_id": last.memo_id}
    out: list[Signal] = []

    for c in last.commitments:
        if c.due_at <= day_end:
            out.append(Signal(
                "commitment_due",
                due_at=c.due_at,
                payload={"kind": c.kind, "origin": c.origin, "text": c.text},
                dedupe_key=f"commitment:{last.memo_id}:{c.kind}:{c.due_at.date().isoformat()}",
                **base,
            ))

    waiting_on_future = any(c.due_at > day_end for c in last.commitments)
    if last.interest in WARM and now - last.at >= COLD_AFTER and not out and not waiting_on_future:
        out.append(Signal(
            "going_cold",
            due_at=None,
            payload={"interest": last.interest, "days_silent": (now - last.at).days},
            dedupe_key=f"cold:{last.memo_id}",
            **base,
        ))

    if last.objections and last.interest in (WARM | {"low"}):
        category, quote = last.objections[-1]
        out.append(Signal(
            "objection_open",
            due_at=None,
            payload={"category": category, "quote": quote, "touch_at": last.at.isoformat()},
            dedupe_key=f"objection:{last.memo_id}:{category}",
            **base,
        ))
    return out


def _rank_key(s: Signal, now: datetime) -> tuple:
    tier = TIER[s.type]
    if s.type == "commitment_due":
        return (tier, 0 if s.due_at < now else 1, s.due_at.timestamp())
    if s.type == "going_cold":
        # A lead that just crossed the line is more recoverable than a long-dead one.
        return (tier, 0 if s.payload["interest"] == "high" else 1, s.payload["days_silent"])
    return (tier, 0, -datetime.fromisoformat(s.payload["touch_at"]).timestamp())


def rank_cards(signals: list[Signal], *, now: datetime, limit: int = DEFAULT_LIMIT) -> tuple[list[Card], int]:
    """One card per contact: the strongest signal leads, the rest support it.
    Returns (visible cards, how many more are folded)."""
    groups: dict[str, list[Signal]] = {}
    for s in signals:
        groups.setdefault(s.contact_id or s.deal_id or s.source_memo_id, []).append(s)
    cards: list[Card] = []
    for group in groups.values():
        ordered = sorted(group, key=lambda s: _rank_key(s, now))
        cards.append(Card(primary=ordered[0], supporting=tuple(ordered[1:])))
    cards.sort(key=lambda c: _rank_key(c.primary, now))
    return cards[:limit], max(0, len(cards) - limit)


def reconcile(known: dict[str, str], fresh: list[Signal]) -> tuple[list[Signal], set[str]]:
    """known: dedupe_key → status of every stored signal (pending, done, dismissed, snoozed).
    Never resurrects a key the rep already acted on; resolves pending keys that stopped applying."""
    fresh_keys = {s.dedupe_key for s in fresh}
    to_insert = [s for s in fresh if s.dedupe_key not in known]
    to_resolve = {k for k, status in known.items() if status == "pending" and k not in fresh_keys}
    return to_insert, to_resolve
```

```python
# backend/app/services/hoy/reasons.py
"""The most-read sentence in the product, written once, server-side.
Deterministic on purpose: identical in every surface, instant, free, and it
cannot invent anything. The LLM is reserved for text that is unique (the draft)."""
from __future__ import annotations

from datetime import datetime

from app.services.hoy.signals import Signal

CATEGORY = {
    "es": {"price": "precio", "timing": "momento", "authority": "decisor", "competitor": "competencia",
           "status_quo": "statu quo", "trust": "confianza", "other": "otra"},
    "en": {"price": "price", "timing": "timing", "authority": "decision-maker", "competitor": "competitor",
           "status_quo": "status quo", "trust": "trust", "other": "other"},
}


def _lang(lang: str) -> str:
    return "en" if (lang or "").lower().startswith("en") else "es"


def _clause(text: str) -> str:
    """'Enviar el caso de logística.' → 'enviar el caso de logística'"""
    t = " ".join((text or "").split()).rstrip(".")
    return t[:1].lower() + t[1:] if t else t


def due_label(due_at: datetime, *, now: datetime, lang: str = "es") -> str:
    lang = _lang(lang)
    days = (now.date() - due_at.date()).days
    if days <= 0:
        if due_at > now:
            return f"Hoy a las {due_at:%H:%M}" if lang == "es" else f"Today at {due_at:%H:%M}"
        return "Hoy" if lang == "es" else "Today"
    if days == 1:
        return "Vencía ayer" if lang == "es" else "Due yesterday"
    return f"Vencía hace {days} días" if lang == "es" else f"Due {days} days ago"


def reason(signal: Signal, *, lang: str = "es") -> str:
    lang = _lang(lang)
    p = signal.payload
    if signal.type == "commitment_due":
        kind, origin, what = p["kind"], p["origin"], _clause(p["text"])
        if lang == "es":
            if kind == "call":
                return "Pidió que le llamaras." if origin == "prospect_request" else "Quedaste en llamarle."
            if origin == "rep_promise":
                return f"Le prometiste {what}."
            return f"Te pidió: {what}."
        if kind == "call":
            return "They asked you to call." if origin == "prospect_request" else "You said you'd call."
        if origin == "rep_promise":
            return f"You promised to {what}."
        return f"They asked: {what}."
    if signal.type == "going_cold":
        days = p["days_silent"]
        if lang == "es":
            lead = "Mostró mucho interés" if p["interest"] == "high" else "Mostró interés"
            return f"{lead} y lleváis {days} días sin hablar."
        lead = "Showed strong interest" if p["interest"] == "high" else "Showed interest"
        return f"{lead}; {days} days without talking."
    label = CATEGORY[lang].get(p["category"], p["category"])
    if lang == "es":
        return f"Quedó una objeción de {label} sin cerrar."
    return f"An open {label} objection."
```

What the tests pin down:
- A commitment due today or overdue is a card.
- A future commitment silences "going cold".
- `interest: none` never nudges.
- A closed deal is silent.
- A newer touch clears the older signals.
- One card per contact, with supporting signals attached.
- The order is overdue promises → hot leads → objections.
- Everything above the limit is folded.
- Reconcile never resurrects a dismissed key.
- Every sentence and due label, in ES and EN.

### 5.4 From card to view

A `Card` becomes the `TodayItem` of `PLAN_INTEGRACION.md` §3.3:

- `reason(card.primary)` and `due_label(...)` are written on the server.
- `evidence` is the objection quote from a supporting `objection_open` signal.
- `play` is the best playbook entry, or the best proven pattern, for that category.
- `primary_action` follows `kind`: call → *Llamar*, email or send → *Escribir*.

---

## 6. Interaction controllers (slices 2 and 5 — validated: 6 tests)

### 6.1 The SDR queue

```js
// shared/ui/queue.js
// "Empezar a llamar": Hoy becomes a dial queue. One loop, no navigation.
//   idle → queue(i) → calling(i) → review(i) → queue(i+1) … → done
// A call with no conversation (voicemail, no answer) produces no memo and
// advances straight to the next contact.
export const initialQueue = { mode: 'idle' };

export function queueReducer(state, event) {
  switch (state.mode) {
    case 'idle':
    case 'done':
      if (event.type === 'start' && event.items?.length) return { mode: 'queue', items: event.items, index: 0 };
      return state;
    case 'queue':
      if (event.type === 'call') return { ...state, mode: 'calling' };
      if (event.type === 'skip') return advance(state);
      if (event.type === 'exit') return initialQueue;
      return state;
    case 'calling':
      if (event.type === 'call_ended') {
        return event.memoId ? { ...state, mode: 'review', memoId: event.memoId } : advance(state);
      }
      return state;
    case 'review':
      if (event.type === 'reviewed') return advance(state);
      if (event.type === 'exit') return initialQueue;
      return state;
    default:
      return state;
  }
}

function advance(state) {
  const index = state.index + 1;
  if (index >= state.items.length) return { mode: 'done', items: state.items };
  return { mode: 'queue', items: state.items, index };
}

export function currentItem(state) {
  return state.items && state.index != null ? state.items[state.index] ?? null : null;
}

/** The next contact's brief is fetched while the rep is still on this one. */
export function prefetchTarget(state) {
  if (!['queue', 'calling', 'review'].includes(state.mode)) return null;
  return state.items[state.index + 1] ?? null;
}

/** Keyboard map per mode. Kept here so every surface binds the same keys. */
export const QUEUE_KEYS = {
  queue: { Enter: 'call', s: 'skip', Escape: 'exit' },
  review: { n: 'reviewed', Escape: 'exit' },
};
```

Wiring in the extension:
- On every transition to `queue`, the panel calls `chrome.tabs.update(tabId, { url: item.crmUrl })`, so HubSpot follows the queue (the `tabs` permission already exists).
- `call_ended` comes from the dialer's existing call state. Its voicemail screening produces no memo, so the queue moves on by itself.

### 6.2 The live pill

```js
// shared/ui/pill.js
// "Quiet by default" as a reducer. The pill speaks only with team evidence,
// never nags about the same objection twice in a row, and gets out of the way
// once the rep starts answering.
export const PILL_TIMING = {
  minHoldMs: 4000, // long enough to read one line
  maxShowMs: 10000,
  categoryCooldownMs: 60000,
};

export const initialPill = { visible: null, lastShownAt: {} };

export function pillReducer(state, event, timing = PILL_TIMING) {
  const { visible } = state;
  switch (event.type) {
    case 'suggestion': {
      const s = event.suggestion;
      if (!s?.isObjection || !s.grounded) return state;
      const last = state.lastShownAt[s.category] ?? -Infinity;
      if (event.at - last < timing.categoryCooldownMs) return state;
      if (visible && event.at - visible.shownAt < timing.minHoldMs) return state;
      return {
        visible: { ...s, shownAt: event.at },
        lastShownAt: { ...state.lastShownAt, [s.category]: event.at },
      };
    }
    case 'rep_speaking':
      if (visible && event.at - visible.shownAt >= timing.minHoldMs) return { ...state, visible: null };
      return state;
    case 'tick':
      if (visible && event.at - visible.shownAt >= timing.maxShowMs) return { ...state, visible: null };
      return state;
    case 'dismiss':
      return visible ? { ...state, visible: null } : state;
    default:
      return state;
  }
}
```

Inputs:
- **`suggestion`** comes from the existing `/api/v1/copilot/suggest` stream. The server adds `grounded` and `source_label` once playbook entries and patterns exist; until then nothing is grounded, and the pill stays silent — that is the contract, not a bug.
- **`rep_speaking`** comes from turns on the `rep` channel, which the desktop already labels (`lib/channels.js`).
- **`tick`** is a 1 s interval while a suggestion is visible.

---

## 7. Accessibility and motion

- **Contrast**: body text ≥ 4.5:1 on paper and cream. That is why muted text is `30 6% 42%`. Bronze text is 6.31:1 on white.
- **Focus**: every control gets a visible 2 px bronze outline. The editable subject and body get a soft ring, so it never looks like a form field.
- **Targets**: buttons are at least 36 px tall, and pills keep generous padding. Surfaces are mouse-first, but the SDR queue must also work from the keyboard alone.
- **Live regions**: `role="status"` for *"Escribiendo el seguimiento…"* and the hand-off result. The pill is polite.
- **Motion**: 150 ms, `cubic-bezier(0.32, 0.72, 0, 1)`. Under `prefers-reduced-motion`, no movement, only opacity.
- **Language**: components read `lang` from the element, or else from the document. The draft's language is whatever the conversation was in.

---

## 8. Testing and verification

| Layer | How | Command |
|---|---|---|
| Shared UI logic (escape, render, compose, queue, pill) | Pure modules | `node --test shared/ui/*.test.js` (added to `make test-js`) |
| Tokens and sync | Sandbox-based tests + drift checks | `node --test scripts/*.test.mjs`, then `node scripts/build-tokens.mjs --check` and `node scripts/sync-shared.mjs --check` in CI |
| Backend logic and service | `unittest` with a PostgREST-faithful fake and a fake LLM | `make test` |
| Prompt | Evals over consented beta transcripts | `backend/evals/followup/` (MASTER_PLAN F0.3) |
| Web UI | Reticle flow with a saved `intent` | Per `CLAUDE.md` |
| Extension and desktop glue | Manual smoke: the host code is kept thin enough to read in one screen | Checklist in the plan |

---

## 9. Rollout

- `FOLLOWUP_ENABLED` is the backend kill switch. With it off, no draft is generated and every card renders nothing (`unavailable`), so no UI flag is needed.
- Order: the founders and Gon first (dogfood), then the betas by rotation, per `MASTER_PLAN.md`.
- Two weeks after rollout, read three numbers: the no-edit rate, ready-at-first-paint, and hand-offs per review.

---

## 10. Open decisions

1. **Monorepo move** (plan Task 1). Recommended; the `Makefile` already assumes it.
2. **Default mail client** per company (mailto, Gmail or Outlook web). v1 uses mailto everywhere and adds the setting when a beta asks.
3. **The Hoy limit** (7) and the "going cold" threshold (10 days) are starting values, to be tuned with betas — not facts.
