# Call recording playback + channel transcript

**Date:** 2026-09-15  
**Status:** Ready for implementation  
**Surfaces:** memo detail player, `GET /memos/:id`, Vocify/HubSpot call STT, sanitize pipeline (unchanged), accuracy pill

## Decision

Call recordings (Vocify dialer + HubSpot-imported) get a playable file on the memo page and a diarized transcript that comes from **audio channels when we have them**, then the **existing sanitize process**. Voice memos and WhatsApp stay as they are.

Do not invent a second transcript UI. The page shows one transcript: cheap-sanitize first, then Gemini polish when it lands — same as today. Do not disable polish. Do not show `transcript_raw`.

The Francesc memo (`5981ab94-89a7-4fcc-b94a-875c087ae7d8`) is the failure mode: dual-channel WAV exists (or can), STT guessed speakers, fake **95%** badge, Gemini then rewrote Catalan/Spanish into word salad on top of a bad base.

## Product

On `/dashboard/memos/:id` for `vocify_call` and `hubspot_call`:

- Existing player (already in `MemoDetail.tsx`) renders as soon as a recording can be signed. Including `transcribing` / `extracting`.
- Transcript card unchanged: `TranscriptConversation` with You / contact first name from S1/S2.
- Re-transcribe on Vocify calls as well as HubSpot imports (uses stored WAV, not a re-download from Twilio).
- Accuracy pill: real STT mean confidence, or hidden. Never `0.95` / `1.0` defaults.

Out of scope: voice-memo / WhatsApp quality, recordings library redesign, attaching audio into HubSpot (HubSpot already pulls Vocify recordings via the signed public endpoint).

## Why the Francesc page is wrong

1. `memos.audio_url` is written `""` on purpose (`004_audio_url_optional.sql`, upload + call processors). Vocify WAVs live in private `call-recordings` (`outbound_calls.recording_path`). The player keys off `memo.audioUrl` → never shows.
2. Twilio `record-from-answer-dual` and Telnyx `record_channels: dual` already split rep vs prospect. Batch STT still sends `diarize=true` (Deepgram speaker clustering) / Speechmatics `diarization: speaker`. `format_deepgram_transcript` can fall back to `channels[0]` only.
3. `start_extraction_from_transcript(..., transcript_confidence=0.95)` and Speechmatics webhook `0.95` hardcode the pill. Upload-with-transcript writes `1.0`.
4. Sanitize is **not** skipped today. Cheap pass runs before extract; Gemini polish updates the shown transcript in the background. The bug is feeding that pipeline a speaker-guessed, often wrong-language transcript. Keep the process; fix the input.

## Sanitize (do not change)

Order is locked:

1. Provider STT → persist `transcript_raw`.
2. `sanitize_user_transcript` — glossary aliases, S1/S2 canonicalize, spelled emails. No LLM. Extract starts on this text.
3. `schedule_transcript_polish` — Gemini repairs the **display** transcript while status ∈ `{extracting, pending_review, pending_transcript}`. Never writes extraction/CRM fields.

`two_party=True` today only when `source == "hubspot_call"`. Vocify calls are also two-party: pass `two_party=True` for `vocify_call` as well. That is applying the existing process, not a new sanitizer.

## Playback

`audioUrl` in the API is a **signed playback URL**, not a public column.

| Source | File | Sign from |
|---|---|---|
| `vocify_call` | Already uploaded to `call-recordings` | `outbound_calls.recording_path` for `memo_id` |
| `hubspot_call` | Persist the download **before** STT | `call-recordings/{user_id}/hs_{engagement_id}.wav` |

Do not write the signed URL into `memos.audio_url`. Keep that column as-is (WhatsApp public URLs, legacy). Add `memos.recording_path` (nullable text). Vocify processor copies `outbound_calls.recording_path` onto the memo when the WAV lands. HubSpot processor writes the path immediately after download, before `transcribe_bytes`.

`GET /memos/:id` (and list if cheap): if `recording_path` is set, `audioUrl = StorageService.signed_call_recording_url(path, CALL_RECORDING_URL_TTL_SECONDS)`. Else `audioUrl = memos.audio_url` (WhatsApp / legacy). Same TTL / Range / 206 behaviour HubSpot already uses.

Player 403: client already refetches the memo on poll; a stale signature is a refetch. No new refresh endpoint in v1.

Missing path → `audioUrl=""`, player hidden, transcript pipeline unchanged.

## Channel STT

Dual-channel file (Vocify always; HubSpot only if the persisted WAV is stereo):

- Deepgram: `multichannel=true`. **Do not** send `diarize`. Merge channels by utterance start time. Channel 0 → `S1` (rep / caller), channel 1 → `S2` (prospect). Twilio/HubSpot convention: caller on channel 1 = our index 0.
- Speechmatics fallback: `diarization: channel` (not `speaker`).
- Persist `transcript_stt_meta.diarization = "channel"` and `transcript_stt_meta.channels = 2`.

Mono HubSpot imports: keep `diarize` / `diarization: speaker`. `transcript_stt_meta.diarization = "speaker"`.

Detect stereo from WAV header (or known `vocify_call`). If channel STT fails, fall back to today’s speaker-diarize once, then sanitize. Do not fail the memo solely because multichannel 400’d.

Language detect + optional second Deepgram pass (`stt_batch.py`) stay as they are.

## Confidence

`transcribe_bytes` / Deepgram formatter return the mean of utterance `confidence` values in `[0, 1]`. Speechmatics: mean word/phrase confidence when the job JSON has it.

Write `transcript_confidence` **only** when the provider returned a real mean. Otherwise `NULL`.

Remove:

- default `transcript_confidence: float = 0.95` on `start_extraction_from_transcript`
- webhook `"transcript_confidence": 0.95`
- upload-transcript / upload-and-extract `"transcript_confidence": 1.0`

Frontend already hides the pill when `transcriptConfidence` is falsy. `0` must not display as `0%` if we treat it as missing — persist `NULL`, not `0`.

## Re-transcribe

`POST /memos/:id/re-transcribe` today requires `source == "hubspot_call"` and re-downloads from HubSpot.

After this:

- `vocify_call` + `recording_path` → read WAV from `call-recordings`, run channel STT, then existing sanitize + extract + polish.
- `hubspot_call` + `recording_path` → same from stored file (no HubSpot round-trip unless the object is missing).
- `hubspot_call` without path → current HubSpot re-fetch, then persist path.
- Approved memos stay blocked.
- Voice memos still have no file → 400, same as today.

Francesc: if `recording_path` or `outbound_calls.recording_path` exists, re-transcribe after ship. If neither exists, playback and a new transcript are impossible for that row.

## Data flow

```
hangup / HubSpot process
  → WAV in call-recordings, memos.recording_path set
  → GET memo signs audioUrl → player
  → channel (or speaker) STT → transcript_raw + real confidence
  → sanitize_user_transcript → extract
  → schedule_transcript_polish → display transcript
```

## Errors

| Case | Behaviour |
|---|---|
| Sign fails | `audioUrl=""`, log, memo still loads |
| Channel STT fails | One speaker-diarize retry, then sanitize |
| HubSpot download fails | Existing failed memo + error_message |
| Polish rejects / throws | Cheap transcript stays; extract unaffected |
| Expired signed URL | Poll/refetch memo |

## Tests

- Memo GET: `vocify_call` / `hubspot_call` with `recording_path` → `audioUrl` is a signed `call-recordings` URL, column `audio_url` still empty.
- Memo GET: no path → `audioUrl=""`.
- Deepgram formatter: two-channel utterances → `S1`/`S2` interleaved by time; no `diarize` query param when `multichannel`.
- Speechmatics batch config: stereo → `diarization: channel`; mono → `speaker`.
- `transcript_confidence` is the utterance mean or omitted; never 0.95/1.0 from extract/upload/webhook defaults.
- `sanitize_user_transcript` + `schedule_transcript_polish` still invoked in that order on call processors.
- `two_party` true for `vocify_call` and `hubspot_call`.
- Re-transcribe allowed for `vocify_call` with a path; rejected for voice_memo; still rejected when approved.
- MemoDetail: player when `audioUrl` set, including `transcribing`; pill hidden when confidence null.

## UI

No new components. `MemoDetail` player + `TranscriptConversation` stay. Hide the accuracy pill when `transcriptConfidence == null`. Enable the existing re-transcribe control for `source === "vocify_call"` with a recording, not only `isHubSpotCall`.
