# V1 review fixes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the cross-company playbook read, the blank meeting-review screen, the wrong pre-call brief, the frozen priority clock, the false "incomplete" empty Today, and the Ask turn that stays pending forever.

**Architecture:** Each fix stays inside the module that already owns the behavior. Reads stay scoped to the caller's company. A failed Ask loop becomes a terminal `failed` turn so the client stops polling. Empty Today with no signals is a complete read, not an unavailable one.

**Tech Stack:** Python/FastAPI, pytest, React 18, TypeScript, node:test.

## Global Constraints

- Do not sign the desktop app or invent a download URL. F01 needs an Apple identity and a hosted installer. Leave `desktop/package.json` identity and `RecordPage.tsx` alone.
- Do not invent annotated conversations for F09. Leave `backend/evals/F09/cases.json` alone.
- Do not rewrite playbook step extraction or the card-height animation in this plan. Those stay for a later pass.
- Company scope comes from `Membership`, never from the request body or a tool argument.
- A missing row for another company is `404`, the same as a missing row.
- Copy the Today clock pattern: a sentinel default means "use `datetime.now`"; tests replace `_CLOCK[0]` with a fixed instant.
- Deterministic logic gets a failing test before the implementation.
- Commit each task on `feat/vocify-v1`. Do not push.

---

### Task 1: Meeting review error view includes phrases

**Files:**
- Modify: `src/lib/meeting-proposal-review.ts`
- Modify: `src/lib/meeting-proposal-review.test.ts`
- Modify: `src/components/dashboard/memos/MeetingProposalReview.tsx`
- Modify: `shared/ui/meeting-proposal.js`

**Interfaces:**
- Consumes: `renderMeetingProposal` destructures `view.phrases` (`save`, `omit`, `reconcile`) whenever `view.visible` is true.
- Produces: `meetingProposalReadErrorView(title, phrases)` returns `{ visible: true, title, startsAt: null, save: false, omit: false, phrases }`.

- [ ] **Step 1: Write the failing test**

In `src/lib/meeting-proposal-review.test.ts`, extend the read-error assertion:

```ts
const phrases = { save: "Guardar", omit: "Omitir", reconcile: "Reconciliar" };
const view = meetingProposalReadErrorView(productCatalog.ES.meetingReadFailed, phrases);
assert.equal(view.title, productCatalog.ES.meetingReadFailed);
assert.deepEqual(view.phrases, phrases);
assert.equal(view.save, false);
assert.equal(view.omit, false);
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --experimental-strip-types --test src/lib/meeting-proposal-review.test.ts`
Expected: FAIL because `meetingProposalReadErrorView` takes one argument and returns no `phrases`.

- [ ] **Step 3: Write minimal implementation**

`meetingProposalReadErrorView` takes `phrases` and returns it on the view. `MeetingProposalReview` builds phrases with the existing `meetingProposalView(null, { surface: "review", extractionPending: true, lang: uiLang }).phrases` and passes them in. In `renderMeetingProposal`, if `view.phrases` is missing, use `{ save: "", omit: "", reconcile: "" }` so a future caller cannot blank the page.

- [ ] **Step 4: Run test to verify it passes**

Run: `node --experimental-strip-types --test src/lib/meeting-proposal-review.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/lib/meeting-proposal-review.ts src/lib/meeting-proposal-review.test.ts src/components/dashboard/memos/MeetingProposalReview.tsx shared/ui/meeting-proposal.js
git commit -m "fix: keep meeting review readable when the proposal read fails"
```

### Task 2: Playbook import reads stay inside the company

**Files:**
- Modify: `backend/app/services/playbooks/store.py`
- Modify: `backend/app/api/playbooks.py`
- Test: `backend/tests/playbooks/test_imports.py`

**Interfaces:**
- Consumes: `Membership.company_id`
- Produces: `get_import(company_id: str, import_id: str) -> dict | None` on both stores. `GET /api/v1/playbooks/imports/{import_id}` uses that signature and returns 404 when the row belongs to another company.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/playbooks/test_imports.py` a TestClient case: save an import for company `co-a`, then request it as company `co-b`. Expected status `404`. The same request as `co-a` returns `200` and that `import_id`.

Use `MemoryPlaybookStore` if the router already allows a store override; if not, add the smallest override the existing tests use and call `get_import` on the memory store directly as well:

```python
def test_import_from_another_company_is_not_found():
    store = MemoryPlaybookStore({}, {})
    store.save_import("co-a", {"import_id": "imp-a", "status": "ready", "draft": {"text": "secret"}}, None)
    assert store.get_import("co-b", "imp-a") is None
    assert store.get_import("co-a", "imp-a")["import_id"] == "imp-a"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/playbooks/test_imports.py::test_import_from_another_company_is_not_found -q`
Expected: FAIL, `get_import` does not take `company_id`.

- [ ] **Step 3: Write minimal implementation**

Memory store records `company_id` on the saved dict and `get_import` returns the row only when it matches. Supabase store adds `.eq("company_id", company_id)`. Update the call in `start`/`POST` that passes `existing=store.get_import(...)` to pass `membership.company_id`. `GET` stops discarding `membership` and passes `membership.company_id`. A miss stays `404`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/playbooks/test_imports.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/playbooks/store.py backend/app/api/playbooks.py backend/tests/playbooks/test_imports.py
git commit -m "fix: scope playbook import reads to the caller's company"
```

### Task 3: Pre-call brief uses the contact column

**Files:**
- Modify: `backend/app/api/briefs.py`
- Test: `backend/tests/briefs/test_preparation.py`

**Interfaces:**
- Consumes: memo columns `hubspot_contact_id`, `hubspot_deal_id`, `matched_deal_id`, `crm_connection_id`, `created_at`, `extraction`.
- Produces: `_from_memos(supabase, company_id, contact_id, *, connection_id, deal_id)` returns the newest matching memo's facts. No match with a successful query is `{"coverage": "complete"}` (the preparer then says there is no conversation). A query exception stays `{"coverage": "unavailable"}`.

- [ ] **Step 1: Write the failing test**

Fake supabase table that records filters. A memo whose `hubspot_contact_id` equals the requested contact, and whose `extraction` has no `contact_id`, must produce a brief with that memo's summary. A memo for another contact must not. When `deal_id` is set, only rows with that `hubspot_deal_id` or `matched_deal_id` count. Order is `created_at` descending and the limit stays 100.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/briefs/test_preparation.py -q -k contact_column`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Replace the scan of `extraction.contact_id` with:

```python
query = (
    supabase.table("memos")
    .select("id,created_at,extraction,hubspot_contact_id,hubspot_deal_id,matched_deal_id,crm_connection_id")
    .eq("company_id", company_id)
    .eq("hubspot_contact_id", contact_id)
    .order("created_at", desc=True)
    .limit(100)
)
if connection_id:
    query = query.eq("crm_connection_id", connection_id)
```

If `deal_id` is set, keep rows where `hubspot_deal_id` or `matched_deal_id` equals it. Pass `connection_id` and `deal_id` from `get_brief`. Leave `_LOADER` behavior unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/briefs/test_preparation.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/briefs.py backend/tests/briefs/test_preparation.py
git commit -m "fix: match pre-call briefs on the contact column"
```

### Task 4: Priority clock moves while the process stays up

**Files:**
- Modify: `backend/app/api/contact_priorities.py`
- Test: `backend/tests/hoy/test_priority_http.py`

**Interfaces:**
- Consumes: tests that assign `api._CLOCK[0] = NOW` keep that frozen instant.
- Produces: `_now()` returns `datetime.now(timezone.utc)` when `_CLOCK[0]` is still the import sentinel.

- [ ] **Step 1: Write the failing test**

```python
def test_priority_clock_advances_after_import():
    from app.api import contact_priorities as api
    first = api._now()
    assert api._CLOCK[0] is api._CLOCK_DEFAULT
    later = api._now()
    assert later >= first
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/hoy/test_priority_http.py::test_priority_clock_advances_after_import -q`
Expected: FAIL, `_CLOCK_DEFAULT` is missing and `_now()` is frozen.

- [ ] **Step 3: Write minimal implementation**

Match `backend/app/api/today.py`:

```python
_CLOCK_DEFAULT = datetime.now(timezone.utc)
_CLOCK = [_CLOCK_DEFAULT]

def _now() -> datetime:
    return datetime.now(timezone.utc) if _CLOCK[0] is _CLOCK_DEFAULT else _CLOCK[0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/hoy/test_priority_http.py -q`
Expected: PASS, including tests that freeze `_CLOCK[0]`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/contact_priorities.py backend/tests/hoy/test_priority_http.py
git commit -m "fix: let contact priority age move with the clock"
```

### Task 5: Zero Today signals are a complete empty read

**Files:**
- Modify: `backend/app/api/today.py`
- Test: `backend/tests/hoy/test_schedule.py` or the existing today HTTP test file if one asserts `_intelligence`

**Interfaces:**
- Produces: `_intelligence([]) == "complete"`. Rows that exist still follow the current coverage rules (`complete` only when every row is complete, otherwise `partial`).

- [ ] **Step 1: Write the failing test**

```python
def test_no_visible_signals_are_complete_coverage():
    from app.api.today import _intelligence
    assert _intelligence([]) == "complete"
    assert _intelligence([{"coverage": "complete"}]) == "complete"
    assert _intelligence([{"coverage": "partial"}]) == "partial"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/hoy/test_schedule.py::test_no_visible_signals_are_complete_coverage -q`
Expected: FAIL, empty list returns `unavailable`.

- [ ] **Step 3: Write minimal implementation**

```python
def _intelligence(rows: list[dict]) -> str:
    if not rows:
        return "complete"
    coverages = {row.get("coverage") or "unavailable" for row in rows}
    if coverages == {"complete"}:
        return "complete"
    return "partial"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/hoy/test_schedule.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/today.py backend/tests/hoy/test_schedule.py
git commit -m "fix: treat an empty Today as complete coverage"
```

### Task 6: A failed Ask loop ends the turn

**Files:**
- Modify: `backend/app/api/ask.py`
- Test: add `backend/tests/copilot/test_ask_failure.py` if no ask HTTP test exists; otherwise extend the existing ask test module.

**Interfaces:**
- Produces: when the configured loop returns `None`, the stored turn `status` is `failed` and the response is HTTP 200 with `"status": "failed"`. A successful loop still returns `completed`. GET of that turn returns `failed`, so a client that stops on `failed` does not poll forever.

- [ ] **Step 1: Write the failing test**

Post a turn with `set_ask_loop` returning `None`. Assert status code 200 and body `status == "failed"`. GET the same turn and assert `failed`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/copilot/test_ask_failure.py -q`
Expected: FAIL, status stays `pending` and the response is 202.

- [ ] **Step 3: Write minimal implementation**

In `_finish`, when `result is None`:

```python
if result is None:
    return {**turn, "status": "failed", "text": turn["text"]}
```

Persist that status the same way a completed turn is persisted when `_store` is set. Do not leave it as the original pending turn.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/copilot/test_ask_failure.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/ask.py backend/tests/copilot/test_ask_failure.py
git commit -m "fix: fail an Ask turn when the copilot loop returns nothing"
```
