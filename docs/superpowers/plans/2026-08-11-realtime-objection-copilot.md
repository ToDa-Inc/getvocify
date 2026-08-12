# Real-Time Objection Copilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline — user requested DEVELOP IT).

**Goal:** Ship a beta `/dashboard/copilot` page that listens via mic, transcribes with Speechmatics, detects prospect turn ends, and streams OpenRouter Gemini Flash objection coaching as silent on-screen cards.

**Architecture:** Reuse `useRealtimeTranscription` → client turn debounce → `POST /api/v1/copilot/suggest` SSE → OpenRouter chat completions with structured JSON.

**Tech Stack:** FastAPI, httpx SSE, React/Vite, existing Speechmatics WS, OpenRouter `google/gemini-3-flash-preview`.

## Global Constraints

- Silent coaching only (no TTS)
- Phone speakerphone first; do not hard-block Zoom/softphone stream injection later
- Auth on suggest endpoint via Bearer JWT
- Do not commit secrets; use `COPILOT_MODEL` env with safe default
- Match existing Vocify dashboard visual language (cream/beige)

---

### Task 1: Backend copilot suggest + prompt

**Files:**
- Create: `backend/app/services/copilot/__init__.py`
- Create: `backend/app/services/copilot/prompts.py`
- Create: `backend/app/services/copilot/suggest.py`
- Create: `backend/app/api/copilot.py`
- Modify: `backend/app/api/router.py`
- Modify: `backend/app/config.py` (add `COPILOT_MODEL`)
- Modify: `.env.example`

**Interfaces:**
- Produces: `POST /api/v1/copilot/suggest` → SSE (`event: token|result|error`)
- Request body: `{ transcript_window, latest_turn, product_context?, language?, call_mode? }`

- [x] Implement prompt + streaming suggest + route registration

### Task 2: Frontend feature module + page

**Files:**
- Create: `src/features/copilot/types.ts`
- Create: `src/features/copilot/api/suggest.ts`
- Create: `src/features/copilot/hooks/useTurnDetector.ts`
- Create: `src/features/copilot/hooks/useObjectionSuggestions.ts`
- Create: `src/features/copilot/components/SuggestionCard.tsx`
- Create: `src/features/copilot/components/CopilotControls.tsx`
- Create: `src/features/copilot/index.ts`
- Create: `src/pages/dashboard/ObjectionCopilotPage.tsx`
- Modify: `src/App.tsx`, `DashboardLayout.tsx`, `constants.ts`

- [x] Wire Listen → transcript → turn detect → suggest → UI

### Task 3: Smoke verify

- [ ] Typecheck / lint touched files; ensure imports resolve
