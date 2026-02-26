# Vocify Extension UX Revamp – Implementation Plan

**Goal:** Make the extension the fastest, simplest way for sales reps to update HubSpot from voice. Reduce friction, remove hardcoded assumptions, and align with how users already work (or want to work): **Record → See what changes → Edit if needed → Approve**.

**Principle:** Users can already use HubSpot dropdowns and forms. We must be *faster* and *simpler* or we add no value. Every extra step is friction.

---

## Current State vs Target

| Aspect | Current | Target |
|--------|---------|--------|
| **Review steps** | 3 (transcript → full form → proposed changes) | 1 primary (proposed changes) + transcript on demand |
| **Fields** | Hardcoded 14+ in HTML | Dynamic from CRM config + schema |
| **Edit** | Full form in Step 2 | Inline edit + remove per proposed change |
| **Add field** | Not supported | "Add field" from allowed list |
| **Transcript** | Mandatory Step 1 | Always present, collapsible; source of truth |
| **Deal context** | Step 3 | Prominent from start when on deal page |

---

## Architecture Dependencies

### Existing APIs (no changes to contracts)

| Endpoint | Purpose |
|----------|---------|
| `GET /crm/hubspot/configuration` | Returns `allowed_deal_fields` + pipeline config |
| `GET /crm/hubspot/schema?object_type=deals` | Returns properties with `name`, `label`, `type`, `options` (for enums) |
| `GET /memos/:id/preview?deal_id=` | Returns `proposed_updates` (field_name, field_label, current_value, new_value) – **already dynamic** from config |
| `POST /memos/:id/preview` | Same with optional `extraction` override |
| `POST /memos/:id/approve` | Accepts `deal_id`, `is_new_deal`, `extraction` |

### Data Flow

- `proposed_updates` is derived from: `extraction` + `allowed_deal_fields` + deal schema (labels).
- Extension never needs to render fields from a hardcoded list; it renders `proposed_updates`.
- "Add new field" requires: config (`allowed_deal_fields`), schema (labels, types, options), and merging new field into `extraction.raw_extraction` before approve.

---

## Phase 0: Preparation (No UI Changes)

**Objective:** Ensure backend and extension can support the new flow without breaking existing behavior.

### 0.1 Backend: Enrich Preview for "Add Field"

- **Add optional `available_fields`** to `ApprovalPreview` response.
  - List of `{ name, label, type, options? }` for fields in `allowed_deal_fields` that are **not** in `proposed_updates`.
  - Enables "Add new field" dropdown without extra schema call.
- **Alternative:** Extension fetches config + schema separately. Simpler backend, more extension logic.
- **Recommendation:** Add `available_fields` to preview. Single round-trip, consistent with preview semantics.

### 0.2 Backend: Support Enum Options in ProposedUpdate (Optional)

- If we want inline edit to show dropdowns for enum fields, we need `options` per field.
- `ProposedUpdate` could get optional `field_type` and `options`.
- Enables proper controls (select vs text) in extension.

### 0.3 Extension: Add API Proxies

- Ensure extension can call:
  - `GET /crm/hubspot/configuration`
  - `GET /crm/hubspot/schema?object_type=deals`
- Via existing `api.get` / background proxy pattern.

---

## Phase 1: Remove Hardcoding, Single-Screen Flow

**Objective:** Replace 3-step wizard with a single "Proposed Changes" screen. All fields driven by backend.

### 1.1 New Review Screen Structure

**Single screen layout:**

```
┌─────────────────────────────────────────┐
│ Deal Target                              │
│ [Deal Name] – From current page / New   │
│ [Change Deal]                            │
├─────────────────────────────────────────┤
│ Proposed Changes                         │
│                                         │
│ Amount     [50000€]        ✏️ 🗑️        │
│   Was: 45000€                            │
│ Stage     [Negotiation]    ✏️ 🗑️        │
│   Was: Proposal                          │
│ ...                                     │
│                                         │
│ [+ Add field]                           │
├─────────────────────────────────────────┤
│ ▾ View transcript (collapsed by default) │
├─────────────────────────────────────────┤
│ [Confirm & Update CRM]  [Discard]        │
└─────────────────────────────────────────┘
```

### 1.2 Remove Step 2 (Hardcoded Form)

- Delete hardcoded fields from `popup/index.html` (Step 2).
- No more `ext-company`, `ext-amount`, etc. as fixed inputs.
- All editing happens inline on proposed changes.

### 1.3 Transcript as Collapsible Section

- Transcript always loaded and available.
- Default: collapsed ("View transcript").
- Expanded: shows full transcript for verification/editing.
- If user edits transcript: need path to re-extract (existing "Retry extraction").
- **Critical:** Transcript is the source for extraction. It must remain accessible but not block the main flow.

### 1.4 Direct-to-Proposed Flow

- When `status === 'review'`:
  - **If on deal page:** Go straight to proposed-changes screen (deal pre-selected).
  - **If not on deal page:** Same screen, with deal picker/search.
- Step 1 (transcript) becomes:
  - Either: auto-advance if `pending_review` (extraction done).
  - Or: skip when on deal page, show proposed changes first; transcript collapsible.

### 1.5 Pending Transcript Path

- If `pending_transcript`: user must confirm transcript to trigger extraction.
- Options:
  - **A:** Brief transcript step → "Looks good" → extract → then proposed changes.
  - **B:** Single screen with transcript at top (editable), "Extract & continue" → proposed changes.
- **Recommendation:** A. Minimal transcript view, one action to extract, then straight to proposed changes.

---

## Phase 2: Inline Edit + Remove

**Objective:** Edit or remove any proposed change without leaving the screen.

### 2.1 Per-Row Actions

- Each proposed update row has:
  - **Pencil (edit):** Click to switch to inline edit mode.
  - **Bin (remove):** Remove this field from the sync (don't send it to HubSpot).
- Edit mode:
  - **Text/number:** Inline input.
  - **Enum:** Dropdown (from `options` if available).
  - **Date:** Date picker.
  - Save on blur or Enter.

### 2.2 State Management

- Maintain local `editedProposedUpdates` derived from `preview.proposed_updates`.
- On edit: update local state.
- On remove: remove from list (visual + from extraction we'll send).
- On approve: build `extraction` from:
  - Original extraction
  - Overrides from edited/removed proposed updates
  - Merged into `raw_extraction` / top-level fields as appropriate.

### 2.3 Building Extraction for Approve

- Map proposed updates back to extraction structure:
  - `field_name` → `raw_extraction[field_name]` or top-level (e.g. `dealAmount` for `amount`).
  - Removed fields: omit from extraction.
  - Edited fields: use edited value.
- Reuse existing `approve` API; no backend changes needed.

---

## Phase 3: Add New Field

**Objective:** Let users add a field that wasn't extracted but is in `allowed_deal_fields`.

### 3.1 "Add field" UI

- Button: "+ Add field".
- Opens dropdown/modal with fields from `available_fields` (Phase 0) or from config + schema.
- User selects a field → add to proposed updates with empty or placeholder value.
- User can then inline-edit to set value.

### 3.2 Backend Support

- **Option A:** Extend preview to return `available_fields`.
- **Option B:** Extension fetches config + schema, computes `allowed_deal_fields - proposed_field_names`.
- Approve already accepts full `extraction`; new fields go into `raw_extraction`.

### 3.3 Validation

- For enums: value must be in `options`.
- For numbers: basic numeric check.
- Extension can use schema metadata; backend enum sanitizer already protects API.

---

## Phase 4: Context-Aware Entry & Polish

**Objective:** Reduce steps when context is clear; smooth loading and errors.

### 4.1 Entry Points

- **Record on deal page:** Context captured. When review loads, go straight to proposed changes with that deal. No deal picker unless user clicks "Change Deal".
- **Record elsewhere:** Show deal picker + proposed changes. Match-first or search.
- **Hotkey (Alt+Shift+V):** Same flow; side panel opens.

### 4.2 Loading States

- Skeleton for proposed changes while preview loads.
- Clear "Extracting..." when confirming transcript.
- Disable approve while syncing; show "Updating…" on button.

### 4.3 Error Handling

- Extraction failed: Retry + "Edit transcript" path.
- Preview failed: Retry + optional "Open in web app".
- Sync failed: Retry, keep edited extraction intact.

### 4.4 Empty States

- No proposed updates: "No fields to update from this memo. Add a note to the deal?" (if supported) or "Nothing to sync – Discard or add a field".
- No transcript: Should not occur (transcript required for extraction); handle gracefully.

---

## Implementation Order

| Phase | Tasks | Risk |
|-------|-------|------|
| **0** | Preview `available_fields`, enum metadata; extension API proxies | Low |
| **1** | Single-screen layout, remove Step 2, transcript collapsible, direct-to-proposed | Medium |
| **2** | Inline edit, remove, extraction merge for approve | Medium |
| **3** | Add field UI + backend/extension support | Low |
| **4** | Context-aware entry, loading, errors, empty states | Low |

---

## What We Do NOT Change

- **Approve API:** Same contract (`deal_id`, `is_new_deal`, `extraction`).
- **Preview API:** Same response shape; optional extensions only.
- **Web app MemoDetail:** Unchanged. Extension and web app can diverge slightly; web app stays full-featured.
- **CRM configuration:** No changes. Extension consumes it.
- **Extraction pipeline:** Unchanged. Extension only edits the extraction before approve.

---

## Rollback Strategy

- Feature flag or build variant: `REVIEW_FLOW=v2` to enable new flow.
- If issues: revert to 3-step flow by flipping flag.
- Phases are independent; Phase 1 can ship alone.

---

## Success Metrics

- **Clicks to approve** (on deal page): 3+ → 1.
- **Time to approve:** Measurable reduction.
- **Fields shown:** Always matches CRM config; no hardcoding.
- **Edit friction:** Edit/remove without leaving screen.

---

## Files to Touch (by Phase)

### Phase 0
- `backend/app/models/approval.py` – optional `available_fields` on preview
- `backend/app/services/hubspot/preview.py` – populate `available_fields`
- `chrome-extension/lib/api.js` or background – ensure configuration/schema calls

### Phase 1
- `chrome-extension/popup/index.html` – new single-screen structure
- `chrome-extension/popup/popup.js` – render from `proposed_updates`, remove Step 2 logic
- `chrome-extension/popup/styles.css` – layout for proposed changes, collapsible transcript

### Phase 2
- `chrome-extension/popup/popup.js` – inline edit/remove, extraction merge

### Phase 3
- `chrome-extension/popup/popup.js` – add-field UI
- `chrome-extension/popup/index.html` – add-field dropdown/modal

### Phase 4
- `chrome-extension/popup/popup.js` – entry-point logic, loading, errors
- `chrome-extension/background.js` – state/context handling if needed

---

## Summary

1. **Proposed changes are the primary screen** – not transcript, not a full form.
2. **Fields come from backend** – config + schema + preview; no hardcoding.
3. **Edit and remove inline** – pencil and bin per row.
4. **Add field** – from allowed list when user wants to add something.
5. **Transcript** – always available, collapsible, required for extraction.
6. **Context-aware** – on deal page, jump straight to proposed changes.
7. **Phased delivery** – each phase shippable and rollback-safe.
