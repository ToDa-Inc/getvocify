# Dashboard Sidebar, Approval Split-Pane & Unified Home Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a fixed, compact sidebar layout on the left, a coordinated sticky split-pane for locked transcript review in the memo approval screen, and an interactive home recording & memos workspace on Dashboard Home mirroring the extension.

**Architecture:** 
- Fix the sidebar on the left viewport with `fixed inset-y-0 left-0 w-60 z-40` and compact grouped navigation (no artificial `flex-1` gap), offsetting the main view with `lg:pl-60`.
- In `MemoDetail.tsx`, arrange the layout as a coordinated split-pane with the left transcript pane sticky-pinned (`sticky top-20`) so the transcript stays locked at eye-level alongside the scrolling CRM fields on the right.
- Build a self-contained `VoiceRecorderWidget` supporting live mic recording, waveform, Deepgram live streaming STT, and quick transcript import, and embed it directly into `DashboardHome.tsx` above the recent memos stream.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, Radix UI, TanStack React Query, Lucide Icons, Vite.

## Global Constraints
- Apply `/senior-code` standards: minimal surgical changes, zero duplication, existing theme tokens (`@/lib/theme/tokens`), no TODOs left behind.
- All unit tests must pass (`node --test src/**/*.test.ts`).
- Production build must succeed with zero TypeScript or JSX errors (`npm run build`).

---

### Task 1: Compact Fixed Sidebar Layout (`DashboardLayout.tsx`)

**Files:**
- Modify: `src/components/dashboard/DashboardLayout.tsx`

**Interfaces:**
- Consumes: `useAuth`, `getUserDisplayName`, `getUserInitials`, `Logo`, `THEME_TOKENS`, `DEMO_BOOKING_URL`
- Produces: Fixed left sidebar with compact grouped items and fluid main scrolling container

- [ ] **Step 1: Update `DashboardLayout.tsx` sidebar to be fixed, compact, and unified**

Update `src/components/dashboard/DashboardLayout.tsx`:
- Change `<aside>` to `fixed inset-y-0 left-0 z-40 w-60 bg-background border-r border-border flex flex-col h-screen overflow-y-auto`.
- Remove `flex-1` from `<nav>` so nav links and the "Scale with us" upgrade card are glued together in a compact group.
- Update the main container to `lg:pl-60 min-h-screen flex flex-col min-w-0 w-full` so the content area does not overlap the fixed sidebar.
- Maintain sticky header: `header className="h-14 sticky top-0 z-30 px-6 flex items-center justify-between glass-panel border-b border-white/40 backdrop-blur-md"`.

- [ ] **Step 2: Verify build and layout**

Run: `npm run build`
Expected: PASS with 0 errors.

- [ ] **Step 3: Commit sidebar layout update**

```bash
git add src/components/dashboard/DashboardLayout.tsx
git commit -m "feat(dashboard): fix sidebar on left with compact unified grouping"
```

---

### Task 2: Coordinated Sticky Split-Pane in Approval Screen (`MemoDetail.tsx`)

**Files:**
- Modify: `src/pages/dashboard/MemoDetail.tsx`

**Interfaces:**
- Consumes: `HubSpotSyncPreview`, `TranscriptConversation`, `memosApi`, `useParams`, `useSearchParams`
- Produces: Sticky transcript left pane and scrollable CRM fields right pane on desktop

- [ ] **Step 1: Refactor desktop layout in `MemoDetail.tsx` to sticky split-pane**

Update the grid in `src/pages/dashboard/MemoDetail.tsx`:
- Wrap the left transcript section in `sticky top-20 max-h-[calc(100vh-6rem)] flex flex-col gap-4 self-start lg:col-span-2`.
- Inside the Transcript card, configure internal smooth scrolling on `TranscriptConversation` using `overflow-y-auto max-h-[calc(100vh-16rem)] pr-2 scrollbar-thin`.
- Keep Audio player card compact at the top of the left rail.
- Ensure the "Extract & Continue" action button sits prominently inside the transcript card when `isPendingTranscript` is true.
- Keep the right column (`lg:col-span-3`) for `HubSpotSyncPreview` which scrolls smoothly through Deal target, Call note, Next steps tasks, Proposed fields, and Call outcome.

- [ ] **Step 2: Verify build and layout**

Run: `npm run build`
Expected: PASS with 0 errors.

- [ ] **Step 3: Commit locked transcript split-pane update**

```bash
git add src/pages/dashboard/MemoDetail.tsx
git commit -m "feat(approval): add sticky locked transcript split-pane for CRM review"
```

---

### Task 3: Build Interactive `VoiceRecorderWidget` Component

**Files:**
- Create: `src/components/dashboard/VoiceRecorderWidget.tsx`

**Interfaces:**
- Consumes: `useMediaRecorder`, `useAudioUpload`, `useRealtimeTranscription`, `AudioWaveform`, `LiveTranscript`, `THEME_TOKENS`, `V_PATTERNS`
- Produces: `<VoiceRecorderWidget onComplete={(memoId) => navigate(ROUTES.MEMO_DETAIL(memoId))} />`

- [ ] **Step 1: Create `src/components/dashboard/VoiceRecorderWidget.tsx`**

Implement `VoiceRecorderWidget.tsx` with:
- States:
  - `idle`: Pulsing circular Record button, "Tap to start recording" label, "Paste transcript" quick-action button (opens clean collapsible/modal for pasting transcripts), and file drag-and-drop zone.
  - `recording`: Active waveform visualization (`AudioWaveform`), real-time tabular duration timer, live streaming Deepgram transcription (`LiveTranscript`), and "Stop recording" button.
  - `transcript_ready` (Step 1): Review/edit transcript textarea with "Re-record" and "Transcribe / Extract & Continue" action.
  - `uploading`: Loading indicator with spinner during audio/transcript upload.
- Seamlessly calls `uploadTranscriptAndExtract` or `upload` and invokes `onComplete(memoId)` to transition directly into memo review.

- [ ] **Step 2: Verify TypeScript compilation**

Run: `npm run build`
Expected: PASS with 0 errors.

- [ ] **Step 3: Commit `VoiceRecorderWidget` component**

```bash
git add src/components/dashboard/VoiceRecorderWidget.tsx
git commit -m "feat(recording): create unified VoiceRecorderWidget component"
```

---

### Task 4: Integrate `VoiceRecorderWidget` into `DashboardHome.tsx`

**Files:**
- Modify: `src/pages/dashboard/DashboardHome.tsx`

**Interfaces:**
- Consumes: `VoiceRecorderWidget`, `memosApi`, `memoKeys`, `formatRecordedAtLabel`, `memoListTitle`, `memoListSubtitle`
- Produces: Complete unified home hub with live recorder, quick transcript import, and live recent memos feed

- [ ] **Step 1: Update `DashboardHome.tsx`**

- Replace the static "Record your meeting notes" redirect card with `<VoiceRecorderWidget onComplete={(memoId) => navigate(\`/dashboard/memos/\${memoId}\`)} />`.
- Enhance the Recent Memos list with:
  - Memo title (Company / Contact name)
  - Subtitle / preview snippet
  - Duration indicator
  - Formatted timestamp chip (`formatRecordedAtLabel`)
  - Status badges (`Approved`, `Pending review`, `Review transcript`, `Processing`, `Failed`)
  - Direct 1-click navigation to `/dashboard/memos/:id`.

- [ ] **Step 2: Verify build and layout**

Run: `npm run build`
Expected: PASS with 0 errors.

- [ ] **Step 3: Commit `DashboardHome.tsx` integration**

```bash
git add src/pages/dashboard/DashboardHome.tsx
git commit -m "feat(dashboard): integrate live recorder and memo activity feed on Home"
```

---

### Task 5: End-to-End Verification & Quality Polish

**Files:**
- Verify: All touched components and layout files

- [ ] **Step 1: Run unit tests**

Run: `node --test src/**/*.test.ts`
Expected: All 16+ tests PASS.

- [ ] **Step 2: Run production build**

Run: `npm run build`
Expected: PASS with 0 errors.

- [ ] **Step 3: Final Commit and status check**

```bash
git status
```
