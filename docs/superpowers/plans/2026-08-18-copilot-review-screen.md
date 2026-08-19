# Copilot Review Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the extension Review & sync screen into a Granola-style copilot: one note, a few dated task bullets, a quiet target, and everything else collapsed.

**Architecture:** Keep approve/sync APIs. Split review *presentation* into a small pure module (`review-insights.js`) that decides what is primary vs hidden. Popup HTML/CSS re-layout around note + tasks. Preview already extracts `nextSteps` + `nextStepSchedules`; surface due dates on the bullets instead of dumping them as CRM field rows.

**Tech Stack:** Chrome extension popup (`chrome-extension/popup/`), existing HubSpot approve payload (`create_note`, `nextSteps`, `proposed_updates`), Node test runner (`node --test chrome-extension/lib/*.test.js`).

## Global Constraints

- Extension side panel only in this plan. Do not restyle `HubSpotSyncPreview.tsx` unless a later task is added.
- Do not change HubSpot write behavior except: note is always created when there is a summary or transcript; unchecked tasks are omitted from `nextSteps` (already true).
- Paper-like Vocify cream/beige. No new color system. No native checkbox chrome — keep the existing custom boxes.
- Review session stays locked to the record it started on (already shipped). Do not re-open page-follow.
- Contact-only reviews already drop deal field rows (`proposedUpdatesForPage`). Keep that.
- User must reload the unpacked extension after JS/HTML/CSS changes.

---

## Product: what actually earns space

The current Review & sync stack (contact card + deal card + call note + fields list + action items + note checkbox + call outcome + open transcript) is a CRM form. Vocify’s job in this panel is a **copilot after a call**: remember what mattered, queue the next actions, write them to HubSpot with one tap.

### Keep on screen (priority order)

1. **Who** — contact name (already in the header). One line. No email, phone, or “This HubSpot contact · …” meta.
2. **Note** — Granola-style structured markdown (short headings + bullets), not a 3–5 sentence paragraph. Rendered, not a wall of prose. Editable. Posted to HubSpot as a note by default (no toggle).
3. **Tasks** — the last section of that same document (`Próximos pasos`). Checkbox = create this HubSpot task. Do not duplicate next steps inside the markdown and again as a separate block.
4. **Where** — deal is optional on a contact page. Keep the collapsed “Contact only / Choose deal” control from the previous pass. Do not add a second identity card.

### Hide or collapse

5. **CRM property diffs** — job title, amount, close date, lifecycle, etc. Useful sometimes, not the point. Collapse behind `CRM updates (n)`. Hide the section entirely when `n === 0`. Never show identity noise (email/phone/name that already matches HubSpot, or empty “no field updates” copy).
6. **Transcript** — keep it, default **closed**. The note already explains the call.
7. **Create HubSpot note** checkbox — remove. Always `create_note: true` when summary or transcript is non-empty.
8. **Call outcome** — keep, but move inside the collapsed CRM block. It is optional admin-gated chrome, not the copilot.

### Contact page specifically

On a HubSpot **contact** tab the write target is that contact (and company properties if the preview has real company diffs). A deal is opt-in via Choose deal. Do not imply a deal is required. Do not show deal field rows unless a deal is selected.

```
┌ Review & sync · Franck Valls ──────────────┐
│                                            │
│  Deal · Contact only              Choose   │
│                                            │
│  Contexto                                  │
│  · Cold call to Franck (NEURTEK)           │
│  · Did not recall prior contact            │
│  Perfil                                    │
│  · No internal sales team                  │
│    · Sales run through distributors        │
│  · CRM: Microsoft Dynamics                 │
│  Decisión                                  │
│  · Franck is not the decision maker        │
│  · Redirects to Aritzel Expuru, director   │
│  Próximos pasos                            │
│    ☑ Contactar a Aritzel Expuru     —      │
│    + Add                                   │
│                                            │
│  ▸ CRM updates                             │
│  ▸ Transcript                              │
│                                            │
│  [Discard]     [Update Franck Valls]       │
└────────────────────────────────────────────┘
```

### What “Granola-style” means for the note body

Today `summary` is forced to “3–5 sentences, prospect-centric CRM note”. That is why Franck’s call became one paragraph and lost the decision-maker beat.

Change the extraction contract:

- `summary` = short markdown. 2–4 headings that the call actually earned (not a fixed template). Each heading has 1–4 bullets. One nested level allowed. Bold people and companies. Same language as the transcript.
- Do **not** put `Próximos pasos` inside `summary`. That list is `nextSteps` and is rendered as the last section of the same visual document, with checkboxes.
- Do **not** recap the pitch. Do **not** invent. Prefer HubSpot CURRENT VALUES / glossary for names that collide with STT (`Franck`, `NEURTEK`). For a new person only heard on the call, keep the spoken name; do not guess a spelling we do not have.
- Cap length: ~400 words. Empty sections are omitted, never filled with fluff.

Worked example from the Franck / NEURTEK transcript (this is the target, not Granola’s EnerTech hallucination):

```
# Contexto
- Llamada en frío a Franck de NEURTEK para presentar Vocify
- No recordaba haber tenido contacto previo

# Perfil
- No gestiona un equipo comercial interno
  - Las ventas van por distribuidores externos
- Usan Microsoft Dynamics; los distribuidores también

# Decisión
- Franck no es el interlocutor adecuado
- Redirige a **Aritzel Expuru**, director de NEURTEK
```

`nextSteps`: `["Contactar a Aritzel Expuru en NEURTEK"]`

Vocify’s current paragraph (“Franck Valls ha aclarado que… Aridge Lexpuru”) is the failure mode: prose, STT name, no structure, next step buried.

---

## File map

| File | Responsibility |
|------|----------------|
| `chrome-extension/lib/review-insights.js` | Pure rules: which CRM rows to show, task row model (text + due + checked), note always-on, transcript default closed |
| `chrome-extension/lib/review-insights.test.js` | Tests for those rules |
| `chrome-extension/lib/extraction-omit.js` | Extend `buildApproveExtraction` to pass `nextStepSchedules` (due dates) through |
| `chrome-extension/lib/extraction-omit.test.js` | Assert schedules ride along with selected tasks |
| `chrome-extension/popup/index.html` | Markup: note+tasks block, collapsed CRM, collapsed transcript, no note checkbox |
| `chrome-extension/popup/styles.css` | Granola-like task rows (text + date chip), tighter target row, details/summary for CRM |
| `chrome-extension/popup/popup.js` | Render using the new helpers; always send `createNote: true`; stop opening transcript; slim contact card to name |
| `chrome-extension/lib/copilot-note.js` | Tiny markdown → HTML for the panel (`#`, `-`, nested `-`, `**bold**` only). Strip a trailing Próximos pasos heading from summary so it is not duplicated. |
| `chrome-extension/lib/copilot-note.test.js` | Parser tests |
| `backend/app/services/extraction.py` | Change `summary` prompt from 3–5 sentences to structured markdown |
| `backend/app/services/hubspot/note_format.py` | Render markdown summary as HTML lists in HubSpot; keep transcript collapsed-equivalent (still included, after the note) |
| `backend/app/services/hubspot/preview.py` | Optional: put ISO `due_date` on `next_step_task_*` proposed updates so the UI does not re-parse Spanish dates. Prefer this over duplicating `_parse_date_from_text` in JS. |

Out of scope: dashboard `HubSpotSyncPreview.tsx`, Salesforce, WhatsApp. Do not copy markdown hashes into HubSpot deal `description` — that field stays a one-liner or empty.

---

### Task 1: Presentation rules (what is “too much data”)

**Files:**
- Create: `chrome-extension/lib/review-insights.js`
- Create: `chrome-extension/lib/review-insights.test.js`

**Interfaces:**
- Produces:
  - `isIdentityNoiseField(update) → boolean`
  - `visibleCrmUpdates(updates) → updates[]` — drops insights fields, identity labels, unchanged email/phone, and empty values
  - `crmUpdatesSummaryCount(updates) → number`
  - `taskRowsFromPreview({ proposedUpdates, nextSteps, nextStepSchedules, dueDatesByIndex }) → { id, text, checked, dueDate }[]`
  - `formatTaskDueLabel(isoDate, { today }) → string` — `'Wed 20'` / `'Today'` / `''`
  - `shouldCreateHubSpotNote({ summary, transcript }) → boolean` — true when either is non-empty
  - `TRANSCRIPT_DETAILS_OPEN_DEFAULT = false`

Identity noise (do not show as CRM rows, do not show on the contact card):

```js
const IDENTITY_NOISE = new Set([
  'contact_name', 'company_name', 'dealname',
  'email', 'phone', 'firstname', 'lastname',
]);
```

Also drop a row when `current_value` and `new_value` are the same (trimmed, case-insensitive for email).

- [ ] **Step 1: Write failing tests**

```js
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  visibleCrmUpdates,
  formatTaskDueLabel,
  shouldCreateHubSpotNote,
  taskRowsFromPreview,
  TRANSCRIPT_DETAILS_OPEN_DEFAULT,
} from './review-insights.js';

describe('visibleCrmUpdates', () => {
  it('hides email/phone and leaves a real job title change', () => {
    const out = visibleCrmUpdates([
      { object_type: 'contacts', field_name: 'email', new_value: 'a@b.com', current_value: 'a@b.com' },
      { object_type: 'contacts', field_name: 'phone', new_value: '+34', current_value: '+34' },
      { object_type: 'contacts', field_name: 'jobtitle', field_label: 'Job title', new_value: 'Retired', current_value: 'Sales Director' },
      { object_type: 'task', field_name: 'next_step_task_0', new_value: 'Follow up' },
    ]);
    assert.equal(out.length, 1);
    assert.equal(out[0].field_name, 'jobtitle');
  });

  it('returns empty when the call only had a note and tasks', () => {
    assert.equal(visibleCrmUpdates([]).length, 0);
  });
});

describe('tasks and note', () => {
  it('pairs nextSteps with schedule ISO dates', () => {
    const rows = taskRowsFromPreview({
      nextSteps: ['Follow up with ops', 'Send one-pager'],
      nextStepSchedules: ['2026-08-20', ''],
    });
    assert.equal(rows[0].dueDate, '2026-08-20');
    assert.equal(rows[1].dueDate, null);
    assert.equal(rows[0].checked, true);
  });

  it('formats a due date as a short weekday chip', () => {
    assert.equal(
      formatTaskDueLabel('2026-08-20', { today: '2026-08-18' }),
      'Thu 20',
    );
  });

  it('always creates a note when there is a summary', () => {
    assert.equal(shouldCreateHubSpotNote({ summary: 'Retired.', transcript: '' }), true);
    assert.equal(shouldCreateHubSpotNote({ summary: '', transcript: '' }), false);
  });

  it('keeps the transcript collapsed by default', () => {
    assert.equal(TRANSCRIPT_DETAILS_OPEN_DEFAULT, false);
  });
});
```

- [ ] **Step 2: Run tests — expect FAIL** (`review-insights.js` missing)

Run: `node --test chrome-extension/lib/review-insights.test.js`

- [ ] **Step 3: Implement `review-insights.js`**

`formatTaskDueLabel`: parse `YYYY-MM-DD`, if equal to `today` return `'Today'`; else `Wed 20` via `Date` at noon UTC (avoid TZ off-by-one). Empty string when no date.

`taskRowsFromPreview`: prefer `nextSteps` + `nextStepSchedules`. If those are empty, fall back to `proposed_updates` rows whose `field_name` starts with `next_step_task_` (current popup path), using `update.due_date` when present.

- [ ] **Step 4: Re-run tests — expect PASS**

- [ ] **Step 5: Commit** `feat(extension): rank review fields so note and tasks come first`

---

### Task 2: Carry due dates through preview → approve

**Why:** Extraction already stores `nextStepSchedules` in `raw_extraction`. Preview formats HubSpot task subjects but the popup never sees the date. Approve already creates tasks via `format_next_step_task`, which re-parses the schedule. The UI still needs the ISO date to show a chip and to let the rep change it.

**Files:**
- Modify: `backend/app/services/hubspot/preview.py` (~197–213) — add `due_date` (ISO date string) onto each `next_step_task_*` `ProposedUpdate` if the model allows extra fields; if `ProposedUpdate` is strict, add an optional `due_date: Optional[str] = None` on that model.
- Modify: `chrome-extension/lib/extraction-omit.js` — `buildApproveExtraction` accepts `nextStepSchedules: string[]` aligned with selected `nextSteps`.
- Modify: `chrome-extension/lib/extraction-omit.test.js`

**Interfaces:**
- Preview row: `{ field_name: 'next_step_task_0', new_value: 'Follow up with ops', object_type: 'task', due_date: '2026-08-20' }`
- Approve extraction: `raw_extraction.nextStepSchedules = ['2026-08-20', '']` in the same order as `nextSteps`

Find `ProposedUpdate` (likely `backend/app/models/` or hubspot preview models). Add:

```python
due_date: Optional[str] = None  # YYYY-MM-DD, HubSpot task hs_timestamp date
```

In the existing next-steps loop, after `formatted = format_next_step_task(...)`:

```python
due_iso = formatted.due_date.date().isoformat() if formatted.due_date else None
proposed_updates.append(ProposedUpdate(
    field_name=f"next_step_task_{i}",
    field_label="Next Step (Task)" if i == 0 else f"Next Step {i + 1} (Task)",
    current_value=None,
    new_value=formatted.subject,
    extraction_confidence=extraction.confidence.get("fields", {}).get("next_step", 0.8),
    object_type="task",
    due_date=due_iso,
))
```

`buildApproveExtraction` — after setting `next.nextSteps`:

```js
  const schedules = Array.isArray(nextStepSchedules)
    ? nextStepSchedules.map((s) => (s ? String(s).slice(0, 10) : ''))
    : [];
  next.raw_extraction.nextStepSchedules = selectedSteps.map((_, i) => schedules[i] || '');
```

Test: selected two tasks, second has empty date → `nextStepSchedules` is `['2026-08-20', '']`.

HubSpot task create already reads `_next_step_schedule_hints(extraction)`. Confirm that path still sees `raw_extraction.nextStepSchedules` after approve. If `MemoExtraction` does not copy that key, set it on `raw_extraction` only (already the source for `_next_step_schedule_hints`).

- [ ] **Step 1:** Failing extraction-omit test for schedules
- [ ] **Step 2:** Implement JS + preview `due_date`
- [ ] **Step 3:** Run `node --test chrome-extension/lib/extraction-omit.test.js`
- [ ] **Step 4:** Commit `feat: pass task due dates from preview into review and approve`

---

### Task 3: Re-layout Review & sync (note + Granola tasks)

**Files:**
- Modify: `chrome-extension/popup/index.html` (`#proposed-changes-main`)
- Modify: `chrome-extension/popup/styles.css`
- Modify: `chrome-extension/popup/popup.js`

**Markup target** (replace the separate Call note / Fields / Action items / note checkbox blocks):

```html
<section id="call-insights-section" class="call-insights">
  <div class="copilot-note">
    <p class="caps-label">Note</p>
    <textarea id="review-summary" class="review-summary-input" rows="4" placeholder="What mattered on this call…"></textarea>
    <div id="action-items-list" class="action-items-list"></div>
    <p id="action-items-empty" class="action-items-empty" style="display: none;"></p>
    <button type="button" id="btn-add-action-item" class="btn-quiet-action">Add task</button>
  </div>

  <details id="crm-updates-details" class="review-disclosure">
    <summary id="crm-updates-summary">CRM updates</summary>
    <div id="proposed-changes-section">
      <div id="proposed-updates-list" class="updates-list"></div>
      <button id="btn-add-field" class="btn-add-field" type="button" style="display: none;">+ Add field</button>
      <div id="add-field-dropdown" class="add-field-dropdown" style="display: none;"></div>
    </div>
    <!-- move #call-outcome-section here, unchanged logic -->
  </details>
</section>

<details id="transcript-collapsible" class="transcript-collapsible">
  <summary>Transcript</summary>
  ...
</details>
```

Critical HTML change: remove the `open` attribute from `#transcript-collapsible` (it is currently forced open).

Remove `#create-note-row` entirely.

Contact card: keep `#target-contact-name`. Stop filling `#target-contact-meta` (leave empty / `display: none`). Header already says the name.

Deal block: keep the collapsed one-card + Choose deal from the previous change. Optionally shrink `#deal-card` to a single line (`Deal · Contact only`) if it still eats height — do that in CSS (`#deal-card { padding: 10px 12px; }`), do not re-open the picker work.

**Task row HTML** (`renderActionItems`):

```html
<div class="action-item">
  <label class="action-item-check">…existing checkbox…</label>
  <input class="action-item-text" value="Follow up with ops">
  <time class="action-item-due" datetime="2026-08-20">Thu 20</time>
  <button class="action-item-remove">×</button>
</div>
```

Date control: clicking `.action-item-due` reveals `<input type="date">` (native, tiny). Changing it sets `item.dueDate`. Empty date shows an em dash `—` at muted opacity, clickable to add a date. Do not put dates in the title text (extraction prompt already forbids that).

`renderProposedUpdates`: feed it `visibleCrmUpdates(...)` instead of the current filter-only-insights list. After render, set:

```js
const n = visibleCrmUpdates(...).length;
const details = document.getElementById('crm-updates-details');
const summary = document.getElementById('crm-updates-summary');
if (details) details.style.display = n || hasCallOutcome ? '' : 'none';
if (summary) summary.textContent = n ? `CRM updates (${n})` : 'CRM updates';
```

`initCallInsights` / loadPreview nextSteps: build rows via `taskRowsFromPreview` so dates survive. Prefer extraction `nextSteps` + `raw_extraction.nextStepSchedules` when the memo fetch returns them; else preview task rows + `due_date`.

Approve click handler:

```js
const createNote = shouldCreateHubSpotNote({
  summary: document.getElementById('review-summary')?.value,
  transcript: document.getElementById('transcript-content')?.value,
});
```

Always pass that boolean (true whenever there is content). Do not read a checkbox.

`buildExtractionForApprove` passes:

```js
nextStepSchedules: reviewActionItems
  .filter((i) => i.checked && i.text.trim())
  .map((i) => i.dueDate || ''),
```

**CSS notes (keep Vocify paper, Granola density):**

- `.copilot-note` — no extra card around the textarea; tasks sit immediately under it with 8px gap.
- `.action-item` — one row, no box shadow, hairline only if needed; text is the label; date is 11px `var(--muted)` right-aligned, min-width ~48px.
- `.action-item.is-unchecked .action-item-text` — muted, not struck through (unchecked = “don’t create”, not “done”).
- `.review-disclosure summary` — same caps-label language as transcript (11px, muted). Default closed.
- Hide `.action-items-empty` when there are zero tasks (do not show “No action items…” — empty is fine; Add task is enough).

- [ ] **Step 1:** HTML restructure + transcript not `open`
- [ ] **Step 2:** CSS for note+task cluster and disclosure
- [ ] **Step 3:** Wire popup.js (imports, `renderActionItems` dates, hide contact meta, always create note, `visibleCrmUpdates`)
- [ ] **Step 4:** `node --test chrome-extension/lib/review-insights.test.js chrome-extension/lib/extraction-omit.test.js chrome-extension/lib/review-screen.test.js`
- [ ] **Step 5:** Commit `feat(extension): make review a note-and-tasks copilot`

**Manual check after reload:**
1. Open Review & sync on a contact. See name in the header, not phone/email on a card.
2. Note is the first body block; tasks are bullets under it with a date or —.
3. Transcript is closed until you open it.
4. No “Create HubSpot note” row. Sync still creates the note.
5. CRM updates is closed; open it only if there are real property diffs.
6. Unchecking a task omits it from HubSpot. Changing the date updates the HubSpot due date on sync.

---

### Task 4: Slim the target row (contact page)

This is polish on Task 3 if the deal card is still loud.

**Files:**
- Modify: `chrome-extension/popup/popup.js` (`renderContactTarget`, deal card copy)
- Modify: `chrome-extension/popup/styles.css`

Rules:
- If `selected_contact` and we are not picking among candidates: do not render `#contact-card` at all when `#review-record-name` already shows that name. Candidates list still shows when the user must pick.
- Deal line stays: `Contact only` / deal name + `Choose deal`.

Test: no new unit test required if Task 1 already hides identity fields. Visual check only.

- [ ] **Step 1:** Hide redundant contact card when the header already names them
- [ ] **Step 2:** Reload extension, confirm one name not two
- [ ] **Step 3:** Commit `fix(extension): drop duplicate contact identity on review`

---

### Task 5: Granola-style note data (extraction + render)

This is the data quality of the display. Layout without this still shows a paragraph.

**Files:**
- Modify: `backend/app/services/extraction.py` (`EXTRACTION_SYSTEM_PROMPT` rule 5, `all_standard["summary"]`, numbered rule 4, `hubspot_call` source hint)
- Modify: `backend/app/services/hubspot/note_format.py` — parse the same tiny markdown subset into HTML (`<h3>`, `<ul>`, `<li>`, `<strong>`)
- Create: `backend/tests/` or existing test path next to `note_format.py` if tests already live under `backend/` — add `test_note_format_markdown.py` using the Franck fixture
- Create: `chrome-extension/lib/copilot-note.js`
- Create: `chrome-extension/lib/copilot-note.test.js`
- Modify: `chrome-extension/popup/index.html` — `#copilot-note-view` (rendered) + keep `#review-summary` as hidden/raw edit buffer
- Modify: `chrome-extension/popup/styles.css` — heading 12px semibold, bullets 13px, nested indent 14px, no card
- Modify: `chrome-extension/popup/popup.js` — render view from summary; click view → textarea; blur → re-render. `Próximos pasos` heading in the view is static chrome above `#action-items-list`, not part of the markdown.
- Modify: `backend/app/services/hubspot/deals.py` — if `description` is filled from `extraction.summary`, take the first heading’s first bullet or skip when summary contains `#`

**Interfaces:**
- `parseCopilotNote(markdown) → { sections: [{ title, items: [{ text, children: string[] }] }] }`
- `stripNextStepsSection(markdown) → markdown` — drops a last heading matching `/próximos pasos|next steps/i`
- `format_hubspot_note_body` already takes `summary`; it must emit lists not escaped `# Heading` paragraphs

Prompt replacement for `summary` (user + system, keep language rule):

```
summary: Structured call note in the transcript language. Markdown only:
- 2–4 headings the call actually earned (`# Contexto`, `# Perfil`, `# Decisión`, …). Do not use a fixed template; omit a heading if the call has nothing for it.
- Under each heading: 1–4 bullets (`- `). One nested level (`  - `) allowed.
- Bold proper names (`**Aritzel Expuru**`).
- No pitch recap. No invented facts. Prefer CURRENT CRM VALUES / glossary when a spoken name is a phonetic near-match (Franck, NEURTEK).
- Do NOT include a Próximos pasos / Next steps heading — that is nextSteps.
- Not a paragraph. Not 3–5 sentences of prose.
```

`nextSteps` prompt stays: only explicit commitments. For this call that is one task: contact the director.

**Display:**
- Default: rendered markdown (not textarea).
- Click note → full markdown textarea (power users / fix a heading). Blur or Done restores render.
- Below the last section, always show `Próximos pasos` (or `Next steps` if the note is English) + task rows. If `nextSteps` is empty, still show the heading and `Add task` so the rep can add one.

**HubSpot note:** summary HTML first (Granola scan), then transcript as today. Reps who only open HubSpot still get the structure.

**Deal description:** do not dump `# Contexto\n- …` into `description`. Either first bullet plaintext or leave description unchanged.

- [ ] **Step 1: Parser tests** in `copilot-note.test.js` using the Franck markdown fixture; assert sections, nested bullet, strip of a trailing `# Próximos Pasos` block
- [ ] **Step 2: Implement `copilot-note.js`**
- [ ] **Step 3: Extraction prompt change** + `note_format.py` markdown HTML. Fixture: Franck markdown in → HubSpot body contains `<h3>` / `<ul>`, not literal `# Contexto`
- [ ] **Step 4: Popup render + edit toggle**
- [ ] **Step 5: Run** `node --test chrome-extension/lib/copilot-note.test.js` and whatever Python test was added
- [ ] **Step 6: Commit** `feat: extract and render Granola-style call notes`

**Manual check:** Re-extract the Franck memo. Note should scan like Granola. Task under Próximos pasos = contact Aritzel. Transcript closed. HubSpot timeline note uses headings + bullets. STT “Aridge Lexpuru” should not win over a glossary/CRM name if one exists; if neither exists, keep the transcript spelling rather than inventing EnerTech.

---

## What we are explicitly not doing

- Auto-sync without Review & sync. Copilot still needs a human tap.
- Redesigning the dashboard HubSpot preview in this pass.
- Opening a date picker library. Native `input type="date"` only.
- Showing pain points / objections / competitors as extra UI sections. If they matter, they become a heading inside the note.
- Re-expanding the deal picker. That work is done.

---

## Spec coverage

| Request | Task |
|---------|------|
| Fields section too heavy / not copilot | 1, 3 |
| Strip to priorities | Product section + 1 |
| Email/phone not needed on contact | 1, 3, 4 |
| Deal optional; contact/company on contact page | already shipped + Task 4 |
| Note created by default | 1 (`shouldCreateHubSpotNote`), 3 (remove checkbox) |
| Tasks as Granola bullets next to the note | 3 |
| Checkbox creates the task from free text | already the model; restyle in 3 |
| Simple dates on tasks | 2, 3 |
| Transcript not opened by default | 3 (remove `open`) |
| Condense / explain simply | Product layout + Task 5 structured note |
| Granola-style headings + bullets | Task 5 |
| Next steps actionable in the same document | Tasks 3 + 5 |
| Better names / less prose than current summary | Task 5 (prompt + CRM grounding) |

---

## Execution

Plan saved to `docs/superpowers/plans/2026-08-18-copilot-review-screen.md`.
