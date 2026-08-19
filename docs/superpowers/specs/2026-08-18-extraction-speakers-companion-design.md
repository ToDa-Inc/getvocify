# Field extraction, speaker display, and desktop companion — Design

**Date:** 2026-08-18  
**Status:** Approved for implementation (cloud agent: user asked to plan and build)  
**Surfaces:** Settings field mapping, memo dashboard transcript, HubSpot review, [getvocify-desktop](https://github.com/ToDa-Inc/getvocify-desktop) companion

## Problem

Three related gaps in how Vocify turns a call into a CRM update:

1. **Field extraction / mapping is hard to trust.** Settings already has HubSpot allowlists, fill policies already exist in the backend, and the extension can edit or omit contact/company fields — but the dashboard review does not, removed fields can still sync from stored extraction, and Settings does not show *how* each field is filled (identity vs call-note vs never-from-a-call).
2. **Speakers are labeled in the extension, not in the dashboard.** Extension review shows **You** vs the contact’s first name (or **Them**). Memo detail dumps raw `SPEAKER: S1` lines. Python’s transcript parser also misses named speakers (`SPEAKER: JUAN`), so extraction and CRM notes are weaker than the extension.
3. **The Chrome extension cannot hear Zoom / Meet / Teams desktop audio.** Tab capture only works on a Chrome tab. Granola-style system-audio loopback is the missing capture path.

## Goals

1. Make field mapping and review one consistent loop: Settings chooses *which* fields AI may write; fill policy decides *when*; review lets the rep edit or omit contact, company, and deal fields; approve must not write omitted values.
2. Render dashboard transcripts with the same speaker labels as the extension (`You` / contact first name / `Them`).
3. Ship a tiny desktop companion that captures **system audio (prospect)** + **mic (rep)**, live-transcribes on the existing Speechmatics channel WS, and uploads a meeting transcript into the SaaS.

## Non-goals

- Replacing the Chrome extension.
- A polished auto-updating installer / code-signed store build.
- Changing HubSpot note HTML speaker copy beyond parser parity (dashboard is the requested surface).
- Salesforce field-mapping UI (same allowlist pattern exists; this pass is HubSpot + shared extraction).
- Bot-joining Zoom/Meet.

## Approaches considered

### Field mapping

**A — Rebuild Settings as a visual mapper (Vocify field → HubSpot property).**  
Pros: explicit. Cons: Vocify already extracts *into HubSpot property names* via allowlist; a second mapping layer fights the current pipeline.

**B — Keep allowlists; surface fill policy; make dashboard review match the extension (chosen).**  
Pros: uses existing extraction + `extraction-omit` contract; Settings becomes understandable; review stops silently writing binned fields. Cons: not a new mapping engine.

**C — Auto-select fields from HubSpot usage.**  
Pros: less config. Cons: dangerous writes; out of scope.

**Decision:** B.

### Speakers

**A — Duplicate extension HTML/CSS in React.**  
**B — Shared transcript-turn helpers in dashboard TS + Python parser parity (chosen).**  
**C — Store structured turns in the DB.** YAGNI: transcripts already serialize as `SPEAKER: S1` blocks.

**Decision:** B. Labels: `s1 → You`, `s2 / named → firstName(contact) || Them`. Contact name from extraction `contactName`, else preview `selected_contact.name`.

### Desktop companion

**A — Native Swift/C# apps.** Too much for “super simple.”  
**B — Electron + Chromium loopback (`audio: 'loopback'`) + existing `copilot_channels` STT (chosen).** Same dual-channel model as the extension (system = prospect, mic = rep).  
**C — Python + PulseAudio only.** Fine on Linux, not Granola-like on macOS/Windows.

**Decision:** B. Core encode/policy logic is unit-tested without launching Electron.

## Architecture

```
Settings allowlist + fill_policy (schema)
        → extraction prompt (field specs + speaker legend)
        → MemoExtraction
        → dashboard / extension review (edit + omit)
        → approve (stripped extraction) → HubSpot

Diarized transcript
        → parse turns (JS + Python, including named speakers)
        → dashboard TranscriptConversation (You / María)
        → extraction speaker legend (S1 = rep, S2 = prospect name)

Desktop companion
        → Electron loopback (system) + getUserMedia (mic)
        → PCM 16 kHz AddChannelAudio (prospect, rep)
        → WS /api/v1/transcription/live?mode=copilot_channels
        → You/Them live transcript
        → POST /memos/upload-transcript source_type=meeting_transcript
```

### Field mapping / extraction

- Annotate HubSpot schema properties with `fill_policy` (`identity | strategy | research | call_note | explicit`) using existing `classify_fill_policy`.
- Settings “Field mapping”: selected fields first, policy badges, clearer copy that AI only writes selected fields (call-outcome exception unchanged).
- Dashboard `HubSpotSyncPreview` uses the same omit/edit rules as `chrome-extension/lib/extraction-omit.js` (contact + company + deal; not identity labels, insights, or line items).
- Approve builds extraction via apply-updates + strip-omitted-keys so hiding a row cannot still write the stored value.
- Extraction prompt includes a speaker legend whenever the transcript has diarization labels.

### Speakers

- Port `parseTranscriptTurns`, named-speaker regexes, `speakerSide`, `speakerDisplayLabel`, `firstName` to `src/lib/transcript-turns.ts`.
- Python `transcript_turns.py` gains the same named-speaker parse path.
- `MemoDetail` (and live companion UI) render conversation bubbles, not raw speaker lines.

### Desktop companion ([getvocify-desktop](https://github.com/ToDa-Inc/getvocify-desktop))

- Super-simple Vocify-themed window: login (existing `/auth/login`), Listen, live You/Them transcript, Stop & send to Vocify.
- Main process: tray + always-on-top overlay; `setDisplayMediaRequestHandler` with `audio: 'loopback'` on macOS/Windows. On Linux, native speaker capture modeled on [Anarlog](https://github.com/fastrepl/anarlog): PipeWire `stream.capture.sink`, else PulseAudio `<default-sink>.monitor` (`pw-record` / `parec` / `ffmpeg`), then Chromium share-picker.
- Mac installer: `npm run dist:mac` (unsigned `.dmg` / zip).
- Renderer: mic as `rep`; system audio as `prospect` (native PCM IPC or MediaStream). Dashboard cream/beige UI, live overlay while listening.
- Renderer: mic as `rep`; system audio as `prospect` (native PCM IPC or MediaStream).
- Tokens in `localStorage`. Default API `https://api.getvocify.com/api/v1`, overridable.
- Do **not** vendor Anarlog’s Tauri/Rust tree; Vocify stays Electron + SaaS STT/CRM.

## Error handling

- Schema annotation is additive; old cached schemas without `fill_policy` are classified on read.
- Companion login/upload errors surface in the window; capture failures do not crash the process.
- Review omit is additive to existing approve payload; identity rows stay locked.

## Testing

- Python: named speakers, speaker legend, fill-policy annotation.
- Node: dashboard transcript-turns + extraction-omit ports; desktop PCM/channel/policy helpers.
- Existing chrome-extension `extraction-omit` and `transcript-turns` tests remain the extension contract.
- `vite build` for the dashboard; `node --test` for JS/TS units.

## Isolated units

| Unit | Does | Interface | Depends on |
|------|------|-----------|------------|
| `transcript_turns` (py/ts) | Parse/normalize diarized text; display labels | `parseTranscriptTurns`, `speakerDisplayLabel` | None |
| `extraction_policy` | Classify + annotate fill policy | `classify_fill_policy`, `annotate_schema_fill_policies` | Schema property dicts |
| `extraction-omit` (ts) | Apply/omit proposed CRM fields | `buildApproveExtraction` | Extraction JSON shape |
| `getvocify-desktop` companion | PCM, channels, listen policy, loopback plan | `floatTo16BitPcm`, `encodeChannelAudio`, `canStartListen`, `buildNativeLoopbackPlan` | None |
| `TranscriptConversation` | Render You/Them bubbles | `transcript`, `contactName` | transcript-turns |
