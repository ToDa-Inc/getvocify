# Real-Time Sales Objection Copilot (Beta) — Design

**Date:** 2026-08-11  
**Status:** Approved for implementation (A/D + DEVELOP IT)  
**Surface:** `/dashboard/copilot` (beta nav badge)

## Problem

Vocify today is post-call CRM extraction. During cold calls (phone on speaker, laptop mic listening), the rep needs silent, sub-second coaching when the prospect objects — not a memo after hangup.

## Goals

1. Capture room audio (phone speakerphone) via laptop mic.
2. Transcribe in near-real-time (existing Speechmatics WS).
3. Detect when the prospect finishes a turn (silence / final segment).
4. Surface a short objection-handling response on screen only (no TTS — prospect must not hear AI).
5. Ship as a beta dashboard page; leave hooks for softphone / Zoom later.

## Non-goals (v1)

- Dual-channel / true speaker diarization
- Spoken AI responses (Gemini Live audio-to-audio)
- Zoom/Meet tab capture (architecture must not block it)
- Multi-tenant playbook CMS (textarea + localStorage is enough)
- Persisting full call recordings as memos (optional later)

## Competitive context

| Product | Mode | Takeaway |
|---------|------|----------|
| Gong / Chorus / Fireflies | Post-call | Wrong category for live coaching |
| Clari Copilot (Wingman), Balto, Cresta, Convo, Nimitai | Live battlecards | Target UX: silent on-screen cues at turn boundary |

## Approaches considered

### A — Gemini Live (native audio) end-to-end
Pros: lowest theoretical latency, tone awareness.  
Cons: audio-out is wrong for speakerphone coaching; Live API is Google WebSocket, not OpenRouter chat; harder to show text battlecards; overkill for silent UI.

### B — Speechmatics STT + turn detect + OpenRouter Flash text (chosen)
Pros: reuses Vocify live STT; silent text UI; OpenRouter key already in `.env`; Gemini 3 Flash (or Grok fast) for low-latency coaching; easy to extend.  
Cons: speakerphone mixes both voices; no true diarization in v1.

### C — Deepgram nova + LLM
Pros: strong real-time STT.  
Cons: Deepgram path is legacy/disabled; extra key; no reuse win.

**Decision:** Approach B.

## Architecture

```
Phone (speaker) → Laptop mic → PCM 16kHz
        → WS /api/v1/transcription/live (Speechmatics partials + finals)
        → Client turn detector (final segment + ~700–900ms quiet / no interim)
        → POST /api/v1/copilot/suggest (SSE stream)
        → OpenRouter google/gemini-3-flash-preview (text)
        → On-screen SuggestionCard (say-this / why / next question)
```

### Turn detection (v1)

Client-side, no Silero dependency yet:

1. Track `finalTranscript` growth and `interimTranscript` emptiness.
2. After a new final chunk, start a debounce timer (~800ms).
3. If interim stays empty and no new finals arrive → treat as end of prospect turn.
4. Skip triggers that are too short (< 8 words) or identical to last suggestion input.
5. Optional energy gate later (RMS from worklet) without changing API.

### Suggestion payload

```json
{
  "transcript_window": "rolling last ~90s of finals",
  "latest_turn": "last final segment that triggered",
  "product_context": "optional offer / ICP / proof points",
  "language": "auto|es|en",
  "call_mode": "speakerphone"
}
```

### Response shape (JSON, streamed as SSE `token` then final `result`)

```json
{
  "is_objection": true,
  "objection_type": "price|timing|authority|competitor|status_quo|trust|other|none",
  "urgency": "low|medium|high",
  "say_this": "1–3 short sentences the rep can speak aloud",
  "why_it_works": "one line coaching note",
  "next_question": "one discovery / advance question",
  "dont_say": "optional anti-pattern to avoid"
}
```

If `is_objection` is false, UI shows a light “listening / no objection” state or a soft next-best-question — not a flashy card.

## Prompt strategy

System prompt encodes:

- Role: silent cold-call copilot for phone speakerphone
- Frameworks: Acknowledge → Isolate → Reframe → Advance; LAER; Feel–Felt–Found (sparingly); never argue
- Style: short, speakable, match prospect language, no jargon dump
- Output: strict JSON only

## Model choice

| Role | Model | Why |
|------|-------|-----|
| STT | Speechmatics (existing) | Already live in product |
| Coach | `COPILOT_MODEL` default `google/gemini-2.5-flash-lite` via OpenRouter | Fastest abortable text (~300–1100ms); stream cutoff via AbortController |
| Avoid | `google/gemini-3.6-flash` | Mandatory reasoning → ~4s TTFT (measured) |
| Future | Gemini 3.1 Flash Live | Google Live API only (not OpenRouter). Needs AI Studio key; unavailable on current Vertex project/regions |

Gemini 3.1 Flash Live stays a future experiment for softphone voice agents, not this beta.

## UX

- Beta nav item: **Call Copilot**
- Big Listen / Stop control
- Live transcript strip (compact)
- Dominant suggestion card (large “Say this”)
- Product context drawer (defaults for Vocify cold outbound; editable; persisted localStorage)
- Latency indicator (ms from turn end → first token)

## Security / auth

- Suggest endpoint requires Bearer JWT (`get_user_id`)
- No storing transcripts by default in v1
- OpenRouter key stays server-side

## Extensibility (D)

- Softphone: same page, cleaner audio constraints
- Zoom: feed `MediaStream` from `getDisplayMedia({ audio: true })` into existing STT hook
- Optional second WS later for push suggestions

## Success criteria

- From prospect silence → first visible coaching text typically < 2.5s on good network
- Suggestions are speakable in under ~12 seconds of talk time
- Works on Chrome desktop with phone on speaker nearby
