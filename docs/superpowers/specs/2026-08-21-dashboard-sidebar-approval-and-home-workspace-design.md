# Dashboard Sidebar, Approval Split-Pane & Unified Home Workspace Design

**Date**: 2026-08-21  
**Author**: Dani Zal & Senior AI Assistant  
**Status**: Ready for Implementation  

---

## 1. Overview & Objectives

This specification defines the architectural enhancements to the Vocify web dashboard to deliver a seamless, intuitive, and modern user experience mirroring the desktop extension:

1. **Fixed Sidebar Navigation**: Keep the navigation sidebar pinned firmly on the left viewport across all screen sizes with dedicated scrolling for the main content area.
2. **Locked Transcript & CRM Approval Motion**: In the memo approval screen (`MemoDetail.tsx`), coordinate the layout with a sticky split-pane so the transcript remains locked and visible alongside the editable CRM fields, notes, tasks, and outcome selections as the user scrolls.
3. **Unified Home Recording & Activity Workspace**: Transform `DashboardHome.tsx` into a fast, interactive recording hub—embedding live recording, real-time waveform & transcription, quick transcript paste, and a live recent memos activity feed with direct one-click review.
4. **Consistent Two-Step Review Progression**: Provide clean step transitions ("Review Transcript & Extract" -> "Review CRM Fields & Sync") matching the extension's refined UX.

---

## 2. Layout & Viewport Architecture (`DashboardLayout.tsx`)

### Problem
Previously, the sidebar used `fixed lg:static inset-y-0 left-0 z-50 w-60`, which caused the sidebar to be in normal document flow on desktop (`lg:static`), leading to awkward document-level scroll behavior and misaligned headers.

### Solution
- **Fixed Left Rail**:
  - Set `<aside>` to `fixed inset-y-0 left-0 z-40 w-60 bg-background border-r border-border flex flex-col h-screen overflow-y-auto`.
  - **Compact Glued-Together Grouping**: Remove the empty `flex-1` space between the nav items and the "Scale with us" card. The logo header, nav menu links, and the upgrade card are unified into a compact, cohesive stack at the top of the sidebar.
  - Mobile behavior: responsive drawer with `sidebarOpen` toggle and overlay backdrop for screens `< 1024px`.
- **Main Viewport Shell**:
  - The main container receives `lg:pl-60 min-h-screen flex flex-col min-w-0 w-full`.
  - Header is `sticky top-0 z-30 h-14 glass-panel border-b border-white/40 backdrop-blur-md` for uninterrupted header controls.
  - Main content container (`<main>`) receives fluid page scroll with standard padding `p-6 md:p-8`.

---

## 3. Approval Section & Locked Transcript Split-Pane (`MemoDetail.tsx`)

### Problem
In the approval screen, reviewing deal fields, extensive notes, and multi-line CRM properties causes the page to scroll down, pushing the transcript out of view. Users had to repeatedly scroll up and down to cross-reference what was discussed against the extracted values.

### Solution: Coordinated Split-Pane Motion
- **Desktop Grid (`lg:grid-cols-5 gap-8`)**:
  - **Left Column (`lg:col-span-2`)**:
    - Sticky container: `sticky top-20 max-h-[calc(100vh-6rem)] flex flex-col gap-4 self-start`.
    - Compact Audio Player Card: Play/pause, scrub progress bar, and timestamp indicators.
    - Transcript Card: Displays `TranscriptConversation` with diarized speaker turns and an internal smooth scroll: `overflow-y-auto max-h-[calc(100vh-16rem)] pr-2 scrollbar-thin`.
    - Transcript Actions: Confidence accuracy badge, re-transcribe button, and prominent **"Extract & Continue"** action when in `pending_transcript` stage.
  - **Right Column (`lg:col-span-3`)**:
    - Scrollable `HubSpotSyncPreview` workspace containing:
      - Deal & Contact Target selection (cards, deal search, new deal creation).
      - Call Note / Summary editor (`CopilotNote` view).
      - Action Items & Next Steps tasks with due dates.
      - Proposed CRM Fields with inline editing, deletion, and custom field addition.
      - Call Outcome disclosure (Converted / On Hold / Lost).
      - Action Bar with **"Discard"** and **"Confirm & Update CRM"** buttons.

---

## 4. Unified Dashboard Home Workspace (`DashboardHome.tsx` + `VoiceRecorderWidget`)

### Problem
`DashboardHome.tsx` only displayed a static hero banner with a link redirecting to a separate `/dashboard/record` page, disconnecting the recording action from the recent memos list.

### Solution
Extract an interactive, self-contained `VoiceRecorderWidget` component and embed it directly into the top of `DashboardHome.tsx`:

### Component: `VoiceRecorderWidget.tsx`
- **Idle State**:
  - Large pulsing Record button with micro-interactions.
  - Quick utility action: **"Paste transcript"** button (with document icon) that opens an inline transcript paste drawer/modal for Zoom/Meet/Teams transcripts.
  - Audio file drag-and-drop / upload fallback.
- **Recording State**:
  - Active audio waveform visualization (`AudioWaveform`).
  - Real-time tabular recording timer (`00:00`).
  - Streaming real-time transcription (`LiveTranscript`) connected to Deepgram via WebSockets.
  - Clear "Stop recording" action button.
- **Transcript Ready State (Step 1)**:
  - Editable transcript review area with "Re-record" and **"Accept & Continue"** / **"Extract & Continue"** actions.
  - Direct smooth navigation to `/dashboard/memos/:id` for automated CRM extraction and approval.

### `DashboardHome.tsx` Integration
- **Header**: Welcome back greeting with active user name.
- **Top Section**: The interactive `VoiceRecorderWidget`.
- **Bottom Section**: Live `Recent Memos` list with:
  - Company/Contact title and summary preview snippet.
  - Duration and relative/formatted timestamp chips.
  - Real-time status badges (`Approved`, `Pending review`, `Review transcript`, `Processing`, `Failed`).
  - 1-click navigation directly to `/dashboard/memos/:id`.

---

## 5. Data Flow & State Management

```
User Action (Record / Paste) 
  ├── Live Audio / WebSockets STT -> Full Transcript
  └── Stop -> Upload Transcript / Audio -> Supabase Memo Created
        └── Auto-transition to /dashboard/memos/:memoId
              ├── Step 1: Diarized Transcript Review (Extract & Continue)
              └── Step 2: CRM Fields & Note Review (Confirm & Update CRM)
                    └── Sync to CRM -> Success Screen with CRM Deep Link
```

---

## 6. Error Handling & Edge Cases

1. **Microphone Permissions**: If denied or unavailable, display clear permission recovery instructions with retry button.
2. **STT Outages / Network Interruptions**: Seamlessly fall back to server-side audio processing.
3. **Extraction Failures**: Provide descriptive error banners with one-click **"Re-extract"** and **"Re-transcribe"** triggers.
4. **Auth Expiry on Long Review Sessions**: Automatically refresh access JWT on 401 for `/auth/me` and `/memos/*` endpoints without user session loss.

---

## 7. Testing & Verification

1. **Static Typecheck & Build**: Verify `npm run build` passes with zero TypeScript compiler errors.
2. **Unit Tests**: Ensure all existing tests pass (`node --test src/**/*.test.ts`).
3. **Viewport & Responsive Testing**:
   - Verify sidebar stays fixed on desktop (1280px, 1440px, 1920px) while main content scrolls.
   - Verify mobile drawer opens and closes properly on viewport `< 1024px`.
4. **Approval Split-Pane Verification**:
   - Verify transcript remains pinned in the left pane as right-hand CRM fields and note areas scroll.
   - Verify internal scroll works seamlessly inside the transcript card.
5. **Home Recording Flow**:
   - Verify start/stop recording, live timer, and waveform animations on Dashboard Home.
   - Verify paste transcript drawer imports text and progresses to memo review.
