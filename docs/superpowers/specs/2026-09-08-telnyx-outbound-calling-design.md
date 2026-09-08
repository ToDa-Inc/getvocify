# Telnyx outbound calling — Design

**Date:** 2026-09-08
**Status:** Design locked from the Twilio-vs-Telnyx evaluation and the current Vocify dialer. Not implemented.
**Supersedes for cost:** [`docs/telephony/DECISION.md`](../../telephony/DECISION.md) said “do not migrate” (2026-08-27) because Spain CLI is law, not carrier. This design is a **cost swap of the same product**, not a CLI fix. Spain BYO-mobile still fails or is suppressed on the handset; that is out of scope.

## Why this exists

Vocify already owns the SDR product: click-to-call in the Chrome extension, server-authoritative caller ID, dual-channel WAV, Deepgram, memos, HubSpot. Twilio is the only production carrier. Telnyx publishes a cheaper Spain mobile termination band ($0.0211–$0.028 vs Twilio $0.0486). Intelligence and transcription stay downstream and are not part of this work.

## Non-goals

- Fixing Spanish CLI / 400-range / TDF 149.
- Replacing STT, extraction, memos, or HubSpot logging.
- Managed Accounts / ISV sub-accounts (Enterprise, $5,000/mo).
- Parallel / power dialer.
- Cutting Twilio out of the codebase on day one.
- Custom-storage-to-our-bucket as a launch blocker (nice later; first ship is download-then-upload like today).

## Approaches considered

| | Approach | Why not / why yes |
|---|---|---|
| A | **TeXML `<Dial>`** — smallest XML diff (`record-from-answer-dual` is the same token) | TeXML `<Dial>` has **no documented recording format**. HubSpot and our STT require WAV. `<Number url>` whisper only lists `<Gather>`/`<Hangup>`. Rejected. |
| B | **Call Control + Park Outbound Calls** (recommended) | Server chooses `from`. `record_format: wav` + `record_channels: dual` are documented. Play-to-PSTN-leg-then-bridge is documented. Webhook Ed25519 signs `timestamp\|body` (URL-safe behind our proxy). |
| C | Hard cutover, delete Twilio | No rollback. First MV3 Telnyx SDK in an offscreen doc is unproven. Rejected. |

**Locked:** Approach B behind `CALLING_PROVIDER=twilio|telnyx`. Default stays `twilio` until the live CDR + handset-CLI gate passes.

## Current system (what we must not break)

```
Extension offscreen
  Twilio.Device.connect({ To, CallerId, ContactId, DealId })
       │  AccessToken identity = Vocify user_id
       ▼
POST /webhooks/twilio/voice   (HMAC over public URL + form)
  identity_from_client_from(From=client:<user_id>)
  resolve_caller_id(user_id, CallerId)   # DB is the only From authority
  INSERT outbound_calls(twilio_call_sid=CallSid)
  return <Dial record="record-from-answer-dual" answerOnBridge>
           <Number url="/whisper">   # AEPD disclosure to callee only
       ▼
POST /webhooks/twilio/recording
  download WAV (Basic auth) → Supabase call-recordings
  initiate_vocify_call_memo → process_vocify_call_background
```

Carrier-agnostic today: E.164 (`twiml.normalize_e164`), `resolve_caller_id`, memo/STT/HubSpot, extension UI (`lib/dialer.js`).

Carrier-locked: `mint_voice_access_token`, TwiML builders, `/webhooks/twilio/*`, `offscreen.js` `Twilio.Device`, columns named `twilio_*`.

## Target flow (Telnyx)

```
Extension offscreen
  TelnyxRTC.connect() + newCall({
    destinationNumber,           # preference only
    customHeaders: [X-Vocify-Caller-Id, X-Vocify-Contact-Id, X-Vocify-Deal-Id]
  })
       │  JWT from POST /v2/telephony_credentials/:id/token
       │  credential sip_username ↔ user_id in user_telephony_credentials
       ▼
Telnyx parks the WebRTC leg (SIP Connection outbound.call_parking_enabled=true)
       ▼
POST /webhooks/telnyx/voice     JSON, Ed25519 over timestamp|raw_body
  event call.initiated / state=parked
  user_id = lookup(sip_username | payload.from)
  to = normalize_e164(payload.to)
  reject emergency destinations (112/911/…) — parking does not apply to them
  caller_id = resolve_caller_id(user_id, X-Vocify-Caller-Id)
  INSERT outbound_calls(carrier='telnyx', carrier_call_id=parked call_control_id, …)
  POST /v2/calls  { connection_id, to, from: caller_id, link_to: parked_id }
       # do NOT set bridge_intent — it overwrites `from` with the parked leg
       ▼
call.answered (PSTN)
  if CALLING_RECORDING_ANNOUNCEMENT_ENABLED:
      speak/play disclosure on the PSTN leg only
      wait call.speak.ended / call.playback.ended
  POST …/actions/bridge on parked id
    record=record-from-answer, record_channels=dual, record_format=wav
       ▼
call.recording.saved
  GET recording download_urls.wav (Bearer, 10 min window)
  same upload → memo → STT path as Twilio
```

Identity is the telephony credential, not a JWT claim the browser can forge. `customHeaders` are correlation only.

## Components

### 1. Provider switch

`CALLING_PROVIDER` is `twilio` or `telnyx`. `telephony_configured()` is true when that provider’s required secrets are set. `/api/v1/calls/config` returns `{ enabled, provider, callerIds, … }`. The extension loads the matching SDK. One process, one provider per environment — no per-call routing in v1.

### 2. Schema

Migration `029_telnyx_carrier.sql`:

- `outbound_calls.carrier TEXT NOT NULL DEFAULT 'twilio'`
- rename `twilio_call_sid` → `carrier_call_id` (no dual-write; update all Python/JS references in the same PR)
- `outbound_calls.provider_state JSONB NOT NULL DEFAULT '{}'` for `{parked_id, pstn_id}`
- `user_caller_ids.verification_sid` replaces `twilio_validation_sid`
- new table `user_telephony_credentials (user_id, provider, credential_id, sip_username UNIQUE)`

HubSpot `hs_call_external_id` continues to store `carrier_call_id` (opaque).

### 3. Telnyx client

Thin `httpx` wrapper + `TELNYX_API_KEY`. No second product SDK required. Endpoints used:

| Purpose | Method |
|---|---|
| Create per-user credential | `POST /v2/telephony_credentials` |
| Mint browser JWT (24 h) | `POST /v2/telephony_credentials/{id}/token` |
| Revoke | `DELETE /v2/telephony_credentials/{id}` |
| Start CLI verify | `POST /v2/verified_numbers` (`verification_method=call`) |
| Confirm code | `POST /v2/verified_numbers/{n}/actions/verify` |
| Dial PSTN | `POST /v2/calls` |
| Speak / play | `POST /v2/calls/{id}/actions/speak` or `playback_start` |
| Bridge + record | `POST /v2/calls/{parked_id}/actions/bridge` |
| Fetch recording | `GET /v2/recordings/{id}` then GET `download_urls.wav` |

Credential is created on first `/calls/config` or `/calls/token` for that user, **never** lazily inside the 5 s settle window of click-to-call if we can avoid it. If missing at token time, create, persist, and still mint (document the rare first-call delay). Subsequent tokens only hit `/token`.

### 4. Webhook auth

Headers `telnyx-signature-ed25519` + `telnyx-timestamp`. Signed message is `{timestamp}|{raw_body}`. Verify with `TELNYX_PUBLIC_KEY` (Ed25519, PyNaCl). Reject if `|now - timestamp| > 300s`. Read `request.body()` once; do not re-serialize JSON.

### 5. Caller ID

Same product: BYO number, `user_caller_ids` remains the authorization table. Telnyx verification is OTP (call or SMS); the UI already shows a code for Twilio’s English keypad call — reuse that surface. `resolve_caller_id` does not change.

Spain +34 verify is **undocumented** at Telnyx. The implementation must treat a Telnyx 4xx on `POST /v2/verified_numbers` as a user-visible failure, not a hang. Live +34 verify is an acceptance gate, not a unit test.

### 6. Extension

No bundler. Vendor `@telnyx/webrtc` `lib/bundle.js` (~274 KB, `globalThis.TelnyxWebRTC`). Classic script in `offscreen.html` next to the Twilio UMD. `offscreen.js` branches on `provider` from the token/config payload.

Use **per-call** remote audio element (Telnyx README: session-level `remoteElement` is clobbered). The offscreen document is already shared with tab/mic capture.

Map events: `telnyx.ready` → device ready; call `state` ringing/active; hangup → `IDLE`. Mute/DTMF via the Telnyx call object.

### 7. Downstream (untouched)

`initiate_vocify_call_memo`, `process_vocify_call_background`, `transcribe_bytes`, HubSpot call log, signed recording URLs. Only the lookup key changes from `twilio_call_sid` to `carrier_call_id`.

## Error handling

| Case | Behavior |
|---|---|
| Bad Ed25519 / stale timestamp | 403, no dial |
| Unknown sip_username | Hang parked call, no PSTN |
| Unverified / missing CLI | Hang parked call |
| Emergency destination | Hang parked call; never dial |
| PSTN no-answer / busy | `log_missed_call_activity` on `call.hangup` with hangup cause; hang parked leg |
| `call.recording.saved` unknown id | 204 + log (same as Twilio) |
| Redelivery with `memo_id` set | 204 |
| Download URL expired | Re-GET `/v2/recordings/{id}` once, then fail the pipeline |

## Testing

- Unit: signature (sign+verify roundtrip + tamper + skew), E.164/emergency reject, `resolve_caller_id` unchanged, webhook state machine with fixture JSON, token mint mocks `httpx`.
- Extension: `node --test` for header building / provider branch; Device lifecycle is manual/MV3.
- Live gate (credentials required, not in CI): Verified L2 account, Park enabled, one +34 mobile verify, one answered call, CDR `cost`, handset CLI, dual WAV channel order, SDC share that month.

## Ops prerequisites (not code)

Telnyx account **Verified (L2)** — Paid caps (5 concurrent, 100/day, 10/hour) cannot run a team. Credential Connection with `outbound.call_parking_enabled=true`, Outbound Voice Profile with ES, webhook `https://{BACKEND_PUBLIC_URL}/webhooks/telnyx/voice`, public key in env. Ask sales in writing: SDC vs unanswered SDR rings; which ES band a +34 CLI hits.

## Success criteria

1. With `CALLING_PROVIDER=telnyx`, an SDR places a call from the extension; callee hears the SDR; dual-channel WAV lands in the existing memo pipeline.
2. Browser cannot present an unverified CLI.
3. Twilio path still works when the flag is `twilio`.
4. No STT/extraction/HubSpot behavior change except the opaque external id.
