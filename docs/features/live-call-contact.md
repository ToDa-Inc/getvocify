# Live call contact: who the rep is calling, as the call starts

Branch `feat/live-call-contact` (on top of local `staging`).

## The model

**The contact of a call is the CRM record the rep had open when it started.**
An SDR calls from the contact's page, so nothing needs to listen to dialers:
it works with any dialer (Aircall, Ringover, HubSpot calling, a softphone).

```
Chrome extension — on every CRM page the rep opens (and a 1-min heartbeat)
  PUT /api/v1/live-calls/presence  {provider, object_type, record_id, account_id}
  (a list/sequence page sends {provider} only: "in the CRM, not on a record";
   HubSpot's calling window is ignored so the record the rep came from stays)
        ▼
Desktop app — call starts (rep presses record, later: mic detection)
  POST /api/v1/live-calls/start {client_capture_id}
    contact = presence if it is a contact record, < 30 min old, same portal
    reserves the desktop capture memo WITH hubspot_contact_id + start time
        ▼
  shows the contact (or asks, when needs_contact) → PATCH /live-calls/current
  live help: /copilot/suggest with contact_id (adds the contact's history)
  hang-up: POST /live-calls/current/end, POST /captures/{id}/complete with the
  live transcript → extraction starts at once (fields, note, coaching, email)
        ▼
HubSpot logs the dialer's call later → linked to that memo, never re-transcribed
```

Clients follow presence + call on `GET /api/v1/live-calls/stream` (SSE:
snapshot, then every update); `src/features/calls/useLiveCall.ts` wraps it
with `start`, `pickContact`, `end`.

## No double processing (desktop memo ↔ HubSpot call)

`memos.hubspot_engagement_id` is how every HubSpot call path knows a call
already has a memo (unique index, migration 009): the recordings list shows
that memo and processing reuses it. `app/services/live_calls/linking.py` sets
it on the desktop memo when the HubSpot call shows up:

- **where:** the contact's recordings list (the extension polls it) and
  `initiate_hubspot_call_memo` (auto-sync webhook and the Transcribe button).
- **match:** the rep's own finished (not still recording) `source=desktop`,
  `interaction_kind=call` memo on the same contact, not yet linked, capture
  start within 5 min of the call's
  `hs_timestamp`; duration breaks ties so an answered call beats a no-answer
  redial. A near-tie links nothing (the old behaviour stays).
- A desktop memo that failed is retried by the normal path with HubSpot's
  recording, so the recording becomes the fallback instead of a duplicate.

No migration: it only uses existing columns.

## Edge cases

| Case | Behaviour |
|---|---|
| Calling window / rep switched tabs | HubSpot calling URLs are ignored; the last record stands |
| Several HubSpot tabs | The active tab's record (last one reported) |
| Deal or company page | `record` kept, `needs_contact: true` → desktop offers its contacts |
| List view, sequence, inbox | Presence cleared to "not on a record" → `needs_contact` |
| Rep opens other records mid-call | Contact fixed at start; presence changes do not move it |
| Record from another portal | Not assigned (compared with the connected `portal_id`) |
| Extension missing / signed out / laptop slept | No or stale (> 30 min) presence → `needs_contact` |
| Retried or double start | `start` is idempotent while a call is live |
| Pipedrive | Contact shown live; memos only store HubSpot contact ids, so not on the memo |
| Inbound calls, calls from a phone | Not known live; HubSpot's call record links after the call |
| Desktop app dies mid-call | The capture never finishes, so it is never linked; HubSpot's recording is processed as today (worst case a duplicate, never a lost call) |

## Verified

- Backend `tests/live_calls/*`: state, hub, HTTP (presence, start with capture
  reservation, portal check, picks reaching the memo, Pipedrive), stream,
  matching (window, redial, ties, races), both linking hooks. Full suite green.
- Extension `lib/presence.test.js`; full suite green.
- Client `src/lib/live-call.test.ts`.
- Real unpacked extension in Chromium against fake HubSpot/Pipedrive pages and
  a stub API (no database): contact, deal, list clears, calling window ignored,
  Pipedrive, non-CRM pages ignored, no resend before heartbeat, alarm
  registered, nothing sent signed out — 10/10.
- On a real HubSpot portal: a call placed with HubSpot calling from a contact
  record runs entirely on that record's page, with the contact id in the URL.

**Not verified:** the desktop side (below) and the linking against a real
HubSpot call record — `hs_timestamp` is documented as the call's time of
creation; dialers that log late would fall outside the 5-min window and keep
today's behaviour.

## Hooking it into the desktop recorder (`feat/desktop-meeting-recorder`)

That branch is far behind staging and has uncommitted work on the same files,
so it was not edited. After it is rebased, in `DesktopMeetingProvider`:

1. `const live = useLiveCall();` On record start: `live.start(draftId)` and use
   the returned `call.memo_id` as the capture (instead of a later
   upload-transcript-and-extract); show `call.contact_id` (name from
   `GET /crm/hubspot/contacts/{id}/context`, brief from `GET /briefs`) with a
   "Change" action → `live.pickContact`. When `call.needs_contact`, ask.
2. Live help: pass `contact_id` in `assist/sources.ts`
   (`SuggestRequest.contact_id`).
3. On stop: `POST /captures/{memo_id}/complete` with the transcript and real
   `audio_duration`, then `live.end()`.

## Limits and open items

- Call start comes from the desktop (record button). Automatic mic detection
  is not built.
- Salesforce has no URL parser in the extension yet.
- The hub is in process memory: correct for the single production instance;
  more than one API process needs a shared broker.
- `/copilot/suggest` strips advice text in call modes by design
  (`finalize_suggest_result`); contact history improves full cards in
  `meeting` mode, which the desktop recorder uses.

## Found along the way (not changed here)

- `/transcription/live` accepts websocket connections with no auth and trusts
  the `user_id` query param.
- Local `backend/.env` points at the production Supabase (so a local backend
  writes to prod) and sets `COPILOT_MODEL=google/gemini-3.5-flash-lite`, which
  rejects `reasoning: disabled`, so live suggestions fail locally.
