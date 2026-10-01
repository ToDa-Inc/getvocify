# Live call contact: who the rep is calling, as the call starts

Backend/web: branch `feat/live-call-contact` (getvocify, on local `staging`).
Mac app: branch `feat/crm-pages-on-call` (getvocify-desktop).

## The model

**The contact of a call is the CRM record on the rep's screen when it starts.**
An SDR calls from the contact's page, so nothing listens to dialers: it works
with any dialer (Aircall, Ringover, HubSpot calling, a softphone).

```
Mac app — call starts (rep presses record; later: mic detection)
  bridge op crm:pages → active tab of every window of each running browser,
  front window first (macOS automation, one-time consent per browser).
  Only HubSpot / Pipedrive app URLs leave the machine.
        ▼
POST /api/v1/live-calls/start {page_urls, client_capture_id}
  front-most CRM page decides (backend/app/services/live_calls/crm_url.py):
    contact record (same portal)  → contact
    deal / company record         → kept, needs_contact (pick one of its contacts)
    list / sequence / inbox       → needs_contact
    HubSpot calling window        → skipped
  reserves the desktop capture memo WITH hubspot_contact_id + start time
        ▼
desktop shows the contact (or asks) → PATCH /live-calls/current
live help: /copilot/suggest with contact_id (adds the contact's history)
hang-up: POST /live-calls/current/end, POST /captures/{id}/complete with the
live transcript → extraction starts at once (fields, note, coaching, email)
        ▼
HubSpot logs the dialer's call later → linked to that memo, never re-transcribed
```

`GET /api/v1/live-calls/stream` (SSE: snapshot, then every update) and
`/current`; `src/features/calls/useLiveCall.ts` wraps them with `start`,
`pickContact`, `end`. The Chrome extension is not involved.

## No double processing (desktop memo ↔ HubSpot call)

`memos.hubspot_engagement_id` is how every HubSpot call path knows a call
already has a memo (unique index, migration 009): the recordings list shows
that memo and processing reuses it. `app/services/live_calls/linking.py` sets
it on the desktop memo when the HubSpot call shows up:

- **where:** the contact's recordings list (the extension polls it) and
  `initiate_hubspot_call_memo` (auto-sync webhook and the Transcribe button).
- **match:** the rep's own finished (not still recording) `source=desktop`,
  `interaction_kind=call` memo on the same contact, not yet linked, capture
  start within 5 min of the call's `hs_timestamp`; duration breaks ties so an
  answered call beats a no-answer redial. A near-tie links nothing.
- A desktop memo that failed is retried by the normal path with HubSpot's
  recording, so the recording becomes the fallback instead of a duplicate.

No migration: it only uses existing columns.

## Edge cases

| Case | Behaviour |
|---|---|
| HubSpot calling window in front | Skipped; the next window's record counts |
| Several browser windows | Front-most browser first, then front-most window |
| Record is a background tab in its window | Not seen (only active tabs) → needs_contact |
| Deal or company page | `record` kept, `needs_contact: true` → desktop offers its contacts |
| List view, sequence, inbox in front | No contact, even if an older window shows a record |
| Rep opens other records mid-call | Contact fixed at start |
| Record from another portal | Not used (compared with the connected `portal_id`) |
| Browser consent declined | That browser is skipped; `crm:open-automation-settings` opens the pane |
| Browser not running | Never asked, never launched |
| Firefox | No AppleScript support → needs_contact |
| Retried or double start | `start` is idempotent while a call is live |
| Pipedrive | Contact shown live; memos only store HubSpot contact ids |
| Inbound calls, calls from a phone | Not known live; HubSpot's call record links after the call |
| Desktop app dies mid-call | The capture never finishes, so it is never linked; HubSpot's recording is processed as today |

## Hooking it into the desktop recorder (`feat/desktop-meeting-recorder`)

That branch has uncommitted work on the same files, so it was not edited.
In `DesktopMeetingProvider`, on record start:

1. `const { urls } = await window.vocifyDesktop.crm.pages();`
   then `live.start(urls, draftId)` (`useLiveCall`) and use the returned
   `call.memo_id` as the capture; show `call.contact_id` (name from
   `GET /crm/hubspot/contacts/{id}/context`, brief from `GET /briefs`) with a
   "Change" action → `live.pickContact`. When `call.needs_contact`, ask.
2. Live help: pass `contact_id` in `assist/sources.ts`
   (`SuggestRequest.contact_id`).
3. On stop: `POST /captures/{memo_id}/complete` with the transcript and real
   `audio_duration`, then `live.end()`.

## Limits and open items

- Mac only; Windows would need UI Automation.
- Call start comes from the record button; automatic mic detection is being
  built separately (`MicActivityMonitor` in getvocify-desktop).
- The hub is in process memory: correct for the single production instance.
- `/copilot/suggest` strips advice text in call modes by design; contact
  history improves full cards in `meeting` mode, which the recorder uses.

## Found along the way (not changed here)

- `/transcription/live` accepts websocket connections with no auth and trusts
  the `user_id` query param.
- Local `backend/.env` points at the production Supabase (a local backend
  writes to prod) and sets `COPILOT_MODEL=google/gemini-3.5-flash-lite`, which
  rejects `reasoning: disabled`, so live suggestions fail locally.
