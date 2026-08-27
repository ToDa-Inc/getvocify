# Vocify Outbound Calling — Carrier Portability Report

**Scope:** `/Users/danizal/getvocify` (`main`), outbound calling feature merged via Twilio.  
**Question:** What is coupled to Twilio, and what would a Telnyx swap cost?

---

## Executive summary

| Bucket | Approx. lines (production) | What it is |
|--------|------------------------------|------------|
| **CARRIER-AGNOSTIC** | **~970** | E.164 normalization, caller-ID authorization against DB, memo/STT/extraction pipeline, HubSpot logging, Supabase storage, extension UI/orchestration |
| **CARRIER-SHAPED** | **~650** | TwiML generation, webhook signature verification, AccessToken minting, caller-ID verification API, recording download auth, `/webhooks/twilio/*` routes |
| **CARRIER-LOCKED** | **~65 + 302KB SDK** | `Twilio.Device` lifecycle in offscreen doc + vendored `twilio-voice-2.18.3.min.js` |

**Schema verdict:** Migration **recommended** (column names and index semantics are Twilio-branded), but a **minimal swap could reinterpret** `twilio_call_sid` / `twilio_validation_sid` as opaque carrier IDs without renaming if you accept misleading names and update application code only.

**Provider abstraction now vs later:** **Later.** There is one carrier in production; seams are partially natural (`telephony/` package) but routes, DB columns, tests, and the browser SDK are all Twilio-shaped. Building a dual-carrier interface before a committed second carrier is speculative work (~650 shaped lines + new Telnyx implementation + ~65 locked lines rewritten).

---

## 1. Three-way classification (calling-related modules)

Line counts are **approximate production code** (tests and the 302KB minified vendor blob counted separately). Mixed files are split by responsibility.

### Backend — `app/services/telephony/`

| File | Bucket | Lines (approx.) | Notes |
|------|--------|-----------------|-------|
| `twiml.py` | **AGNOSTIC** | 43 | `normalize_e164`, `InvalidPhoneNumber`, `E164_RE`, `DEFAULT_RECORDING_ANNOUNCEMENT_ES` (`25:66`, `31:35`, `38:39`) |
| `twiml.py` | **SHAPED** | 66 | `build_outbound_twiml` / `build_whisper_twiml` emit Twilio XML via `twilio.twiml.voice_response` (`23:24`, `75:109`); hard-codes `record-from-answer-dual`, `answerOnBridge`, `<Number url>` whisper pattern |
| `twilio_client.py` | **SHAPED** | 38 | Entire file: `twilio.rest.Client`, `telephony_configured()` gates on `TWILIO_*` (`20:38`) |
| `caller_id.py` | **AGNOSTIC** | 45 | `resolve_caller_id` (`148:175`), `list_caller_ids` (`128:145`), `CallerIdNotVerified` (`27:28`) — core security authorization |
| `caller_id.py` | **SHAPED** | 130 | `start_caller_id_verification` calls `validation_requests.create` (`65:69`), status callback to `/webhooks/twilio/caller-id-status` (`31:33`), `twilio_validation_sid` persistence (`75:76`, `96:125`) |
| `call_processor.py` | **AGNOSTIC** | 186 | `initiate_vocify_call_memo` (`54:81`), `process_vocify_call_background` (`84:158`), `log_call_engagement` (`161:239`) — STT, extraction, HubSpot; keyed by `twilio_call_sid` column name only |
| `call_processor.py` | **SHAPED** | 39 | `twilio_wav_url` (`31:39`), `download_twilio_recording` with Twilio API-key basic auth (`42:51`) |
| `webhook_signature.py` | **SHAPED** | 42 | `RequestValidator`, `verify_twilio_signature` (`21:33`); `identity_from_client_from` parses Twilio's `client:<identity>` (`36:42`) |

### Backend — API & HubSpot & storage

| File | Bucket | Lines (approx.) | Notes |
|------|--------|-----------------|-------|
| `api/calls.py` | **AGNOSTIC** | 50 | `get_calling_config` (`67:80`), `get_caller_ids` (`92:97`), `CallerIdRequest` (`35:37`), route shells |
| `api/calls.py` | **SHAPED** | 71 | `mint_voice_access_token` — `AccessToken` + `VoiceGrant` + `TWILIO_TWIML_APP_SID` (`40:64`, `16:17`) |
| `api/webhooks.py` (Twilio only) | **SHAPED** | 258 | `_twilio_public_url` … `twilio_recording` (`573:790`); `_reject_twiml` uses `VoiceResponse` (`609:613`) |
| `api/hubspot_recordings.py` | **AGNOSTIC** | 58 | Hub-portal pairing + signed URL (`25:59`); lookup uses `twilio_call_sid` as opaque `external_id` (`35`) |
| `services/hubspot/call_log.py` | **AGNOSTIC** | 96 | `build_call_properties`, `log_call_to_hubspot`, `mark_recording_ready` — HubSpot-only |
| `services/hubspot/calling_settings.py` | **AGNOSTIC** | 31 | One-time recording URL registration |
| `services/storage.py` (call helpers) | **AGNOSTIC** | 28 | `upload_call_recording` (`89:102`), `signed_call_recording_url` (`104:116`) |
| `migrations/025_outbound_calling.sql` | **AGNOSTIC** | 70 | Table shapes, RLS, `memos.source` check, `call-recordings` bucket (`19:83`) |
| `migrations/025_outbound_calling.sql` | **SHAPED** | 15 | Column/index names `twilio_validation_sid`, `twilio_call_sid` + Twilio comments (`27:28`, `49`, `42:44`) |
| `config.py` | **AGNOSTIC** | 4 | `CALLING_DEFAULT_COUNTRY_CODE`, `CALL_RECORDING_URL_TTL_SECONDS` (`173:176`) |
| `config.py` | **SHAPED** | 12 | `TWILIO_*` block (`164:172`); `TWILIO_ANNOUNCEMENT_LANGUAGE` consumed by TwiML `<Say>` |

### Chrome extension

| File | Bucket | Lines (approx.) | Notes |
|------|--------|-----------------|-------|
| `lib/dialer.js` | **AGNOSTIC** | 76 | Entire module — explicitly no Twilio (`1:76`) |
| `lib/api.js` | **AGNOSTIC** | 14 | `getCallingConfig`, `createVoiceToken`, `verifyCallerId` (`284:297`) |
| `background.js` (calling) | **AGNOSTIC** | ~95 | `startCallFlow` / `hangupCallFlow` (`877:917`), `CALL_STATE` handler (`1073:1082`), message routes (`1084:1103`), mutual-exclusion guards (`386:388`, `869:875`) |
| `popup/popup.js` (calling) | **AGNOSTIC** | 112 | `loadCallingConfig` … `handleVerifyCallerId` (`2935:3033`) |
| `popup/index.html` (calling UI) | **AGNOSTIC** | 17 | `#call-section` markup (`47:65`) except one Twilio-specific hint line |
| `popup/index.html` | **SHAPED** | 2 | "Twilio te llamará en inglés…" (`57`) |
| `lib/tab-capture.js` | **AGNOSTIC** | 10 | `call_in_progress` gate (`15:18`, `29:30`) — shared mic resource policy |
| `offscreen.js` (calling) | **LOCKED** | 65 | `twilioDevice`, `startCall` / `hangupCall` (`27:28`, `306:368`) — `Twilio.Device.connect({ params: { To, CallerId, … } })` |
| `vendor/twilio-voice-2.18.3.min.js` | **LOCKED** | 302KB | Loaded by `offscreen.html:8`; do not vendor-swap without replacing Device lifecycle |

### Bucket totals (production)

| Bucket | Backend | Chrome | **Total** |
|--------|---------|--------|-----------|
| CARRIER-AGNOSTIC | ~610 | ~360 | **~970** |
| CARRIER-SHAPED | ~650 | ~2 | **~650** |
| CARRIER-LOCKED | 0 | ~65 + SDK | **~65 + 302KB** |

---

## 2. Database schema carrier assumptions

Source: `backend/migrations/025_outbound_calling.sql`

### `user_caller_ids`

| Column | Twilio coupling | Telnyx reinterpretation |
|--------|-----------------|-------------------------|
| `phone_number` | None | E.164, carrier-agnostic |
| `status` | None | `pending` / `verified` / `failed` — generic |
| `twilio_validation_sid` | **Name + semantics** | Stores Twilio `validation_requests.create().call_sid` (`caller_id.py:75`). Twilio format: `CA` + 32 hex chars. Telnyx verification IDs differ (typically UUID). **Rename to `verification_sid` recommended.** |
| Index `idx_user_caller_ids_validation_sid` | Twilio-named | Same data, generic purpose |

### `outbound_calls`

| Column | Twilio coupling | Telnyx reinterpretation |
|--------|-----------------|-------------------------|
| `twilio_call_sid` | **Name + semantics** | Parent-leg call ID from voice webhook (`webhooks.py:637`, `660`). Twilio `CallSid` is `CA` + 32 hex, 34 chars. Used as HubSpot `hs_call_external_id` (`call_processor.py:221`) and recording lookup (`hubspot_recordings.py:35`). **Could store Telnyx call_control_id as opaque TEXT without format validation, but name is misleading.** |
| `recording_sid` | Mild | Twilio posts `RecordingSid` (`webhooks.py:770`, format `RE` + 32 hex). Generic enough to hold any carrier recording ID. |
| `from_number`, `to_number` | None | E.164 |
| `hubspot_*`, `memo_id`, `status` | None | CRM + pipeline state |
| `recording_path` | None | Supabase path `{user_id}/{call_sid}.wav` (`storage.py:96`) — filename embeds carrier call id |

### `memos.source`

- Value `'vocify_call'` added in migration (`74:77`) — **carrier-agnostic** product concept ("Vocify placed the call"), not Twilio-specific.

### Migration required?

| Approach | Verdict |
|----------|---------|
| **Rename columns** (`carrier_call_id`, `verification_sid`) + optional `carrier` enum | **Yes — clean** |
| **Reinterpret in place** (store Telnyx IDs in `twilio_call_sid`) | **Possible, ugly** — no DB constraint enforces `CA` prefix; only app code assumes Twilio webhook field names |
| **Dual-carrier** | **Yes** — add `carrier TEXT` column on `outbound_calls` and `user_caller_ids` |

Nothing in SQL enforces Twilio SID format; coupling is **naming and application-level correlation**, not CHECK constraints.

---

## 3. Security model — carrier dependency

**Property:** The browser cannot choose its own caller ID; the server resolves it from a trusted identity.

### Chain (today)

1. **Authenticated token mint** — Extension calls `POST /api/v1/calls/token` with Vocify JWT (`api.js:288-290`, `calls.py:83-89`). Server returns Twilio AccessToken whose `identity` is the Vocify `user_id` (`calls.py:57-58`, tested `test_telephony_token.py:18-24`).

2. **Browser originates call** — Offscreen `Twilio.Device(token).connect({ params: { To, CallerId, ContactId, DealId } })` (`offscreen.js:317-333`). `CallerId` is explicitly documented as a **preference only** (`offscreen.js:324-325`).

3. **Carrier webhook (authoritative)** — Twilio POSTs `application/x-www-form-urlencoded` to `/webhooks/twilio/voice` (`webhooks.py:616-684`) with:
   - `From=client:<user_id>` — Twilio Voice SDK client identity (`webhook_signature.py:36-42`)
   - `To`, optional `CallerId`, `CallSid`, custom params
   - `X-Twilio-Signature` HMAC over public URL + sorted params (`webhook_signature.py:21-30`, `webhooks.py:597-601`)

4. **Server authorization** — After signature verification:
   - `identity_from_client_from(params["From"])` → `user_id` (`webhooks.py:628-630`)
   - `resolve_caller_id(supabase, user_id, params.get("CallerId"))` → verified E.164 (`webhooks.py:647`, `caller_id.py:148-175`)
   - TwiML `<Dial callerId="…">` sets the **presented** number (`twiml.py:88-89`); client preference is ignored if not verified (`test_telephony_webhook.py:306-346`)

5. **Persistence** — `outbound_calls` row keyed by parent `CallSid` (`webhooks.py:657-671`); `hubspot_hub_id` deliberately **not** taken from client (`webhooks.py:663-666`, test `test_telephony_webhook.py:420-462`).

### Twilio-specific mechanisms this depends on

| Mechanism | Why it matters |
|-----------|----------------|
| **Twilio AccessToken + VoiceGrant → TwiML App** | Binds outbound calls to your server-side Voice URL (`calls.py:61-63`) |
| **`From=client:<identity>` on Voice webhook** | Signed, server-readable user identity without trusting browser-supplied user id in custom params |
| **`X-Twilio-Signature` + `RequestValidator`** | Proves webhook came from Twilio; without equivalent, anyone could POST fake dials |
| **TwiML `<Dial callerId>`** | Server-side override of presented CLI after authorization |
| **`CallSid` as correlation id** | Recording callback minutes later (`webhooks.py:735-737`) |

### What breaks on Telnyx (or similar)

If Telnyx WebRTC lets the client set `from` / caller ID **without** a server-side hook equivalent to the TwiML Voice URL:

- The **caller-ID authorization property cannot be reproduced the same way** — you would need e.g. Call Control API (server initiates or answers client leg), JWT claims inspected server-side before bridging, or a Telnyx TeXML/connection webhook that mirrors Twilio's pattern.
- `client:` identity prefix is **Twilio-specific**; Telnyx uses different client/session identity wiring.
- Signature algorithm and header names differ (Telnyx: Ed25519 / different webhook signing).
- Custom params (`ContactId`, `DealId`) may not forward identically.

**Bottom line:** The security model is **architecturally sound** but **implemented through Twilio's Voice SDK + TwiML App webhook**, not through a carrier-neutral abstraction. A carrier that lacks "server answers outbound client call with authorized CLI" forces a **redesign**, not a drop-in swap.

---

## 4. Dual-carrier — second implementations & abstraction seam

### Functions needing a provider implementation

| Function | Current location | Signature (proposed) |
|----------|------------------|----------------------|
| Config gate | `twilio_client.telephony_configured()` | `telephony_configured() -> bool` |
| REST client | `twilio_client.twilio_rest()` | `get_provider_client() -> ProviderClient` |
| Client token | `calls.mint_voice_access_token(user_id, ttl=3600) -> str` | `mint_client_token(user_id: str, ttl: int) -> str` |
| Webhook verify | `webhook_signature.verify_twilio_signature(url, params, sig, token) -> bool` | `verify_webhook(url: str, params: dict, headers: dict) -> bool` |
| Client identity | `webhook_signature.identity_from_client_from(from_value) -> Optional[str]` | `identity_from_connect_params(params: dict) -> Optional[str]` |
| Outbound connect response | `twiml.build_outbound_twiml(...) -> str` | `build_outbound_connect(to, caller_id, recording_cb, whisper_cb, timeout) -> str` |
| Whisper / disclosure | `twiml.build_whisper_twiml(...) -> str` | `build_pre_bridge_announcement(announcement, language) -> str` |
| Caller ID verify start | `caller_id.start_caller_id_verification(supabase, user_id, raw, label) -> dict` | same |
| Caller ID verify callback | `mark_caller_id_verified/failed(supabase, validation_sid)` | `parse_verification_callback(params) -> (sid, status)` |
| Recording download | `call_processor.download_twilio_recording(url) -> bytes` | `download_recording_media(url) -> bytes` |
| Voice route handler | `webhooks.twilio_voice` | `handle_outbound_connect_webhook(request) -> Response` |
| Recording webhook | `webhooks.twilio_recording` | `handle_recording_ready(request) -> Response` |
| Browser connect | `offscreen.startCall({ token, to, callerId, … })` | `startCall({ credentials, to, metadata })` — **separate SDK** |

### Natural seam

```
backend/app/services/telephony/
  provider.py          # Protocol / ABC
  providers/
    twilio.py          # move twiml build, signature, token, validation_requests
    telnyx.py          # TeXML or Call Control + Telnyx JWT
  caller_id.py         # keep resolve_caller_id (agnostic)
  call_processor.py    # keep memo pipeline (agnostic)
```

Route layer (`webhooks.py`) should call `get_telephony_provider()` rather than importing Twilio types directly. **Today it does not** — `webhooks.py:16` imports `VoiceResponse` at module level; all four routes are under `/twilio/` (`616-790`).

### Easy or awkward?

| Aspect | Assessment |
|--------|------------|
| `resolve_caller_id`, E.164, memo pipeline, HubSpot | **Easy** — already isolated |
| Webhook routes | **Awkward** — four hard-coded `/twilio/*` paths, shared `_twilio_authentic` helpers |
| DB columns | **Awkward** — `twilio_call_sid` threaded through ~15 query sites |
| Extension | **Awkward** — single offscreen doc, Twilio SDK always loaded (`offscreen.html:8`), shared with mic + Listen (`dialer.js:7-8`) |
| Dual-carrier in prod | **Awkward** — would need per-user or per-tenant `carrier` setting, two SDKs or dynamic load, two webhook endpoint sets |

**Honest verdict:** Backend could gain a provider interface in **~2-3 days** of focused refactor; **end-to-end dual-carrier** (extension + DB + two webhook stacks) is a **multi-week** feature.

---

## 5. Hidden couplings

| Coupling | Location | Impact on swap |
|----------|----------|----------------|
| `TWILIO_SKIP_SIG_CHECK` dev flag | `webhooks.py:587-596` | Telnyx needs parallel `TELNYX_SKIP_SIG_CHECK` or generic flag |
| `telephony_configured()` requires 5 Twilio env vars | `twilio_client.py:20-27` | Telnyx has different credential shape |
| `record-from-answer-dual` | `twiml.py:90-91` | HubSpot transcription expects channel 1 = caller, channel 2 = recipient (`14:16`). Telnyx must produce equivalent stereo WAV |
| `.wav` URL suffix | `call_processor.py:31-39` | Twilio-specific media URL pattern; Telnyx uses different recording URLs/auth |
| Recording download auth | `call_processor.py:44-47` | Uses `TWILIO_API_KEY_SID` + `TWILIO_API_KEY_SECRET` as HTTP basic auth — not `AUTH_TOKEN` |
| `memos.source = 'vocify_call'` | `call_processor.py:68`, migration `76` | Carrier-agnostic — keep as-is |
| `_EXTRACTION_SOURCE_TYPES` | `pipeline_meta.py:25-27` | Includes `'vocify_call'` — carrier-agnostic |
| `hs_call_source = INTEGRATIONS_PLATFORM` | `call_log.py:52-53` | **HubSpot requirement**, not Twilio — must not change (`test_hubspot_call_log.py:32-34`) |
| `hs_call_external_id` = call SID | `call_processor.py:221` | Opaque string — works if Telnyx id is unguessable |
| Public recording auth | `hubspot_recordings.py:45-54` | Pairs `external_id` + `externalAccountId` with `hubspot_hub_id` from `crm_connections` — carrier-agnostic |
| Spanish UI strings | `webhooks.py:630,650`, `dialer.js:52-58`, `popup.js:3000-3011`, `index.html:47-65` | Copy-only, not carrier logic |
| Twilio verification UX copy | `index.html:57`, `caller_id.py:8-9` | Must rewrite for Telnyx verification flow |
| Offscreen shared with mic + Listen | `offscreen.js:1-8`, `dialer.js:7-8`, `background.js:327-331` | Call loads Twilio SDK even for memo-only users; `canStartCall` / `canStartTabCapture` enforce mutual exclusion (`tab-capture.js:17-18`) |
| `requirements.txt` | `twilio>=9.0.0` | Python SDK dependency |
| Runbook | `docs/runbooks/twilio-setup.md` | Ops coupling |

---

## 6. Test coverage map

### Would **fail** or need rewrite (Twilio-specific)

| File | Classes / tests | Why |
|------|-----------------|-----|
| `test_telephony_webhook.py` | `TestVerifyTwilioSignature` (all), `TestVoiceRouteSignature` (all), `TestCallerIdStatusWebhook`, `TestTwilioSkipSigCheckProductionGate` | Uses `RequestValidator`, `/webhooks/twilio/*`, TwiML assertions (`302-303`, `344-345`) |
| `test_telephony_token.py` | `TestMintVoiceAccessToken` (all except structure could adapt) | Decodes Twilio JWT grants (`18-42`) |
| `test_telephony_twiml.py` | `TestBuildOutboundTwiml`, `TestBuildWhisperTwiml` | Asserts TwiML attributes (`66-88`, `110-117`) |
| `test_telephony_caller_id.py` | `TestStartCallerIdVerification` (all 4 tests), `TestMarkCallerIdVerified` | Mocks `twilio_rest`, `twilio_validation_sid` |
| `test_telephony_call_processor.py` | `TestTwilioWavUrl`, `TestDownloadUsesBasicAuth` | Twilio URL + credential shape |

### Would **keep passing** (carrier-agnostic)

| File | Classes / tests |
|------|-----------------|
| `test_telephony_twiml.py` | `TestNormalizeE164` (all) |
| `test_telephony_caller_id.py` | `TestResolveCallerId` (all 6 tests) |
| `test_telephony_call_processor.py` | `TestSourceType`, `TestBucket` |
| `test_hubspot_call_log.py` | `TestBuildCallProperties`, `TestRecordingEndpointUrl`, `TestPublicRecordingEndpoint`, `TestLogCallEngagement` (uses `CA…` as opaque id only) |
| `chrome-extension/lib/dialer.test.js` | All (`normalizeDialTarget`, `canStartCall`, `callButtonLabel`) |

### Would pass but become **misleading**

| File | Issue |
|------|-------|
| `test_telephony_token.py` | `TestCreateCallerId` mocks verification — doesn't assert Twilio but path name implies it |
| `test_hubspot_call_log.py` | `twilio_call_sid` in fixtures — still valid if column renamed without test rename |

### No dedicated tests

- `offscreen.js` Twilio Device lifecycle — **untested**
- `background.js` `startCallFlow` — **untested** (integration/manual)
- `popup.js` call section — **untested**
- End-to-end recording webhook → memo → HubSpot — **partially** covered via unit tests, no full integration test

---

## 7. Swap cost estimate (Twilio → Telnyx only)

| Workstream | Effort | Files primarily touched |
|------------|--------|-------------------------|
| Telnyx provider (token, webhooks, TeXML/Call Control, verification, recording fetch) | **Large** | New `providers/telnyx.py`, replace shaped ~650 lines |
| DB migration (rename columns + optional `carrier`) | **Small** | `026_*`, all `twilio_call_sid` query sites |
| Extension WebRTC SDK swap | **Medium** | `offscreen.js`, `offscreen.html`, remove/replace vendor JS |
| Config / ops / runbooks | **Small** | `config.py`, `.env`, `docs/runbooks/` |
| Test rewrite | **Medium** | 5 `test_telephony_*.py` files (~1,040 lines total) |
| **Total (single carrier replacement)** | **~2-4 engineer-weeks** | Assumes Telnyx supports server-mediated CLI + dual-channel recording |

Dual-carrier behind one interface: add **~30-50%** for routing, per-tenant config, and dual SDK loading.

---

*Generated: 2026-08-27. Read-only audit; no repository files modified.*
