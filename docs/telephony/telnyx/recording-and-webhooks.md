# Telnyx: Call Recording, Delivery, Webhook Auth — Factual Reference

Research date: 2026-08-27. Every claim below is tagged DOCUMENTED (with the URL actually fetched) or NOT DOCUMENTED.
No inference beyond what the fetched text states. Where I combine two documented facts, it is labelled INFERRED-FROM-TWO-DOCS and flagged.

**Stale starting point:** `https://developers.telnyx.com/docs/voice/programmable-voice/recording` returns **HTTP 404 / "Page Not Found"** (fetched 2026-08-27). Telnyx docs are now a Mintlify site with a machine index at `https://developers.telnyx.com/llms.txt`; append `.md` to any doc URL for clean Markdown.

---

## 1. Dual-channel (stereo) support

### Call Control (`record_start`)
DOCUMENTED — `https://developers.telnyx.com/api-reference/call-commands/recording-start.md`
(OpenAPI source: `POST /v2/calls/{call_control_id}/actions/record_start`, schema `StartRecordingRequest`)

- `channels` is a **required** field. Enum: `single`, `dual`.
- Verbatim description: *"When `dual`, final audio file will be stereo recorded with the first leg on channel A, and the rest on channel B."*
- `recording_track` enum `both` | `inbound` | `outbound`, default `both`. Verbatim: *"If only single track is specified (`inbound`, `outbound`), `channels` configuration is ignored and it will be recorded as mono (single channel)."* → to get stereo you must leave `recording_track` at `both`.
- Other params: `format` (required), `client_state`, `command_id`, `play_beep`, `max_length` (0–14400, default 0), `timeout_secs`, `trim` (`trim-silence`), `custom_file_name` (1–40 chars), plus transcription options.

Also DOCUMENTED — the recording resource echoes it back: `channels` enum `single`|`dual`, description *"When `dual`, the final audio file has the first leg on channel A, and the rest on channel B."*
(`https://developers.telnyx.com/api-reference/call-recordings/retrieve-a-call-recording.md`)

### Does it work for a BRIDGED call (two legs)?
DOCUMENTED (wording) — the phrase *"first leg on channel A, and the rest on channel B"* explicitly describes multiple legs, i.e. it is not single-leg-only. Same wording appears in:
- `record_start` (`.../call-commands/recording-start.md`)
- Recording resource (`.../call-recordings/retrieve-a-call-recording.md`)
- TeXML schema `TexmlRecordingChannels` in the consolidated OpenAPI spec (`https://raw.githubusercontent.com/team-telnyx/openapi/master/openapi/spec3.json`), verbatim: *"When `dual`, final audio file has the first leg on channel A, and the rest on channel B. `single` mixes both tracks into a single channel."* Default in that schema is `dual`.

DOCUMENTED — recording can be attached **directly to the bridge command**: `POST /v2/calls/{call_control_id}/actions/bridge`, schema `BridgeRequest`, includes `record`, `record_channels`, `record_format`, `record_max_length`, `record_timeout_secs`, `record_track`, `record_trim`, `record_custom_file_name`.
(`https://developers.telnyx.com/api-reference/call-commands/bridge-calls.md`)

NOT DOCUMENTED — an explicit prose statement of the form "channel A = leg A / channel B = leg B for a bridged pair" beyond the "first leg … the rest" wording. No worked bridged-dual example found.

### TeXML
DOCUMENTED — `https://developers.telnyx.com/docs/voice/programmable-voice/texml-verbs/dial.md`
- `<Dial record="...">` options: `do-not-record`, `record-from-answer`, `record-from-ringing`, **`record-from-answer-dual`**, `record-from-ringing-dual`. Default `do-not-record`.
- Verbatim: *"The record attribute lets you record both legs of a call within the associated `<Dial>` verb. It works with the `<Number>` and `<Sip>` nouns only. … Recordings are available in two options: single or dual."*
- Separate attribute `recordingChannels`: *"The number of channels in the final recording. Possible values are: single (for mono) and dual (for stereo). Defaults to single."*
- ⇒ **`record="record-from-answer-dual"` is byte-identical to the Twilio value Vocify uses today.**

DOCUMENTED — TeXML REST outbound call also accepts `Record` + `RecordingChannels` + `RecordingTrack` + `RecordingStatusCallback*` + `RecordingTimeout` + `SendRecordingUrl` + `Trim`.
(`https://developers.telnyx.com/api-reference/texml-rest-commands/initiate-an-outbound-call.md`; note that page's `RecordingChannels` description says *"Defaults to `mono`"*, which conflicts with the `<Dial>` page's *"Defaults to single"* and with the spec's default `dual` — inconsistent docs, so **set it explicitly**.)

---

## 2. Format (WAV vs MP3)

DOCUMENTED — Call Control `record_start`: `format` is **required**, enum `wav` | `mp3`. Verbatim: *"The audio file format used when storing the call recording. Can be either `mp3` or `wav`."* Example value in the schema is `mp3`; the SDK code samples use `format: "wav"`.
(`https://developers.telnyx.com/api-reference/call-commands/recording-start.md`)

DOCUMENTED — `record_format` enum `wav` | `mp3`, **default `mp3`**, on: `POST /v2/calls` (Dial), `.../actions/answer`, `.../actions/transfer`, `.../actions/bridge`.
(`.../call-commands/dial.md`, `.../answer-call.md`, `.../transfer-call.md`, `.../bridge-calls.md`)

DOCUMENTED — `format` and `channels` are **independent** fields with independent enums; nothing in any fetched page restricts `wav` to `single`, or `dual` to `mp3`.
NOT DOCUMENTED — an explicit sentence asserting "WAV is supported with dual channels". The support is implied by the orthogonal required-enum design, not stated. **Verify empirically before committing.**

DOCUMENTED — the stored recording resource exposes **both** formats: `download_urls: { mp3: "Link to download the recording in mp3 format.", wav: "Link to download the recording in wav format." }`.
(`https://developers.telnyx.com/api-reference/call-recordings/retrieve-a-call-recording.md`)
NOT DOCUMENTED — whether `download_urls.wav` is populated for a recording that was created with `format: mp3` (i.e. whether Telnyx transcodes on demand). Assume no.

### TeXML format — GAP
NOT DOCUMENTED — **TeXML `<Dial>` has no recording-format attribute.** The attribute list on `.../texml-verbs/dial.md` contains `record`, `recordingChannels`, `recordMaxLength`, `recordingStatusCallback*`, `sendRecordingUrl` — and no format/`recordFormat`. Same for `Initiate an outbound call` (`Record`, `RecordingChannels`, `RecordingTrack`, `RecordingTimeout`, `Trim`, `SendRecordingUrl` — no format) and for `Request recording for a call` (`.../texml-rest-commands/request-recording-for-a-call.md`).
- The TeXML **`<Record>` verb** (a different verb — records one leg to a file, TwiML `<Record>` equivalent) *does* have `format`: options `mp3`, `wav`, **default `mp3`**. (`https://developers.telnyx.com/docs/voice/programmable-voice/texml-verbs/record.md`)
- The TeXML recording resource's `media_url` example in the spec is `http://recordings.com/mp3/filename.mp3` (example only).
⇒ **If we go TeXML, the WAV question for `<Dial record=...>` is unresolved by docs.** Mitigation that IS documented: TeXML recordings appear in the Call Control recording resource (`initiated_by` enum includes `DialVerb`) which exposes `download_urls.wav`. That is INFERRED-FROM-TWO-DOCS, not stated.

HubSpot relevance: MP3-only would be disqualifying. Call Control gives an explicit `format: "wav"`; TeXML does not.

---

## 3. Recording trigger semantics — can it start automatically on answer?

**YES, in Call Control too — this is the key finding.** DOCUMENTED. You do *not* have to fire a post-answer `record_start` command.

`record` parameter — verbatim: *"Start recording automatically after an event. Disabled by default."* — enum with a single value **`record-from-answer`**. Present on all of:
| Endpoint | Doc URL |
|---|---|
| `POST /v2/calls` (Dial) | `https://developers.telnyx.com/api-reference/call-commands/dial.md` |
| `POST /v2/calls/{id}/actions/answer` | `https://developers.telnyx.com/api-reference/call-commands/answer-call.md` |
| `POST /v2/calls/{id}/actions/bridge` | `https://developers.telnyx.com/api-reference/call-commands/bridge-calls.md` |
| `POST /v2/calls/{id}/actions/transfer` | `https://developers.telnyx.com/api-reference/call-commands/transfer-call.md` |

Companion params on each: `record_channels` (`single`|`dual`, **default `dual`**), `record_format` (`wav`|`mp3`, default `mp3`), `record_max_length` (0–43200, default 0), `record_timeout_secs`, `record_track`, `record_trim`, `record_custom_file_name`.
DOCUMENTED — on `POST /v2/calls`: *"When the `record` parameter is set to `record-from-answer`, the response will include a `recording_id` field."* (`.../call-commands/dial.md`)

⇒ So `record="record-from-answer-dual"` on Twilio's `<Dial>` maps to **either**:
- Call Control: `record: "record-from-answer"`, `record_channels: "dual"`, `record_format: "wav"` on the dial/bridge/answer command; **or**
- TeXML: `<Dial record="record-from-answer-dual">` (format unspecified — see §2).

### Race / latency risk if you use the explicit command instead
DOCUMENTED — `record_start` documents two relevant 422 errors:
- code `90034` "Call not answered yet" — *"This call can't receive this command because it has not been answered yet."*
- code `90020` "Call recording triggered before audio started" — *"Call recording cannot be started until audio has commenced on the call."*
(`https://developers.telnyx.com/api-reference/call-commands/recording-start.md`)
⇒ The failure modes of a webhook-then-command pattern are documented as hard errors. NOT DOCUMENTED: any quantified latency figure, or how much leading audio is lost if `record_start` is issued late. Using the declarative `record: record-from-answer` avoids the round trip entirely.

### `record_start` on the bridge?
DOCUMENTED — there is no `record_start` on a "bridge" object; there is no bridge resource. Instead: (a) `record` params inline on the `bridge` command (above), or (b) `record_start` against a `call_control_id` while the legs are bridged, with `channels: dual`. Conference has its own set: `POST /v2/conferences/{id}/actions/record_start|record_stop|record_pause|record_resume`. (`https://developers.telnyx.com/docs/voice/programmable-voice/voice-api-commands-and-resources.md`)

---

## 4. Recording delivery

DOCUMENTED — event name **`call.recording.saved`**. Also `call.recording.error` and `call.recording.transcription.saved`. Listed as the "Expected Webhooks" of `record_start`.
(`https://developers.telnyx.com/api-reference/call-commands/recording-start.md`, `https://developers.telnyx.com/api-reference/callbacks/call-recording-saved.md`)

DOCUMENTED payload (from `https://developers.telnyx.com/data/webhook-events.json`, event `call.recording.saved`, media type `application/json`):
```json
{ "data": { "record_type": "event", "event_type": "call.recording.saved",
  "id": "0ccc7b54-...", "occurred_at": "2018-02-02T22:25:27.521992Z",
  "payload": { "connection_id": "...", "call_leg_id": "...", "call_session_id": "...",
    "client_state": "aGF2ZSBhIG5pY2UgZGF5ID1d",
    "recording_started_at": "...", "recording_ended_at": "...",
    "channels": "single",
    "recording_urls": { "mp3": "...", "wav": "..." },
    "public_recording_urls": { "mp3": "...", "wav": "..." } } } }
```
A fuller real-world example in the storage tutorial also shows `call_control_id`, `format`, `recording_id`, `start_time`, `end_time`, `occurred_at`, `webhook_id`.
(`https://developers.telnyx.com/docs/voice/programmable-voice/storing-call-recordings.md`)

### Does Telnyx host the file, and for how long?
DOCUMENTED — *"Call recordings are automatically stored in S3 buckets owned by Telnyx, but users can opt to store recordings in their own S3 or GCS buckets instead."* and *"The link to them is shared in the webhook 'call.recording.saved' when they are ready to download."*
(`https://developers.telnyx.com/docs/voice/programmable-voice/storing-call-recordings.md`)

DOCUMENTED — **URL lifetime is 10 minutes**, from two sources:
- Tutorial: *"The link to the recording is active for 10 minutes."* (same URL as above; the sample URL is an AWS SigV4 pre-signed URL with `X-Amz-Expires=600`).
- OpenAPI `CallRecordingSaved.payload.recording_urls` description, verbatim: *"Recording URLs in requested format. These URLs are valid for 10 minutes. After 10 minutes, you may retrieve recordings via API using Reports -> Call Recordings documentation, or via Mission Control under Reporting -> Recordings."*
(`https://raw.githubusercontent.com/team-telnyx/openapi/master/openapi/spec3.json`)

DOCUMENTED — `public_recording_urls`, verbatim: *"Recording URLs in requested format. The URL is valid for as long as the file exists. For security purposes, this feature is activated on a per request basis. Please contact customer support with your Account ID to request activation."* (Same spec URL. Note: in the tutorial's real examples this object is `{}` — i.e. off by default. A permanently-public URL is the opposite of what Vocify wants; do not enable it.)

### Retention / deletion policy
**NOT DOCUMENTED** — no automatic retention window or auto-deletion period for Programmable Voice call recordings appears in any page fetched. Nothing in the recording docs, the recording API reference, or the storage tutorial states "recordings are deleted after N days".
DOCUMENTED — deletion is **your** action:
- `DELETE /v2/recordings/{recording_id}` — verbatim: *"Permanently deletes the specified call recording and returns the deleted recording resource. The media is removed and can no longer be downloaded."* (`https://developers.telnyx.com/api-reference/call-recordings/delete-a-call-recording.md`)
- `POST /v2/recordings/actions/delete` — bulk delete path present in the consolidated OpenAPI spec (`https://raw.githubusercontent.com/team-telnyx/openapi/master/openapi/spec3.json`).
- `GET /v2/recordings`, `GET /v2/recordings/{id}` also exist.
NOT DOCUMENTED — GDPR/AEPD-relevant statements about storage region for recordings on Telnyx's own S3 (a Data Locality setting exists for other products but I did not verify it applies to Programmable Voice recordings). **Open item for a Spanish/EU deployment.**

### TeXML delivery
DOCUMENTED — TeXML uses `recordingStatusCallback` + `recordingStatusCallbackEvent` (`in-progress`, `completed`, `absent`; default `completed`) + `recordingStatusCallbackMethod` (GET/POST, default POST) + `sendRecordingUrl` (default `true`) — i.e. **the same names Vocify already uses on Twilio**.
(`https://developers.telnyx.com/docs/voice/programmable-voice/texml-verbs/dial.md`)
DOCUMENTED payload — media type **`application/x-www-form-urlencoded`** (form-encoded, like Twilio), fields: `AccountSid`, `CallSid`, `CallSidLegacy`, `ConnectionId`, `RecordingChannels` (integer, enum `1`|`2` — *"1 for mono, 2 for dual-channel"*), `RecordingDuration`, `RecordingSid`, `RecordingSource` (e.g. `DialVerb`), `RecordingStatus` (`completed`), `RecordingUrl` (*"conditional, only present if recording URL is available"*).
(`https://developers.telnyx.com/data/webhook-events.json`; schemas `TexmlRecordingCompletedWebhookSchema` / `TexmlRecordingInProgressWebhookSchema` in `spec3.json`; page `https://developers.telnyx.com/api-reference/callbacks/texml-recording-completed.md`)
NOT DOCUMENTED — the lifetime of the TeXML `RecordingUrl`, and whether it is pre-signed.

---

## 5. Downloading the recording — what auth?

DOCUMENTED (webhook path, no auth needed) — the `recording_urls.wav` value in `call.recording.saved` is an **AWS SigV4 pre-signed S3 URL**. The documented example is:
`https://s3.amazonaws.com/telephony-recorder-prod/<account>/<date>/<call_leg_id>-<unix>.wav?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=...&X-Amz-Date=...&X-Amz-Expires=600&X-Amz-SignedHeaders=host&X-Amz-Signature=...`
(`https://developers.telnyx.com/docs/voice/programmable-voice/storing-call-recordings.md`)
⇒ The credential is embedded in the URL and it expires in 600 s. **This is materially different from Twilio**, where you GET the media URL with HTTP Basic auth (AccountSid/AuthToken). Practical consequence for Vocify: download must happen inside the 10-minute window, or re-resolve via the API.

DOCUMENTED (API path) — the whole Telnyx v2 REST API uses `Authorization: Bearer <TELNYX_API_KEY>`; the OpenAPI `securitySchemes` for the recording endpoints is `bearerAuth: {type: http, scheme: bearer}`, and `GET /v2/recordings/{recording_id}` returns `download_urls.{mp3,wav}` ("Links to download the recording files").
(`https://developers.telnyx.com/api-reference/call-recordings/retrieve-a-call-recording.md`, `https://developers.telnyx.com/llms.txt`)

**NOT DOCUMENTED** — whether the `download_urls` returned by `GET /v2/recordings/{id}` are themselves pre-signed/unauthenticated or require the Bearer token, and how long they last. No statement found. (Twilio's Basic-auth-on-media model has **no** documented Telnyx equivalent — I found no page describing Basic auth for recording media.)

### Can we download it and store it ourselves? YES.
DOCUMENTED — two supported ways:
1. Fetch the pre-signed `recording_urls.wav` from the webhook (or `download_urls` via the API) and put the bytes in our own bucket. Nothing prohibits this.
2. **Have Telnyx write directly into a bucket we own** — `POST https://api.telnyx.com/v2/custom_storage_credentials/{call_control_application_id}` with `Authorization: Bearer ...`, and `backend` one of `gcs` | `s3` | `azure`:
   - `s3`: `{bucket, region, aws_access_key_id, aws_secret_access_key}`
   - `gcs`: `{credentials (service-account JSON), bucket}`
   - `azure`: `{bucket, account_name, account_key}`
   The `call.recording.saved` webhook then carries a bucket-native URI instead of a pre-signed link, e.g. `"wav": "s3://tacrde12904/<account>/<date>/<call_leg_id>-<unix>"`, `gs://...`, or `https://my-account.blob.core.windows.net/...`.
   (`https://developers.telnyx.com/docs/voice/programmable-voice/storing-call-recordings.md`; endpoints also listed at `https://developers.telnyx.com/docs/voice/programmable-voice/voice-api-commands-and-resources.md` — `/v2/custom_storage_credentials`)
   ⇒ **This is strictly better than the Twilio flow for "WE own the audio": no download hop, no 10-minute race, audio never sits only on the vendor's S3.**
   NOT DOCUMENTED — whether the object key/extension can be controlled beyond `custom_file_name`, and whether custom storage changes the storage line item on the bill.

---

## 6. Cost: recording and storage

Source for all of the following: `https://telnyx.com/pricing.md` (machine-readable pricing page, fetched 2026-08-27), section `### Voice Api` (`voice-api`, 83 rates), plus the "Voice API" summary table near the top.

| Line item (verbatim) | Base | Volume tiers (verbatim) |
|---|---|---|
| `Call Recording Usd Per Min` (summary table) | **$0.002/min** | flat |
| `Cost associated with recording audio during an origination call - amount is per minute` | **$0.002/min** | 0–100000: $0.002; 100000–1000000: $0.0019; 1000000–10000000: $0.0017; 10000000–50000000: $0.0015; 50000000–100000000: $0.0013; 100000000+: $0.0012 |
| `Cost associated with recording audio during an termination call - amount is per minute` | **$0.002/min** | same tiers as above |
| **`Cost associated with storage of a call recording - amount is per minute`** | **$0** | 10000–5000000: **$0.0004**; 5000000–15000000: $0.0002; 15000000–100000000: $0.00007; 100000000–1000000000: $0.00004; 1000000000+: $0.00003 |

### Your prior belief ("Telnyx recording storage is free") — **PARTIALLY REFUTED**
- DOCUMENTED: the storage line item's **base rate is $0/min**, and the first volume tier only begins at **10,000 minutes**. So there is effectively a free allowance at the bottom of the curve.
- DOCUMENTED: **beyond that, storage is billed** at $0.0004/min falling to $0.00003/min. Storage is **not** unconditionally free.
- DOCUMENTED: **recording itself is always charged** at $0.002/min (and it is charged per call direction — separate origination and termination line items exist).
- NOT DOCUMENTED: any page that uses the words "free storage tier", or that explains the semantics of the `10000-5000000` tier boundary (is the first 10,000 minutes free every month? cumulatively? per account?). The pricing table gives numbers with no prose. **Confirm with Telnyx sales in writing.**
- Unrelated but adjacent, DOCUMENTED: object-storage product ("Storage" section) is $0/GB/mo in the default region, $0.025/GB/mo in EU and APAC; `Media storage - cost per API call` = $0.

Also DOCUMENTED and worth budgeting: `record_timeout_secs` / `RecordingTimeout` silence detection carries a transcription charge — verbatim: *"Please note that call transcription is used to detect silence and the related charge will be applied."* (`https://developers.telnyx.com/api-reference/call-commands/recording-start.md`). Leave it at 0.

---

## 7. Webhook authentication

### Headers — CONFIRMED
DOCUMENTED — **`telnyx-signature-ed25519`** and **`telnyx-timestamp`**. Your belief is correct.
- `https://developers.telnyx.com/docs/development/api-fundamentals/webhooks/receiving-webhooks.md`: *"preserve `telnyx-timestamp` and `telnyx-signature-ed25519`, verify the signature before trusting the event, and reject signatures outside the application's replay window."*
- `https://developers.telnyx.com/docs/voice/programmable-voice/voice-api-webhooks.md` lists `Telnyx-Signature-Ed25519` (*"ED25519 signature for verification"*) and `Telnyx-Timestamp` (*"Unix timestamp when the webhook was generated"*).
- Every recording callback page repeats: *"This webhook uses Telnyx headers (telnyx-timestamp, telnyx-signature-ed25519) that are compatible with Standard Webhooks specification for SDK generation."* (`https://developers.telnyx.com/api-reference/callbacks/call-recording-saved.md`, and `https://developers.telnyx.com/data/webhook-events.json`)

### Algorithm — CONFIRMED, and it does NOT involve the request URL
DOCUMENTED (docs, qualitative) — public-key, not shared-secret: *"Products that document Telnyx Ed25519 signing use the account's key pair. The public key is available in Mission Control Portal [portal.telnyx.com/#/api-keys/public-key]."* and *"Verification requires the exact body bytes received by the server. Do not parse and reserialize JSON before verification."*
(`https://developers.telnyx.com/docs/development/api-fundamentals/webhooks/receiving-webhooks.md`)

DOCUMENTED (official SDK source, exact construction) — `https://raw.githubusercontent.com/team-telnyx/telnyx-python/master/src/telnyx/lib/webhook_verification.py`:
```
SIGNATURE_HEADER = "telnyx-signature-ed25519"     # base64, must decode to exactly 64 bytes
TIMESTAMP_HEADER = "telnyx-timestamp"             # unix seconds
TIMESTAMP_TOLERANCE_SECONDS = 300                 # 5-minute replay window
public key: base64, must decode to exactly 32 bytes (from TELNYX_PUBLIC_KEY)
signed_payload = f"{timestamp_header}|{payload_str}"     # literal pipe separator
verify: nacl.signing.VerifyKey(pubkey).verify(signed_payload.encode("utf-8"), signature_bytes)
```
Module docstring, verbatim: *"Signed payload: `{timestamp}|{payload}`"*. Header lookup is case-insensitive. Same file notes this *"matches the implementation pattern used in the Go, Java, and Ruby SDKs."*

**→ The signed message is `timestamp + "|" + raw_body`. The request URL, host, method, and query string are NOT part of the signature.** This is the concrete answer to your proxy problem: unlike Twilio's HMAC-SHA1 over the full request URL + sorted POST params, **a reverse proxy, a rewritten host, a changed path, or an added query param cannot break Telnyx signature verification.** Only body-mutating middleware can.

### Official Python helper — YES
DOCUMENTED — `https://developers.telnyx.com/docs/development/sdk/python/webhooks.md`
- `pip install "telnyx[webhooks]"` (needs PyNaCl).
- `export TELNYX_PUBLIC_KEY="..."` — read automatically like `TELNYX_API_KEY`.
- `event = client.webhooks.unwrap(payload, headers=request.headers)` — verifies then returns a typed event; raises on bad signature. FastAPI example is in the docs verbatim.
- Lower-level: `from telnyx.lib.webhook_verification import verify_webhook_signature` (verify only, no parse), and `from telnyx.lib.webhooks_ed25519 import verify_ed25519, unwrap_with_ed25519`.
- ⚠️ `client.webhooks.unsafe_unwrap(payload)` does **not** verify. Docs carry an explicit warning about `unsafe`-named helpers.
- Also documented: a legacy HMAC-SHA256 path still exists in the SDK as `client.webhooks._unwrap_hmac(payload, headers=headers)` (private; `webhooks_ed25519.py` calls it *"Fallback to HMAC-SHA256 (old behavior)"*). Ed25519 is the default. Node/Go/Java/Ruby/PHP helpers also documented.

### Delivery contract (relevant to our handler)
DOCUMENTED (`.../receiving-webhooks.md`, `.../voice-api-webhooks.md`):
- Envelope: `{data: {record_type, event_type, id, occurred_at, payload}, meta: {attempt, delivered_to}}`. **TeXML callbacks are form-encoded, not this envelope.**
- Return `200` promptly; do not download media before acknowledging. Dedupe on `data.id`. Do not assume single delivery or ordering.
- Connection config fields: `webhook_event_url`, `webhook_event_failover_url`, `webhook_timeout_secs` (0–30, default null). Settable via the Call Control Applications API.
- HTTP `408`/`429` from our endpoint are retried.
NOT DOCUMENTED — the exact retry schedule for `call.recording.saved` (the fundamentals page explicitly says retry timing is product-specific and *"Do not implement one assumed schedule for every Telnyx webhook"*; the Voice page defers back to fundamentals — circular, so this is a genuine gap).

---

## 8. Call Control vs TeXML for the Vocify flow

Our flow: server picks the caller ID → **play a Spanish disclosure to the CALLED party only** → then bridge → dual-channel WAV recording.

### Is there a TeXML equivalent of Twilio's `<Number url="...">`? **YES — the attribute exists with the same name.**
DOCUMENTED — `https://developers.telnyx.com/docs/voice/programmable-voice/texml-verbs/dial.md`, "Number Attributes" table, attribute `url`, verbatim:
> *"Optional URL to another TeXML document that can contain `<Gather>` and `<Hangup>` verbs so that the called party can chose to take an action on the incoming call before the two parties are connected. The callee will continue to hear ringback while the url document is executed."*

Identical `url` + `method` attributes also exist on the `<Sip>` noun. (`<Queue url>` is documented more broadly: *"can contain `<Play>`, `<Say>`, `<Gather>`, `<Pause>` and `<Redirect>` verbs. The document will be executed on the queued call before bridging the calls."*)

Two caveats, stated plainly:
1. **The verb whitelist as written is narrower than Twilio's.** Telnyx names only `<Gather>` and `<Hangup>` for `<Number url>` — it does **not** name `<Say>` or `<Play>`. Twilio's `<Number url>` documents `<Say>`/`<Play>` directly. Whether bare `<Say>`/`<Play>` work inside a Telnyx `<Number url>` document is **NOT DOCUMENTED**.
   - Documented workaround: **`<Gather>` accepts nested `<Say>` and `<Play>`.** Verbatim: *"`<Say>` can be nested within `<Gather>` to create an interactive IVR with text-to-speech"*, and its "Child verbs/nouns" table lists `Say` and `Play`. (`https://developers.telnyx.com/docs/voice/programmable-voice/texml-verbs/gather.md`) So `<Gather numDigits="1" timeout="0"><Say language="es-ES">…</Say></Gather>` (or `<Play>` of our recorded Spanish disclosure) inside the `<Number url>` document is the documented composition. This is INFERRED-FROM-TWO-DOCS — it composes two documented facts and is not shown as an example anywhere. **Must be validated on a real call before relying on it for AEPD compliance.**
2. **The caller/callee wording is contradictory.** Telnyx writes *"The **callee** will continue to hear ringback while the url document is executed."* Twilio's equivalent sentence says the **caller** hears ringing while the callee's document runs. Taken literally, Telnyx's sentence would mean the called party hears ringback *and* the disclosure simultaneously — which cannot be the intent. This is very likely a doc typo, but **NOT DOCUMENTED which party hears what.** Verify by listening on both legs.

### Which product supports our flow?
| Requirement | Call Control | TeXML |
|---|---|---|
| Server decides caller ID per call | DOCUMENTED — `from` on `POST /v2/calls` | DOCUMENTED — `<Dial callerId="+E164">`, plus `fromDisplayName` |
| Disclosure to the **callee only**, before bridge | **DOCUMENTED, unambiguous** — dial leg B, do **not** bridge; run `playback_start` (`/v2/calls/{id}/actions/playback_start`) or `speak` (`.../actions/speak`) against leg B's own `call_control_id`; on `call.playback.ended`, issue `bridge`. Per-leg addressing is inherent to the model. | DOCUMENTED that `<Number url>` exists; **PARTIALLY DOCUMENTED** that you can play audio in it (via nested `<Gather>`); ambiguous ringback wording |
| Dual-channel | DOCUMENTED — `record_channels: "dual"` | DOCUMENTED — `record="record-from-answer-dual"` / `recordingChannels="dual"` |
| WAV explicitly selectable | **DOCUMENTED** — `record_format: "wav"` / `format: "wav"` | **NOT DOCUMENTED** — no format attribute on `<Dial>` |
| Record automatically from answer | DOCUMENTED — `record: "record-from-answer"` on dial/answer/bridge/transfer | DOCUMENTED — `record-from-answer-dual` |
| Webhook shape | JSON `data`-envelope, Ed25519 signed | form-encoded (Twilio-like), Ed25519 signed |

**Recommendation implied by the documentation (not a doc claim):** **Call Control.** It is the only one of the two where *both* of our two hard requirements — explicit `format: "wav"` alongside `channels: "dual"`, and a per-leg "play to the callee only, then bridge" sequence — are documented outright rather than composed from adjacent facts. TeXML's advantage is that `record="record-from-answer-dual"` and `recordingStatusCallback` are literally the same identifiers we already send to Twilio, so a TeXML port is a smaller diff — but it trades away the documented WAV guarantee and leaves the AEPD disclosure mechanism resting on an inference plus a contradictory sentence about who hears ringback.

---

## Residual gaps to close before committing (all confirmed NOT DOCUMENTED)
1. Explicit confirmation that `channels: "dual"` + `format: "wav"` is a valid combination and yields true 2-channel WAV with the two bridged legs separated. → empirical test.
2. TeXML `<Dial>` recording format. → empirical test, or use Call Control.
3. Auth model and lifetime of `download_urls` from `GET /v2/recordings/{id}`.
4. Retention: no automatic deletion window is published; storage bills per stored minute, so the absence of auto-deletion is cost-relevant. → get it in writing.
5. Semantics of the 10,000-minute storage tier boundary (free allowance? per month?).
6. Retry schedule for `call.recording.saved` specifically.
7. Whether `<Say>`/`<Play>` work bare inside a TeXML `<Number url>` document, and which leg hears ringback during it.
8. EU/Spain data locality for recordings held on Telnyx's own S3 (AEPD/GDPR).

## Sources actually fetched (2026-08-27)
- `https://developers.telnyx.com/docs/voice/programmable-voice/recording` — **404, stale**
- `https://developers.telnyx.com/llms.txt`
- `https://developers.telnyx.com/docs/development/llms/calling-voice-api-llms-txt` (+ `-full-txt`)
- `https://developers.telnyx.com/docs/development/llms/calling-texml-llms-txt` (+ `-full-txt`)
- `https://developers.telnyx.com/api-reference/call-commands/recording-start.md`
- `https://developers.telnyx.com/api-reference/call-commands/dial.md`
- `https://developers.telnyx.com/api-reference/call-commands/bridge-calls.md`
- `https://developers.telnyx.com/api-reference/call-commands/answer-call.md`
- `https://developers.telnyx.com/api-reference/call-commands/transfer-call.md`
- `https://developers.telnyx.com/api-reference/call-recordings/retrieve-a-call-recording.md`
- `https://developers.telnyx.com/api-reference/call-recordings/list-all-call-recordings.md`
- `https://developers.telnyx.com/api-reference/call-recordings/delete-a-call-recording.md`
- `https://developers.telnyx.com/api-reference/callbacks/call-recording-saved.md`
- `https://developers.telnyx.com/api-reference/callbacks/call-recording-error.md`
- `https://developers.telnyx.com/api-reference/callbacks/texml-recording-completed.md`
- `https://developers.telnyx.com/docs/voice/programmable-voice/storing-call-recordings.md`
- `https://developers.telnyx.com/docs/voice/programmable-voice/voice-api-commands-and-resources.md`
- `https://developers.telnyx.com/docs/voice/programmable-voice/voice-api-webhooks.md`
- `https://developers.telnyx.com/docs/voice/programmable-voice/texml-verbs/dial.md`
- `https://developers.telnyx.com/docs/voice/programmable-voice/texml-verbs/record.md`
- `https://developers.telnyx.com/docs/voice/programmable-voice/texml-verbs/gather.md`
- `https://developers.telnyx.com/docs/voice/texml/rest-api/recordings.md`
- `https://developers.telnyx.com/api-reference/texml-rest-commands/initiate-an-outbound-call.md`
- `https://developers.telnyx.com/api-reference/texml-rest-commands/request-recording-for-a-call.md`
- `https://developers.telnyx.com/api-reference/texml-rest-commands/fetch-recording-resource.md`
- `https://developers.telnyx.com/docs/development/api-fundamentals/webhooks/receiving-webhooks.md`
- `https://developers.telnyx.com/docs/development/sdk/python/webhooks.md`
- `https://developers.telnyx.com/docs/development/sdk/node/webhooks.md`
- `https://developers.telnyx.com/data/webhook-events.json`
- `https://raw.githubusercontent.com/team-telnyx/openapi/master/openapi/spec3.json`
- `https://raw.githubusercontent.com/team-telnyx/telnyx-python/master/src/telnyx/lib/webhook_verification.py`
- `https://raw.githubusercontent.com/team-telnyx/telnyx-python/master/src/telnyx/lib/webhooks_ed25519.py`
- `https://telnyx.com/pricing.md`
