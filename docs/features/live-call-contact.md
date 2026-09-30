# Live call contact: who the rep is calling, as the call starts

Branch `feat/live-call-contact` (on top of local `staging`, 2026-10-01).

## What it does

When a rep clicks Call on a HubSpot record and a dialer embedded in HubSpot
(Aircall, Ringover, any app built on HubSpot's Calling Extensions SDK) places
the call, Vocify knows within about a second which HubSpot contact the call is
with. Any client of that rep (the desktop app) receives it live, and
`/copilot/suggest` can coach with what earlier calls with that contact left
behind.

```
HubSpot page (+ embedded dialer iframe)
  dialer ──postMessage──▶ page   OUTGOING_CALL_STARTED {externalCallId, toNumber}
                                 CALL_ANSWERED / CALL_ENDED {callEndStatus, engagementId} / CALL_COMPLETED
  content/hubspot-calling.js (all HubSpot frames) forwards those messages
        ▼
extension service worker (lib/calling-sdk.js)
  call id (synthetic for old SDKs), de-dupe, record = dialer tab's record or
  the HubSpot record tab used last (calling window), reports in order
        ▼
POST /api/v1/live-calls/events
  folds events into one call per rep (app/services/live_calls/state.py)
  contact = contact record the rep was on, else HubSpot phone lookup
        ▼
GET /api/v1/live-calls/stream (SSE: snapshot, then every change) + /current
        ▼
desktop / web: useLiveCall()  (src/features/calls/useLiveCall.ts)
```

## Why this mechanism

- Dialers never send Vocify a webhook, and every dialer differs. But every
  dialer inside HubSpot talks to the HubSpot page with the same SDK messages
  (`@hubspot/calling-extensions-sdk` `src/Constants.ts`, `src/types.ts`; the
  dialer posts to `window.parent`, `IFrameManager.ts`). The extension already
  runs on HubSpot pages, so it can listen without per-dialer code.
- HubSpot's own "call created" webhook (already subscribed in
  `backend/scripts/setup_hubspot_webhooks.py`) is not documented to fire at
  dial time, and HubSpot only links the call to the contact at completion. It
  stays the after-call source of truth.

## Verified

- Backend: `tests/live_calls/*` (state folding, hub, HTTP, stream),
  `tests/copilot/test_contact_history.py`. Full suite green (3652 passed).
- Extension: `lib/calling-sdk.test.js`; full suite green (451).
- Client: `src/lib/live-call.test.ts` (SSE parsing, reconnect/backoff).
- End to end, `scripts/e2e-live-call-hubspot.mjs` (setup in the header): the
  real SDK (HubSpot host side + dialer side, full handshake), the unpacked
  extension in Chromium and this backend. 9/9 on every run:
  dialer on a contact record; dialer nested in a HubSpot frame; legacy SDK
  payload without `externalCallId`; HubSpot's separate calling window (record
  taken from the record tab used last); stream delivers
  dialing → connected → ended → completed in order.
- Contact history in suggestions: a real model call (meeting mode) with and
  without history. With history the card used the CFO decision-maker and the
  repeated price objection from the earlier call, and invented nothing.

**Not verified:** a real Aircall or Ringover account inside a real HubSpot
portal. The SDK source says they must send these messages, but whether they
fill `toNumber` / `externalCallId` is theirs to decide (both are handled:
legacy ids are synthesized; a missing number just skips the phone lookup). To
check in 10 minutes, open HubSpot, DevTools console:

```js
window.addEventListener('message', e => e.data?.type && console.log(e.origin, e.data))
```

Then place one call from a contact and look for `OUTGOING_CALL_STARTED`.

## Hooking it into the desktop recorder (`feat/desktop-meeting-recorder`)

That branch is 500+ commits behind staging and has uncommitted work on the
same files, so it was not edited. After it is rebased:

1. Know the call: in `DesktopMeetingProvider`, `const { call } = useLiveCall();`
   and keep `call?.contact_id` (open or just-ended calls only, via
   `isLiveCallOpen`) as the session contact. Optionally start recording, or
   offer to, when a call opens.
2. Show the contact: `GET /briefs?connection_id=…&contact_id=…` already
   returns the pre-call brief (last conversation, what is pending, what to
   say). `contact_name` is on the live call when it came from the phone lookup;
   otherwise `GET /crm/hubspot/contacts/{id}/context` has name and company.
3. Coach with it: in `assist/sources.ts` add `contact_id` to the
   `streamObjectionSuggestion` body (`SuggestRequest.contact_id`, added on
   this branch). The backend adds the contact's history to the prompt.

## Limits and open items

- **HubSpot only.** Pipedrive's app SDK has no call messages at all (checked
  `@pipedrive/app-extensions-sdk` 0.16.1). Salesforce Open CTI has no "call
  started" method, and it is being retired in Feb 2028. For both, the signal
  would be the open record plus desktop mic detection, confirmed by the rep.
- Calls started outside HubSpot (the dialer's own app or keypad, the Aircall
  click-to-dial extension) are not seen. Desktop mic detection would be the
  fallback; it is not built.
- The live call hub is in process memory: correct for the single production
  instance, and it needs a shared broker if the API ever runs more than one.
- Anyone who can script the HubSpot page can post fake call messages; the
  worst case is a wrong live call for that same signed-in rep.
- `/copilot/suggest` strips advice text in call modes (`speakerphone`,
  `softphone`) by design (`finalize_suggest_result`). Contact history
  improves full cards only in `meeting` mode, which the desktop recorder uses.

## Found along the way (not changed here)

- `/transcription/live` accepts websocket connections with no auth and trusts
  the `user_id` query param.
- Local `backend/.env` sets `COPILOT_MODEL=google/gemini-3.5-flash-lite`,
  which rejects `reasoning: disabled`, so live suggestions fail locally with
  OpenRouter 400. Production logs show no such errors.
