# Extraction, Speakers, and Desktop Companion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make CRM field mapping and review trustworthy, show You/contact speakers in the dashboard like the extension, and ship a Granola-style desktop companion that listens to system audio.

**Architecture:** Keep HubSpot allowlists as the mapping layer; annotate each property with fill policy; port extension omit/edit into dashboard approve; share diarized transcript parsing (named speakers + You/Them labels) across Python, dashboard, and companion; Electron loopback + existing `copilot_channels` STT for system audio.

**Tech Stack:** FastAPI/Pydantic, React/TypeScript, Node test runner, Electron (companion shell only).

## Global Constraints

- Do not invent a second Vocify→HubSpot field mapper; mapping remains the HubSpot allowlist plus fill policy.
- Speaker labels on the dashboard must match the extension: `You` and contact first name or `Them`.
- Approve must strip omitted fields from `raw_extraction` / identity aliases, not only hide UI rows.
- Desktop companion must reuse existing `/auth/login`, live STT `mode=copilot_channels`, and `POST /memos/upload-transcript`.
- No exploit/PoC code; capture is the user's own system audio for their Vocify account.
- Follow existing THEME_TOKENS; no new CSS framework.

---

### Task 1: Transcript parser parity (Python + dashboard TS)

**Files:**
- Modify: `backend/app/services/transcript_turns.py`
- Create: `backend/tests/test_transcript_turns.py`
- Create: `src/lib/transcript-turns.ts`
- Create: `src/lib/transcript-turns.test.ts`

**Interfaces:**
- Consumes: Speechmatics-style `SPEAKER: S1` / `Speaker 1` / `SPEAKER: JUAN` transcripts
- Produces: `parseTranscriptTurns`, `normalizeSpeaker`, `speakerSide`, `speakerDisplayLabel`, `firstName`, `normalizeDiarizedTranscript`, `speakerPromptLegend(transcript, prospect_name=None)`

- [ ] Write Python + TS tests for named speakers and You/Them labels
- [ ] Implement named-speaker parse in Python (match chrome-extension)
- [ ] Implement dashboard TS port
- [ ] Add `speaker_prompt_legend` for extraction prompts

### Task 2: Fill-policy on schema + Settings field mapping UX

**Files:**
- Modify: `backend/app/services/hubspot/types.py` (`fill_policy` optional on `HubSpotProperty`)
- Modify: `backend/app/services/extraction_policy.py` (`annotate_schema_fill_policies`)
- Modify: `backend/app/api/crm.py` (annotate schema response)
- Create: `backend/tests/test_extraction_policy.py`
- Create: `src/lib/fill-policy.ts`
- Modify: `src/lib/api/crm.ts`
- Modify: `src/components/dashboard/hubspot/HubSpotConfiguration.tsx`
- Modify: `src/pages/dashboard/SettingsPage.tsx`

**Interfaces:**
- Produces: each schema property has `fill_policy`; Settings shows selected-first list with policy badges

### Task 3: Extraction prompt uses speaker legend

**Files:**
- Modify: `backend/app/services/extraction.py`
- Create: `backend/tests/test_extraction_prompt.py` (call `build_extraction_prompt` if config allows; otherwise test legend helper only)

### Task 4: Dashboard speaker UI + review omit parity

**Files:**
- Create: `src/lib/extraction-omit.ts`
- Create: `src/lib/extraction-omit.test.ts`
- Create: `src/components/dashboard/memos/TranscriptConversation.tsx`
- Modify: `src/pages/dashboard/MemoDetail.tsx`
- Modify: `src/components/dashboard/hubspot/HubSpotSyncPreview.tsx`

**Interfaces:**
- `buildApproveExtraction` + `omittedKeys` on sync
- `canEditOrRemoveProposedField` for deal/contact/company rows
- `TranscriptConversation` uses extraction.contactName or preview selected_contact.name

### Task 5: Desktop companion

**Repo:** [ToDa-Inc/getvocify-desktop](https://github.com/ToDa-Inc/getvocify-desktop) (not `desktop/` in this repo)

**Files:**
- Create: companion app in `getvocify-desktop` (`package.json`, `electron-main.mjs`, renderer, `lib/*`, tests)
- Modify: `src/pages/dashboard/RecordPage.tsx` (link to getvocify-desktop)
- Modify: `Makefile` test-js target (if needed for dashboard-only tests)

**This repo:** `desktop/README.md` is a pointer only.

### Task 6: Verify, commit, PR
