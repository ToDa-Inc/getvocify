# Vocify Dialer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development or
> superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** an SDR verifies their phone number once in dashboard Settings, then dials from the
Vocify side panel on any HubSpot record with a real dialer — caller-ID picker, keypad, mute,
live duration, ringing/active states, contact search, post-call processing feedback and call
history. Today there is a one-line dial bar; this plan turns it into the dialer.

---

## What already exists (verified in code, 2026-09-02)

Do not rebuild these. They are shipped and working.

| Thing | Where |
|---|---|
| Twilio Voice JS SDK vendored (UMD) | `chrome-extension/vendor/twilio-voice-2.18.3.min.js` |
| Device lifecycle, connect, hangup | `chrome-extension/offscreen.js:306-368` |
| Call state machine (5 states) | `chrome-extension/lib/dialer.js:11-17` |
| Mic mutual exclusion (call ↔ memo ↔ Listen) | `dialer.js:50-61`, `lib/tab-capture.js:9-25`, enforced `background.js:386-393,676-708,877-883` |
| `startCallFlow` / `hangupCallFlow` | `background.js:877-917` |
| Minimal dial bar (input + select + button) | `popup/index.html:47-65`, `popup/popup.js:2903-3001` |
| `GET /calls/config`, `POST /calls/token`, `GET /calls/caller-ids`, `POST /calls/caller-ids` | `backend/app/api/calls.py` |
| Caller-ID verification against Twilio | `backend/app/services/telephony/caller_id.py` |
| TwiML `<Dial record="record-from-answer-dual">` + whisper | `backend/app/services/telephony/twiml.py` |
| Voice / whisper / recording / caller-id-status webhooks | `backend/app/api/webhooks.py:616-790` |
| `user_caller_ids` + `outbound_calls` tables | `backend/migrations/025_outbound_calling.sql` |
| Recording → Supabase → STT → extraction → HubSpot call engagement | `services/telephony/call_processor.py`, `services/hubspot/call_log.py` |
| HubSpot contact search (`GET /crm/hubspot/search/contacts?q=`) | `backend/app/api/crm.py:1009-1032`, extension msg `SEARCH_CONTACTS` (`background.js:1119-1123`) |
| `contactPhone` in page context | `crm.py:343-403`, `lib/page-scope.js:17-28` |

## The real blocker (not code)

Nothing dials because the five Twilio settings are unset. `telephony_configured()` is false, so
`GET /calls/config` returns `enabled: false`, so `renderCallSection` hides the whole section
(`popup.js:2922-2924`). **Phase 0 must happen before any of this is testable.**

## Gaps this plan closes (each verified as absent)

1. **Only one number can ever be added.** `#caller-id-setup` is hidden the moment one number is
   verified (`popup.js:2929`) — there is no second-number path and no delete.
2. **No way to set the default caller ID.** `user_caller_ids.is_default` exists and
   `resolve_caller_id` reads it (`caller_id.py:167`) but no API writes it.
3. **Verification feedback is a 20-second `setTimeout`** (`popup.js:2997`), not a poll.
4. **No keypad.** `sendDigits` is never called — IVRs, extensions and "marque 1" are dead ends.
5. **No mute.** `call.mute()` is never called.
6. **No duration.** Nothing records when the call was answered.
7. **No progress feedback.** `#call-status` only renders `call.error` (`popup.js:2951-2953`).
8. **Prefill is sticky.** `input.value` is only set when empty (`popup.js:2947`), so moving from
   contact A to contact B keeps A's number in the box.
9. **Nothing after hangup.** `state.call.to` is cleared on idle; the memo is created server-side
   so the extension never learns its id. `watchingForRecording` is dead — it is only ever set to
   `false` (`background.js:64,268-270,1210,1220,1228,1231,1237,1274`).
10. **No call history.** `outbound_calls` has no read API and no UI anywhere.
11. **Device is destroyed and recreated per call** (`offscreen.js:313-320`), adding registration
    latency to every dial in a sequence.

---

## Architecture decisions

**Two surfaces, split by frequency.** Number management (add, verify with a code, wait ~60s,
set default, delete) is once-per-quarter setup with a keypad code to type — it goes in the
dashboard Settings page where there is room. Dialing is per-minute work in context — it stays in
the side panel. The side panel's "Añadir número" opens the Settings page in a new tab rather
than duplicating the verification flow.

**Follow the WhatsApp phone precedent, do not merge with it.** `user_profiles.phone`
(`ProfilePage.tsx:97-107` → `PATCH /api/v1/auth/me` → unique partial index at
`full_reset.sql:391-393`) is the WhatsApp sender identity and is looked up by exact match in
`whatsapp/processor.py:701-715`. `user_caller_ids.phone_number` is a Twilio-verified calling
identity. They are different lifecycles. The new Settings card **prefills** from
`user_profiles.phone` and offers one-click "verificar este número para llamar" — it does not
write to `user_profiles`.

**No sixth phone normalizer.** Five already exist (`auth.py:33-40`,
`whatsapp/processor.py:89-96`, `unipile/webhook_parser.py:34-37`, `hubspot/search.py:24-25`,
`telephony/twiml.py:42-66` mirrored in `lib/dialer.js:27-47`). The dashboard sends the raw string
and renders the E.164 that `POST /calls/caller-ids` returns, exactly as `PATCH /auth/me` behaves.

**Call correlation.** The offscreen document reads `activeCall.parameters.CallSid` after connect
and reports it upward, so the extension can poll `GET /calls/{sid}` for post-call status. Task 12
verifies this equals `outbound_calls.twilio_call_sid` against a live call before anything depends
on it, with a `?limit=1` history fallback if it does not.

## Global constraints

- **No bundler in the extension.** Plain ES modules, `scripts/package-chrome-extension.sh`
  rsyncs raw source. Nothing new gets compiled.
- **The client never chooses its own `From`.** `resolve_caller_id` (`caller_id.py:148-175`) is
  the only authority. Nothing in this plan may weaken that.
- **`record-from-answer-dual` stays.** HubSpot's transcription requires caller on channel 1.
- Mic mutual exclusion must keep holding: a dialer that grabs the mic mid-memo is a regression.
  Every new entry point re-uses `canStartCall` / `canStartTabCapture`.
- Backend tests: `cd backend && python -m pytest tests/test_<file>.py -v`.
  Extension tests: `cd chrome-extension && node --test lib/<file>.test.js`.
  Full: `make test`, `make test-js`.
- New Settings components copy `TranscriptionLanguageSettings.tsx:24-146` (useEffect load,
  `isLoading`/`isSaving`, toast, `THEME_TOKENS.cards.base` shell, `rounded-full bg-beige` button).
- `outbound_calls` and `user_caller_ids` have RLS enabled with **no policies**
  (`025_outbound_calling.sql:70-71`), i.e. deny-all except service role. All dashboard reads go
  through FastAPI, never through the Supabase anon client.

## Out of scope, with reasons

- **Call disposition / outcome UI.** Commit `8483506` deliberately removed the call-outcome and
  `lost_reason` fields from the popup and from `APPROVE_SYNC`. Do not reintroduce them.
- **Power dialing / call lists / auto-advance.** Needs a queue model; separate plan.
- **Inbound calls and callbacks.** The access token is outgoing-only
  (`calls.py:60-63`, `incoming_allow` stays false).
- **Salesforce.** HubSpot only.
- **Carrier change (Telnyx) and the Spanish CLI question.** Tracked in
  `docs/telephony/DECISION.md` and `2026-08-27-spain-cli-remediation.md`. This plan is
  carrier-agnostic above `offscreen.js`; it neither fixes nor worsens that.

## File map

**Create**

- `backend/app/api/calls.py` additions (no new file)
- `backend/migrations/026_dialer.sql`
- `backend/tests/test_calls_caller_id_management.py`
- `backend/tests/test_calls_history.py`
- `chrome-extension/lib/call-format.js`
- `chrome-extension/lib/call-format.test.js`
- `src/features/calls/api.ts`
- `src/features/calls/types.ts`
- `src/components/dashboard/settings/CallerIdSettings.tsx`

**Modify**

- `backend/app/config.py` — `CALLING_RECORDING_ANNOUNCEMENT_ENABLED`
- `backend/app/services/telephony/caller_id.py` — set-default, delete, single-number read
- `backend/app/services/telephony/twiml.py` — optional whisper
- `backend/app/api/webhooks.py` — pass the flag through; persist `answered_at`
- `backend/tests/test_telephony_twiml.py`, `backend/tests/test_telephony_caller_id.py`
- `chrome-extension/lib/dialer.js` — mute/DTMF gates
- `chrome-extension/lib/dialer.test.js`
- `chrome-extension/offscreen.js` — mute, `sendDigits`, CallSid, device reuse, token refresh
- `chrome-extension/background.js` — richer `state.call`, post-call watch, new messages
- `chrome-extension/lib/api.js` — `getCall`, `getCallHistory`, caller-ID mutations
- `chrome-extension/popup/index.html` — the dialer markup
- `chrome-extension/popup/popup.js` — dialer wiring
- `chrome-extension/popup/styles.css` — dialer styles
- `src/pages/dashboard/SettingsPage.tsx` — mount the new card
- `.env.example`, `docs/runbooks/twilio-setup.md`

---

## Phase 0 — Turn it on

### Task 0: Twilio credentials and TwiML App

No code. Blocks everything. Follow `docs/runbooks/twilio-setup.md`.

- [ ] Create the Twilio account (any billing country; Spanish registration is not required to
      place outbound calls or to verify a caller ID).
- [ ] Set in `.env`: `TWILIO_ACCOUNT_SID`, `TWILIO_API_KEY_SID`, `TWILIO_API_KEY_SECRET`,
      `TWILIO_TWIML_APP_SID`, `TWILIO_AUTH_TOKEN`, and confirm `BACKEND_PUBLIC_URL` is a
      publicly reachable HTTPS origin (ngrok/tunnel in dev — Twilio must reach the webhooks).
- [ ] Apply `backend/migrations/025_outbound_calling.sql` if not already applied. Verify:
      `select 1 from user_caller_ids limit 1;` and the `call-recordings` bucket exists and is
      private.
- [ ] Point the TwiML App's Voice URL at `{BACKEND_PUBLIC_URL}/webhooks/twilio/voice` (POST).
- [ ] Restart the API and confirm `GET /api/v1/calls/config` returns `enabled: true`.
- [ ] Verify one number end to end through the existing side-panel UI and place one real call.
      **Record what `activeCall.parameters.CallSid` is and compare it to the
      `outbound_calls.twilio_call_sid` row** — Task 12 depends on the answer.
- [ ] Complete the runbook's outstanding "Recording endpoint registration" step (HubSpot
      `calling_settings` recording endpoint) or note explicitly that recordings will not play
      inside HubSpot until it is done.

---

## Phase 1 — Backend APIs the dialer needs

### Task 1: Caller-ID management (default, delete, single read)

**Files:** modify `backend/app/services/telephony/caller_id.py`, `backend/app/api/calls.py`;
create `backend/tests/test_calls_caller_id_management.py`; modify
`backend/tests/test_telephony_caller_id.py`.

**Interfaces produced:**
- `set_default_caller_id(supabase, user_id, phone_number) -> bool`
- `delete_caller_id(supabase, user_id, phone_number) -> bool`
- `get_caller_id(supabase, user_id, phone_number) -> dict | None`
- `PATCH /api/v1/calls/caller-ids/{phone_number}` body `{ isDefault?: bool, label?: str }`
- `DELETE /api/v1/calls/caller-ids/{phone_number}`

- [ ] **Step 1: failing tests.** Cover: setting a default clears any other default for the same
      user and touches no other user's rows; setting a default on a `pending` row is rejected
      (400) because `resolve_caller_id` only reads `verified`; deleting a number the user does
      not own returns 404 and deletes nothing; deleting the current default leaves the user with
      no default and `resolve_caller_id` still resolves via the `order(is_default desc)` fallback
      (`caller_id.py:167`); label update does not reset `status` or `verified_at`.
      Use the `FakeQuery` from the existing telephony tests — it applies `.eq()` filters against
      its data, so cross-tenant assertions are meaningful.
- [ ] **Step 2:** implement. `set_default_caller_id` does two updates: clear
      `is_default=false where user_id=? and is_default=true`, then set `is_default=true where
      user_id=? and phone_number=? and status='verified'`; return false if the second matched
      nothing. Path params are normalized with `normalize_e164` before matching, so `+34 600...`
      and `+34600...` hit the same row. URL-encode in the client.
- [ ] **Step 3:** wire the routes with `get_user_id`, 404 on no match, `telephony_configured()`
      guard only on routes that call Twilio (delete and patch do not).
- [ ] **Step 4:** `python -m pytest tests/test_calls_caller_id_management.py tests/test_telephony_caller_id.py -v`

### Task 2: Call history and per-call read

**Files:** modify `backend/app/api/calls.py`; create `backend/migrations/026_dialer.sql`,
`backend/tests/test_calls_history.py`.

**Interfaces produced:**
- `GET /api/v1/calls/history?limit=20&contactId=&dealId=` → `{ calls: CallSummary[] }`
- `GET /api/v1/calls/{call_sid}` → `CallSummary`

`CallSummary`: `{ callSid, to, from, contactId, dealId, engagementId, status, startedAt,
answeredAt, durationSeconds, memoId, memoStatus, errorMessage }`.

- [ ] **Step 1: migration `026_dialer.sql`.** Add `answered_at TIMESTAMPTZ` to `outbound_calls`
      (the existing `recording_duration` is the *recording* length, which starts at answer and
      is unknown until the recording callback fires minutes later — the dialer needs the answer
      timestamp at answer time). Add
      `CREATE INDEX idx_outbound_calls_contact ON outbound_calls (user_id, hubspot_contact_id, created_at DESC)`.
      Wrap in `BEGIN/COMMIT`, use `IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS`.
- [ ] **Step 2: failing tests.** History is scoped to `user_id` and never leaks another user's
      calls; `limit` is clamped (1..100); filters compose; `memoStatus` comes from a join on
      `memos` and is null when `memo_id` is null; unknown `call_sid` → 404; a `call_sid`
      belonging to another user → 404, not 403 (do not confirm existence).
- [ ] **Step 3:** implement with a single `select` plus the memo join
      (`memos(id,status)` via the FK, or a second query keyed on the collected `memo_id`s if the
      client's join syntax is awkward — prefer whichever matches existing code in
      `backend/app/api/memos.py`).
- [ ] **Step 4:** `python -m pytest tests/test_calls_history.py -v`

### Task 3: Make the recording announcement optional

The user's position is that the disclosure is not needed for this use case. Make it a
deployment switch rather than deleting the code. *One-line note, not a debate: recording without
notice carries RGPD/AEPD exposure independent of the CLI question in `docs/telephony/`; this flag
is where that decision is expressed.*

**Files:** modify `backend/app/config.py`, `backend/app/services/telephony/twiml.py`,
`backend/app/api/webhooks.py`, `backend/tests/test_telephony_twiml.py`, `.env.example`.

- [ ] **Step 1: failing test.** `build_outbound_twiml(..., whisper_url=None)` produces
      `<Number>+34...</Number>` with no `url` attribute, and everything else (caller ID,
      `record="record-from-answer-dual"`, `answerOnBridge`, the recording callback) is byte-for-byte
      identical to the whisper case. Assert on the XML string.
- [ ] **Step 2:** change `whisper_url: str` to `whisper_url: str | None = None` and call
      `dial.number(to)` without `url` when it is falsy (`twiml.py:97`).
- [ ] **Step 3:** add `CALLING_RECORDING_ANNOUNCEMENT_ENABLED: bool = False` to `Settings`
      (default off, per the decision above) and gate the `whisper_url` the voice webhook passes.
      Leave `/webhooks/twilio/whisper` mounted so flipping the flag needs no redeploy of routes.
- [ ] **Step 4:** `python -m pytest tests/test_telephony_twiml.py tests/test_telephony_webhook.py -v`

---

## Phase 2 — The dialer in the side panel

### Task 4: Offscreen — mute, DTMF, CallSid, device reuse

**Files:** modify `chrome-extension/offscreen.js`.

`offscreen.js` has no unit tests (it needs `globalThis.Twilio` and DOM); its logic must stay thin
and every decision must live in `lib/dialer.js` or `lib/call-format.js` where it is testable.

- [ ] **Step 1: report the CallSid.** After `twilioDevice.connect()` resolves, read
      `activeCall.parameters?.CallSid` and include it in the `CALL_STATE` message for
      `connecting`, and again on `accept`. Extend `reportCallState(state, error, extra)` to merge
      an object rather than growing positional args.
- [ ] **Step 2: `answeredAt`.** On the `accept` handler, send `answeredAt: Date.now()` with the
      `active` state. This is the client-side clock and drives only the UI timer; the billable
      truth stays server-side.
- [ ] **Step 3: mute.** Handle `{ target:'offscreen', type:'MUTE_CALL', muted }` →
      `activeCall.mute(Boolean(muted))`, then report the state again with
      `muted: activeCall.isMuted()`. Read back from the SDK rather than echoing the request.
- [ ] **Step 4: DTMF.** Handle `{ target:'offscreen', type:'SEND_DIGITS', digits }` →
      reject anything not matching `/^[0-9*#]+$/`, then `activeCall.sendDigits(digits)`. No state
      change is reported; the UI echoes locally.
- [ ] **Step 5: device reuse.** Stop destroying the Device on every call. Create it on the first
      `START_CALL` and keep it; on later calls reuse it and call `twilioDevice.updateToken(token)`
      first (background sends a fresh token each dial already — `background.js:890`). Wire
      `twilioDevice.on('error', ...)` → report `idle` with the message, and
      `twilioDevice.on('tokenWillExpire', ...)` → `chrome.runtime.sendMessage({ type:'CALL_TOKEN_REFRESH_REQUEST' })`.
      Destroy the Device only on an unrecoverable device error or when the offscreen document is
      torn down — not in `hangupCall`.
- [ ] **Step 6: manual verification.** Two consecutive calls without reloading the extension; the
      second must connect noticeably faster and must not throw "Device destroyed".

### Task 5: Pure dialer helpers

**Files:** create `chrome-extension/lib/call-format.js` + `.test.js`; modify
`chrome-extension/lib/dialer.js` + `.test.js`.

**Interfaces produced (all pure):**
- `formatCallDuration(ms) -> "0:07" | "12:03" | "1:02:11"`
- `describeCallState({ state, to, answeredAt, now, muted }) -> string` (Spanish, matching the
  existing tone of `callButtonLabel`)
- `canSendDigits(callState) -> boolean` (active only)
- `canMute(callState) -> boolean` (active only)
- `shouldPrefillNumber({ currentValue, prefilledFrom, contactId, contactPhone }) -> string | null`

- [ ] **Step 1: failing tests.** `formatCallDuration`: 0, 7s, 59s, 60s, 3661s, negative → `"0:00"`,
      non-finite → `"0:00"`. `shouldPrefillNumber` is the fix for gap 8: returns the new phone
      when `contactId` differs from `prefilledFrom`; returns `null` when the user has typed
      something the prefill did not put there; returns `null` when the contact is unchanged.
      `canSendDigits`/`canMute` false for every state except `active`.
- [ ] **Step 2:** implement. Keep `dialer.js` free of `chrome.*` and Twilio, as its header states.
- [ ] **Step 3:** `node --test lib/call-format.test.js lib/dialer.test.js`

### Task 6: Background — richer call state and post-call watch

**Files:** modify `chrome-extension/background.js`, `chrome-extension/lib/api.js`.

- [ ] **Step 1: extend `state.call`.** From `{ state, to, callerId, error }` to
      `{ state, to, callerId, error, callSid, answeredAt, muted, contactId, dealId }`. Keep using
      `updateState({ call: {...} })` with a whole replacement object — the broadcast path depends
      on it. Carry `contactId`/`dealId` from `startCallFlow`'s existing context read
      (`background.js:903-904`) so the post-call card knows who was called.
- [ ] **Step 2: new messages.** `MUTE_CALL` and `SEND_DIGITS` forward to offscreen;
      `CALL_TOKEN_REFRESH_REQUEST` mints a new token via `api.createVoiceToken()` and posts
      `{ target:'offscreen', type:'UPDATE_TOKEN', token }`.
- [ ] **Step 3: `lastCall`.** On the `active → idle`/`ending → idle` transition, snapshot
      `state.lastCall = { callSid, to, contactId, dealId, answeredAt, endedAt, durationMs, memoId: null, memoStatus: null, processing: true }`
      before clearing `state.call`. If the call never reached `active`, set `processing: false`
      and `outcome: 'no_answer'` — there will be no recording, so nothing will ever arrive.
- [ ] **Step 4: post-call polling.** When `lastCall.processing` and `callSid` is known, poll
      `api.getCall(callSid)` every 3s for up to 4 minutes (recording callbacks arrive after the
      call ends, then STT runs). Stop on `status: 'logged'` or `'failed'`, or on timeout. Update
      `lastCall.memoId`/`memoStatus` on each tick. Reuse the `clearMemoPoll` interval discipline
      at `background.js:273-278` — one timer, always cleared, and cleared when a new call starts.
- [ ] **Step 5: api.js.** Add `getCall(sid)`, `getCallHistory(params)`, `setDefaultCallerId`,
      `deleteCallerId` mirroring the existing method style in `lib/api.js`.
- [ ] **Step 6:** `node --test` for any pure helper extracted here; the message routing is
      verified manually in Task 12.

### Task 7: The dialer UI

**Files:** modify `chrome-extension/popup/index.html`, `popup/popup.js`, `popup/styles.css`.

Replace the `#call-section` block at `index.html:47-65`. Target markup:

```html
<section id="call-section" class="dialer" hidden>
  <div class="dialer-to">
    <input id="call-number" type="tel" inputmode="tel" placeholder="+34 600 111 222" />
    <button id="call-contact-search-toggle" type="button" title="Buscar contacto">Buscar</button>
  </div>
  <div id="call-contact-results" class="dialer-results" hidden></div>

  <div class="dialer-from">
    <label for="call-caller-id">Desde</label>
    <select id="call-caller-id"></select>
    <button id="call-add-number" type="button" class="link-button">Añadir número</button>
  </div>

  <div id="call-live" class="dialer-live" hidden>
    <span id="call-state-label"></span>
    <span id="call-timer" class="dialer-timer">0:00</span>
    <button id="call-mute" type="button" aria-pressed="false">Silenciar</button>
    <button id="call-keypad-toggle" type="button" aria-expanded="false">Teclado</button>
  </div>
  <div id="call-keypad" class="dialer-keypad" hidden></div>

  <button id="call-button" type="button" class="dialer-action">Llamar</button>
  <p id="call-status" class="call-status" hidden></p>
  <div id="call-postcall" class="dialer-postcall" hidden></div>
</section>
```

- [ ] **Step 1: always show the section when calling is configured.** Keep the
      `!callingConfig.enabled` early return, but when `enabled` is true and there are zero
      verified numbers, render an inline empty state — "Verifica tu número para llamar" plus the
      "Añadir número" button — instead of today's inline verification form. Delete
      `#caller-id-setup`, `#caller-id-number`, `#caller-id-verify`, `#caller-id-code` and
      `handleVerifyCallerId` (`popup.js:2983-3001`); that flow moves to Settings in Task 9.
- [ ] **Step 2: "Añadir número"** → `chrome.tabs.create({ url: <dashboard>/dashboard/settings })`.
      Take the dashboard origin from wherever the extension already derives it (check
      `lib/api.js` / `lib/config.js`); do not hardcode a URL.
- [ ] **Step 3: caller-ID select always visible** when at least one number is verified, showing
      `label || phoneNumber`, defaulting to `isDefault`. Persist the user's last manual choice in
      `chrome.storage.local` and restore it, so a second number is not re-picked every dial.
- [ ] **Step 4: prefill via `shouldPrefillNumber`** from Task 5, keyed on
      `lastBgState.context.contactId`, replacing `popup.js:2946-2949`. Track `prefilledFrom` in a
      module-level variable, not in the DOM.
- [ ] **Step 5: live block.** Show `#call-live` for `connecting|ringing|active|ending`. Render
      `describeCallState(...)` into `#call-state-label`. Start a 1s `setInterval` when
      `state === 'active'` that writes `formatCallDuration(Date.now() - answeredAt)` into
      `#call-timer`; clear it on every other state and on `visibilitychange` hidden. The timer
      derives from `answeredAt` in background state, so closing and reopening the side panel mid
      call resumes at the correct time.
- [ ] **Step 6: mute** toggles `aria-pressed`, sends `MUTE_CALL`, and renders from
      `lastBgState.call.muted` (the SDK read-back), never from local optimistic state.
- [ ] **Step 7: keypad.** 12 buttons (1-9, *, 0, #) generated in JS. Click appends to a local
      echo string shown in `#call-state-label` and sends `SEND_DIGITS` with the single digit.
      Enabled only when `canSendDigits(call.state)`. Also accept keydown of `0-9*#` while
      `#call-keypad` is open.
- [ ] **Step 8: contact search.** Reuse the existing `SEARCH_CONTACTS` message
      (`background.js:1119-1123`) and copy the debounce pattern from the review-panel picker
      (`popup.js:2744-2788`). Render name + company + phone; clicking one fills `#call-number`
      with its phone and sets `prefilledFrom` to that contact id so Step 4 does not clobber it.
      Skip results without a phone.
- [ ] **Step 9: status line.** `#call-status` now renders both errors (red) and non-error
      progress. Keep `call.error` red; use a muted style otherwise.
- [ ] **Step 10: CSS.** Extend the existing block at `styles.css:1699-1790`. Match the current
      pill inputs and beige-dark action button. Keypad is a 3-column grid of round buttons.
      Nothing may push the record button below the fold — check at the side panel's minimum width.
- [ ] **Step 11:** manual pass through every state with the mic mutual-exclusion cases: start a
      memo then try to call, start a call then try to record, start Listen then try to call. Each
      must show the Spanish reason from `canStartCall` / `canStartTabCapture`, not fail silently.

### Task 8: Post-call card, and remove the dead watch indicator

**Files:** modify `chrome-extension/popup/index.html`, `popup/popup.js`, `background.js`.

- [ ] **Step 1: render `#call-postcall`** from `lastBgState.lastCall`:
      answered → "Llamada de 4:12 · transcribiendo…" with a spinner; then
      `memoStatus` ready → "Listo para revisar" with a button that opens the review panel through
      the existing `openReviewFromMemo` path; `failed` → the error plus a retry affordance;
      never answered → "Sin respuesta" plus "Reintentar" that redials the same number.
- [ ] **Step 2: dismissible.** An × clears `lastCall` in background state. It must also clear
      when a new call starts or the user navigates to a different HubSpot record.
- [ ] **Step 3: delete the dead indicator.** Remove `#call-watch-indicator`
      (`index.html:67-71`), its CSS, `state.watchingForRecording` (`background.js:64`) and every
      `watchingForRecording: false` assignment (`background.js:268-270,1210,1220,1228,1231,1237,1274`)
      and its popup read (`popup.js:793`). Confirm with a grep that no reader remains before
      deleting the writers.
- [ ] **Step 4:** `make test-js`.

---

## Phase 3 — Dashboard number management

### Task 9: `CallerIdSettings` card

**Files:** create `src/features/calls/api.ts`, `src/features/calls/types.ts`,
`src/components/dashboard/settings/CallerIdSettings.tsx`; modify
`src/pages/dashboard/SettingsPage.tsx`.

Copy the shell of `TranscriptionLanguageSettings.tsx:24-146` exactly — same card wrapper, same
`isLoading`/`isSaving` pattern, same toast calls, same button classes.

- [ ] **Step 1: `api.ts`.** `getCallingConfig`, `addCallerId`, `setDefaultCallerId`,
      `deleteCallerId`, using the shared `api` client from `src/shared/lib/api-client.ts`
      (bearer token and base URL are handled there). No client-side phone normalization — send
      the raw string, render the returned `phoneNumber`.
- [ ] **Step 2: the list.** One row per number: E.164, label, a "Predeterminado" badge or a
      "Hacer predeterminado" button, a status pill (`pending` / `verified` / `failed`), and a
      delete button with a confirm. Empty state explains what a caller ID is in one sentence.
- [ ] **Step 3: add + verify.** An input plus "Verificar". On submit, show the returned
      `verificationCode` **large and persistent** with the instruction: Twilio llamará a ese
      número, en inglés, desde un número de Estados Unidos; teclea el código. Handle
      `alreadyVerified: true` (no code is returned — do not render `null`, that bug already
      happened once in the side panel).
- [ ] **Step 4: poll, do not `setTimeout`.** While any row is `pending`, re-fetch
      `GET /calls/caller-ids` every 3s for up to 120s, then stop and show "La verificación ha
      caducado. Inténtalo de nuevo." Clear the interval on unmount.
- [ ] **Step 5: prefill from the WhatsApp number.** Read `user?.phone` from `useAuth()`. If it is
      set and is not already in the caller-ID list, show "Usar +34… (tu número de WhatsApp)" as a
      one-click fill of the input. It does not auto-submit and it does not modify
      `user_profiles`.
- [ ] **Step 6: disabled state.** When `config.enabled` is false, render the card with an
      explanatory line ("Las llamadas no están configuradas en este entorno") rather than hiding
      it, so the state is diagnosable. Surface `hubspotLogging: false` as a warning line — calls
      will still work but will not land in HubSpot.
- [ ] **Step 7: mount** in `SettingsPage.tsx` after `TranscriptionLanguageSettings`
      (`SettingsPage.tsx:81-83`), inside the same `space-y-8` stack.
- [ ] **Step 8:** `make test-js`, plus a manual pass: add, verify, set default, delete, and
      confirm the side panel picks up the change on its next `GET_CALLING_CONFIG`.

### Task 10: Call history view (do last)

**Files:** modify `chrome-extension/popup/popup.js`; optionally create a dashboard panel.

- [ ] **Step 1: side panel.** When the current record has calls, add Vocify outbound calls from
      `GET /calls/history?contactId=…` into the existing merged activity list
      (`renderRecordingsSection`, `popup.js:779-868`) rather than building a second list. Row
      shows time, duration, and either "Revisar" (memo ready) or the processing state.
- [ ] **Step 2: redial** from a history row, prefilling the number and caller ID used.
- [ ] **Step 3 (optional): dashboard.** `RecordingsPanel.tsx` currently shows HubSpot calls only.
      Adding a Vocify-calls tab is a separate, self-contained change — defer unless asked.

---

## Phase 4 — Verification

### Task 11: Regression suite

- [ ] `cd backend && make test`
- [ ] `make test-js`
- [ ] Grep that `resolve_caller_id` is still the only writer of `From` and that no new code path
      passes a client-supplied caller ID to Twilio unchecked.
- [ ] Confirm the three mic mutual-exclusion pairs still block in both directions.

### Task 12: Live call verification

The parts that cannot be unit tested. Do these on a real call, and write the results into
`docs/runbooks/twilio-setup.md`.

- [ ] `activeCall.parameters.CallSid` **equals** `outbound_calls.twilio_call_sid`. If it does
      not, switch the post-call poll in Task 6 Step 4 to `GET /calls/history?limit=1` filtered by
      `to`, and record the discrepancy in the runbook.
- [ ] DTMF reaches an IVR (call a number with a menu and press a digit).
- [ ] Mute actually mutes (confirm from the far end, not from the UI).
- [ ] The timer matches the far end's wall clock within a second or two.
- [ ] Two back-to-back calls work on a reused Device.
- [ ] With `CALLING_RECORDING_ANNOUNCEMENT_ENABLED=false` the prospect hears no disclosure and
      the recording is still dual-channel — pull the WAV and confirm two channels.
- [ ] The call appears in HubSpot with playable audio, and the memo reaches review.
