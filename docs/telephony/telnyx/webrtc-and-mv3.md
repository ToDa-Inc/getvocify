# Telnyx Browser/WebRTC SDK — Feasibility in a Chrome MV3 Extension Offscreen Document

Research date: 2026-08-27
Scope: `@telnyx/webrtc` JS SDK only. Evaluated against an existing Twilio Voice JS SDK
implementation that loads a prebuilt UMD bundle as a classic script in an MV3 offscreen
document, with **no bundler** in the extension.

Every claim below is tagged:

- **VERIFIED BY INSPECTION** — command output from the actual published package, reproduced inline.
- **DOCUMENTED** — traceable to a URL that was actually fetched.
- **NOT DOCUMENTED** — docs are silent; no source found.

---

## TL;DR — the two decision-critical findings

1. **A no-bundler UMD bundle EXISTS.** `lib/bundle.js` is a real UMD wrapper that attaches
   `globalThis.TelnyxWebRTC`. It loads as a classic `<script>` with zero build tooling.
   Telnyx's own docs use `TelnyxWebRTC.TelnyxRTC` and a `<script src=...>` tag.
   **No build step needs to be added.**
2. **Server-authoritative caller ID EXISTS**, via the SIP Connection setting
   **"Park Outbound Calls"** (`outbound.call_parking_enabled: true`). With it enabled, the
   browser-originated leg is *parked* and never reaches the destination; the browser's
   `callerNumber` is not what the callee sees. The backend receives `call.initiated`
   (`state: "parked"`), then issues `POST /v2/calls` with a **server-chosen `from`** and
   bridges. This is a structural equivalent of the Twilio TwiML-App webhook trust model.

Both feasibility gates pass.

---

## 1. Package shape

### Version — VERIFIED BY INSPECTION

```
$ npm view @telnyx/webrtc version dist-tags time.modified
version = '2.27.10'
dist-tags = { latest: '2.27.10', beta: '2.27.10-beta.3' }
time.modified = '2026-08-21T16:54:49.621Z'
```

Latest published: **2.27.10**. Tarball `telnyx-webrtc-2.27.10.tgz` = 188,600 bytes.

### There is NO `dist/` directory — VERIFIED BY INSPECTION

The package ships `lib/`, not `dist/`. Only **two** JS files exist in the whole package;
everything else is `.d.ts` type declarations plus `README.md`.

```
$ find package -type f -name '*.js' -o -name '*.mjs'
package/lib/bundle.js
package/lib/bundle.mjs

$ wc -c package/lib/bundle.js package/lib/bundle.mjs
  273634 package/lib/bundle.js
  272737 package/lib/bundle.mjs
  546371 total
```

| File | Bytes | Format |
|---|---|---|
| `lib/bundle.js` | **273,634** (267.2 KiB) | **UMD** |
| `lib/bundle.mjs` | 272,737 (266.3 KiB) | ESM |

For scale: the Twilio UMD bundle in the current implementation is ~302 KB. Telnyx's UMD
bundle is **~274 KB — slightly smaller**.

### Declared entry points — VERIFIED BY INSPECTION

From `package/package.json`:

```json
"main":   "lib/bundle.js",
"module": "lib/bundle.mjs",
"types":  "lib/src/index.d.ts",
"files":  ["lib", "README.md"]
```

- `main` → `lib/bundle.js` (UMD)
- `module` → `lib/bundle.mjs` (ESM)
- `types` → `lib/src/index.d.ts`
- **`browser`** — NOT DECLARED
- **`unpkg`** — NOT DECLARED
- **`exports`** — NOT DECLARED (no modern conditional-exports map; this is *helpful* here,
  because it means no export-map gate blocks direct deep file access)
- **`jsdelivr`** — NOT DECLARED

Because neither `browser` nor `exports` is declared, CDNs fall back to `main`, i.e. the UMD
file. Confirmed live:

```
$ curl -sIL "https://unpkg.com/@telnyx/webrtc"
HTTP/2 302
location: /@telnyx/webrtc@2.27.10/lib/bundle.js
HTTP/2 200

$ curl -sIL "https://cdn.jsdelivr.net/npm/@telnyx/webrtc"
HTTP/2 200
content-type: application/javascript; charset=utf-8
x-jsd-version: 2.27.10
content-length: 273912
```

### It IS UMD and it DOES attach a global — VERIFIED BY INSPECTION

The first 220 bytes of `lib/bundle.js` are a textbook UMD preamble:

```js
!function(e,t){
  "object"==typeof exports && "undefined"!=typeof module ? t(exports)          // CJS
  : "function"==typeof define && define.amd ? define(["exports"],t)            // AMD
  : t((e=e||self).TelnyxWebRTC={})                                             // GLOBAL
}(this,(function(e){"use strict"; ...
```

The third branch assigns to `(self).TelnyxWebRTC`. In a classic `<script>` there is no
`module`/`exports` and no AMD `define`, so this branch is taken.

**Global name: `TelnyxWebRTC`** (a namespace object, not the constructor directly).

I confirmed this empirically rather than by reading the minified source alone, by executing
the bundle in a bare VM context that mimics a classic-script browser load (no `module`, no
`exports`, no `define`):

```
$ node probe.js
LOADED OK as classic script (no CJS/AMD present)
NEW GLOBALS CREATED: ["TelnyxWebRTC"]
TelnyxWebRTC EXPORT KEYS: Call, ERROR_TYPE, IceReasonCode,
  MICROPHONE_RECORDING_NOTICE, MicrophoneReasonCode, NOTIFICATION_TYPE,
  MicrophoneReasonCode, NetworkReasonCode, PreCallDiagnosis, PreCallDiagnostic,
  Region, SDK_ERRORS, SDK_WARNINGS, SwEvent, TELNYX_ERROR_CODES,
  TELNYX_ICE_SERVERS, TELNYX_WARNING_CODES, TelnyxError, TelnyxRTC,
  TimingsCollector, createTimingsCollector, isFunctionCallOutputParams,
  isFunctionCallParams, isMediaRecoveryErrorEvent
typeof TelnyxWebRTC.TelnyxRTC = function
```

Exactly one global is created, and `TelnyxWebRTC.TelnyxRTC` is the constructor.

So the access pattern is `new TelnyxWebRTC.TelnyxRTC({...})` — one level deeper than
Twilio's `Twilio.Device`, but structurally identical.

---

## 2. Bundler requirement

**A bundler is NOT required.** — VERIFIED BY INSPECTION + DOCUMENTED

The README is misleading on this point. It says
(`package/README.md`, and https://github.com/team-telnyx/webrtc/blob/main/packages/js/README.md):

> "As long as you can import npm packages with a bundler like Webpack, you're ready to
> import `TelnyxRTC` and begin"

and only ever shows `import { TelnyxRTC } from '@telnyx/webrtc'`. Taken at face value this
suggests a build step is mandatory. **It is not** — the README simply never mentions the UMD
path. The UMD build demonstrably exists (§1) and Telnyx's *developer docs* do document the
script-tag path:

**Evidence A — docs use a plain `<script>` tag + CDN.** DOCUMENTED
Source: https://developers.telnyx.com/docs/development/llms/calling-webrtc-llms-full-txt
(the "full content" export of the WebRTC docs section, discovered via
https://developers.telnyx.com/llms.txt)

```html
<script src="https://cdn.jsdelivr.net/npm/@telnyx/webrtc"></script>
<script>
  const response = await fetch('/api/telnyx-token');
  const { token } = await response.json();
  client = new TelnyxRTC({ login_token: token, enableCallReports: true });
  ...
</script>
```

> **Caveat — this specific snippet is buggy.** It writes bare `new TelnyxRTC(...)`, but the
> UMD bundle namespaces under `TelnyxWebRTC`. Per the inspection in §1 the correct call is
> `new TelnyxWebRTC.TelnyxRTC(...)`. Do not copy this snippet verbatim.

**Evidence B — the Outbound Dialer guide uses the UMD global correctly.** DOCUMENTED
Source: https://developers.telnyx.com/docs/voice/webrtc/use-cases/outbound-dialer.md

```javascript
client = new TelnyxWebRTC.TelnyxRTC({
  env: env,
  login: document.getElementById('username').value,
  password: document.getElementById('password').value,
  ringtoneFile: './sounds/incoming_call.mp3',
});
```

This is Telnyx's own documentation using `TelnyxWebRTC.TelnyxRTC` — matching the inspected
global exactly. This is the authoritative confirmation of the no-bundler path.

### Bundle is fully self-contained — VERIFIED BY INSPECTION

The three runtime dependencies declared in `package.json`
(`@peermetrics/webrtc-stats`, `loglevel`, `uuid`) are all inlined by Rollup. There are no
runtime module resolutions:

```
$ grep -o "import[^a-zA-Z][^;]\{0,60\}" bundle.js
(no output — no bare module specifiers)

$ grep -o '.\{60\}require.\{60\}' bundle.js
(13 hits, ALL inside error-message string literals, e.g.
 "Error: destinationNumber is required", "AUTHENTICATION_REQUIRED", ...
 — zero actual require() calls)
```

`npm install` is therefore not needed at all: the single file `lib/bundle.js` can be vendored
into the extension directory and referenced directly. This matters for MV3, which forbids
remotely-hosted code — the CDN URL above must NOT be used in the extension; the file must be
copied in locally.

### Practical consequence

Twilio today:
```html
<script src="vendor/twilio.min.js"></script>   <!-- globalThis.Twilio.Device -->
```
Telnyx equivalent:
```html
<script src="vendor/telnyx-bundle.js"></script> <!-- globalThis.TelnyxWebRTC.TelnyxRTC -->
```

Same integration shape. **No build step needs to be introduced.**

---

## 3. Dependencies, CSP, and MV3 compatibility of the bundle

### No `eval` / `new Function` — VERIFIED BY INSPECTION

MV3's default CSP for extension pages is
`script-src 'self'; object-src 'self'` — it forbids `unsafe-eval`. The bundle is clean:

```
$ for p in 'new Function' 'eval(' 'Function(' 'require(' 'process\.' 'Buffer' \
           '__dirname' 'importScripts' 'unsafe-eval' 'WebAssembly' \
           'document\.write' 'innerHTML'; do
    printf '%-18s : %s\n' "$p" "$(grep -o "$p" bundle.js | wc -l | tr -d ' ')"
  done

new Function       : 0
eval(              : 0
Function(          : 0
require(           : 0
process\.          : 0
Buffer             : 40
__dirname          : 0
importScripts      : 0
unsafe-eval        : 0
WebAssembly        : 0
document\.write    : 0
innerHTML          : 0
```

Every count that matters is **zero**. No dynamic code evaluation, so the default MV3 CSP is
satisfied without relaxation.

### The 40 `Buffer` hits are NOT Node's Buffer — VERIFIED BY INSPECTION

```
$ grep -o '.\{12\}Buffer' bundle.js | sort -u
&(this.statsBuffer      ,this.statsBuffer      0!==n.jitterBuffer
.options.maxBuffer      /e*500)}_maxBuffer     Delay,jitterBuffer
RecordingMaxBuffer      arded,jitterBuffer     ched its maxBuffer
e3,this._maxBuffer      elay?{jitterBuffer     es:this._maxBuffer
...
```

All are `statsBuffer`, `jitterBuffer`, `maxBuffer`, `RecordingMaxBuffer` — WebRTC stats
identifiers. **No Node.js `Buffer` polyfill is needed.** Likewise no `process`, no
`__dirname`. There are no Node-only APIs and no polyfill requirements.

### Browser APIs used — VERIFIED BY INSPECTION

```
navigator.mediaDevices  : 37
RTCPeerConnection       : 12
sessionStorage          : 15
localStorage            :  3
document.createElement  :  2
new Audio               :  2
beforeunload            :  5
window.addEventListener :  3
globalThis              :  2
self.                   :  0
```

**Implication for MV3 placement:** the SDK touches `document`, `new Audio`,
`sessionStorage`/`localStorage`, and `beforeunload`. All of these are **available in an
offscreen document** (a real `chrome-extension://` DOM page) and **unavailable in a service
worker**. So the offscreen-document placement already in use for Twilio is the correct — and
the only viable — host. Running this SDK directly in the MV3 service worker is not possible.
(Chrome offscreen API reference: https://developer.chrome.com/docs/extensions/reference/api/offscreen
— "Service workers don't have DOM access… The runtime API is the only extensions API
supported by offscreen documents.")

Note `localStorage` is used by the inlined `loglevel` dependency for log-level persistence,
wrapped in `try{}catch{}`; `sessionStorage` is used by the SDK's own session/reconnect
bookkeeping. Both are fine in an offscreen document.

### Network endpoints the CSP must permit — VERIFIED BY INSPECTION

```
$ grep -oE 'wss?://[a-zA-Z0-9./_@:-]+' bundle.js | sort -u
wss://rtc.telnyx.com
wss://rtcdev.telnyx.com

$ grep -oE '(stun|turn):[a-zA-Z0-9./_@:?=-]+' bundle.js | sort -u
stun:stun.l.google.com:19302
stun:stun.telnyx.com:3478
stun:stundev.telnyx.com:3478
turn:turn.telnyx.com:3478?transport=tcp
turn:turn.telnyx.com:3478?transport=udp
turn:turndev.telnyx.com:3478?transport=tcp
turn:turndev.telnyx.com:3478?transport=udp
```

Signaling is JSON-RPC over secure WebSocket to `wss://rtc.telnyx.com`
(DOCUMENTED: https://developers.telnyx.com/docs/voice/webrtc —
"Implements the WebRTC session negotiation, aka signaling, via JSON-RPC messages over
Secure WebSocket (WSS)"). `connect-src` must allow `wss://rtc.telnyx.com`.

Note it also embeds a **Google** STUN server (`stun.l.google.com:19302`) in its default ICE
configuration. If that is unacceptable, `iceServers` is overridable per-client and per-call
(DOCUMENTED: https://developers.telnyx.com/docs/development/webrtc/js-sdk/reference/icalloptions.md).

### Documented CSP requirements

**NOT DOCUMENTED.** No Telnyx page found states a Content-Security-Policy requirement, lists
required CSP directives, or discusses `unsafe-eval`. The CSP conclusions above are derived
from inspection of the bundle, not from Telnyx documentation.

---

## 4. Authentication model

### Three-level hierarchy — DOCUMENTED

Source: https://developers.telnyx.com/docs/voice/webrtc/sdk-commonalities (Authentication),
plus the three auth sub-pages below.

```
Credential Connection            (parent SIP connection; has user_name + password)
  └── Telephony Credential       (per-device SIP identity; sip_username = "gencred...")
        └── JWT                  (short-lived token minted from the credential)
```

- Credential Connections: https://developers.telnyx.com/docs/voice/webrtc/auth/credential-connections
- Telephony Credentials: https://developers.telnyx.com/docs/voice/webrtc/auth/telephony-credentials
- JWTs: https://developers.telnyx.com/docs/voice/webrtc/auth/jwt

### The browser does NOT need a long-lived SIP password — DOCUMENTED

This is the key security answer. The SDK accepts **either** a JWT **or** raw SIP
credentials, and the JWT path is the recommended one.

`IClientOptions` — VERIFIED BY INSPECTION (`lib/src/utils/interfaces.d.ts`):

```ts
export interface IClientOptions {
    login_token?: string;   // JWT  ← use this
    login?: string;         // SIP username
    password?: string;      // SIP password ← do NOT ship to a browser
    ...
}
```

README (`package/README.md`) explicitly warns against the credential path:

> "Important: You should treat Connection credentials as sensitive data and should not
> hardcode credentials into your frontend web application."

So: **use `login_token` only. A long-lived SIP username/password is never required in the
browser.** This is architecturally equivalent to Twilio's AccessToken model.

### Exact API call to mint the token — DOCUMENTED

Source: https://developers.telnyx.com/docs/voice/webrtc/auth/jwt

**Step 1 (one-time per device/agent) — create a telephony credential:**

```http
POST /v2/telephony_credentials HTTP/1.1
Host: api.telnyx.com
Authorization: Bearer XXX
Content-Type: application/json

{
  "connection_id": "<credential_connection_id>",
  "expires_at": "2024-09-18T00:00:00"
}
```

`expires_at` is optional; docs say it "is recommended for security especially when many are
expected to be created."

**Step 2 (repeatable) — mint a JWT from that credential:**

```http
POST /v2/telephony_credentials/:id/token HTTP/1.1
Host: api.telnyx.com
Authorization: Bearer XXX
```

Response is the JWT string, passed to the SDK as `login_token`.

### TTL — DOCUMENTED

> "This JWT is valid until:
> - **24 hours** after its creation or
> - the parent telephony credential is expired
>
> whichever comes first"

**24 hours** — versus Twilio AccessToken's 1 hour. This is a **longer** window, i.e.
marginally *worse* blast radius per leaked token, but the same class of secret (short-lived,
mintable server-side, revocable). Two mitigations are documented:

- Set `expires_at` on the parent telephony credential to cap the whole chain.
- **Revocation:** `DELETE /v2/telephony_credentials/:id` — docs state "A client-side
  application's voice capabilities can be revoked by removing the corresponding credential."
  This is a genuine kill-switch Twilio's stateless JWTs do not offer.

Limits: "No limit on count of tokens on a telephony credential, nor any limit on the
aggregate count of tokens on a single account." So short-TTL rotation is not rate-capped.

### Operational gotcha — DOCUMENTED

> "Telephony credential creation is not guaranteed to be immediately usable for SDK login or
> registration… If you create credentials on demand, **wait about 5 seconds** before the
> first login or registration attempt."

This repeats on the credential-connections page and the JWT page. It applies to the
credential *and* to a JWT minted from a freshly created credential. **Do not create the
telephony credential lazily at click-to-call time** — provision it per user ahead of time and
only mint JWTs on demand (minting a JWT from an *established* credential has no documented
delay).

Registration can be verified server-side:

```http
GET /v2/sip_registration_status?credential_type=telephony_credential&username=gencredabc123
```

### Best practice — DOCUMENTED

> "For multi-user applications, create a separate telephony credential per device"
> "JWTs minted from the same telephony credential still represent the same `sip_username`"

One telephony credential per agent/device. Multi-client registration on the same credential
has explicitly **indeterminate** routing behavior for inbound calls
(the docs' multi-client table says "Indeterminate; the last client to register").

---

## 5. Making an outbound PSTN call from the browser

### API — DOCUMENTED + VERIFIED BY INSPECTION

```javascript
const call = client.newCall({
  destinationNumber: '+12345678900',   // required, E.164 for PSTN, or sip:user@domain
  audio: true,
  callerName: 'Acme Corp',
  callerNumber: '+18005551234',
  customHeaders: [
    { name: 'X-Customer-ID', value: '12345' },
    { name: 'X-Agent-Name', value: 'john.doe' },
  ],
});
```

Source: https://developers.telnyx.com/docs/development/webrtc/js-sdk/reference/icalloptions.md

### Caller ID parameter — DOCUMENTED

Per the `ICallOptions` reference table:

| Property | Type | Description |
|---|---|---|
| `callerName` | `string` | Display name shown to the remote party (Caller ID name) |
| `callerNumber` | `string` | **Phone number shown to the remote party (Caller ID number)** |
| `customHeaders` | `SipHeader[]` | Custom SIP headers to include in the INVITE. Each header has `name` and `value`. |

So **`callerNumber`** is the browser-side caller-ID parameter. **Read §6 before relying on
it** — with Park Outbound Calls enabled it is not what the callee sees.

### Application metadata / CRM correlation — DOCUMENTED + VERIFIED BY INSPECTION

There are three viable mechanisms, and `customHeaders` is the direct analogue of what you
want.

**(a) `customHeaders` — custom SIP `X-` headers. This is the recommended mechanism.**

Confirmed in the published typings (`lib/src/utils/interfaces.d.ts`, `ICallOptions`):

```ts
customHeaders?: { name: string; value: string; }[];
```

and also on `AnswerParams` and `IHangupParams.dialogParams` (so headers can be attached at
answer and hangup too) — VERIFIED BY INSPECTION.

Crucially, **these headers are surfaced to your backend in the webhook payload.** The
`call.initiated` example for the WebRTC-originated parked leg includes them
(DOCUMENTED: https://developers.telnyx.com/docs/voice/webrtc/use-cases/outbound-dialer.md):

```json
{
  "data": {
    "event_type": "call.initiated",
    "payload": {
      "call_control_id": "...",
      "call_leg_id": "...",
      "call_session_id": "...",
      "custom_headers": [
        { "header_name": "X-Custom-Header", "header_value": "CustomValue" }
      ],
      "client_state": "optional_client_defined_state",
      "from": "+12345678901",
      "to": "+10987654321",
      "direction": "outgoing",
      "state": "parked"
    }
  }
}
```

This is the functional equivalent of Twilio's TwiML-App POST parameters: the browser attaches
`X-CRM-Contact-Id: <id>`, and the backend reads `payload.custom_headers` on
`call.initiated` and correlates. **This is the mechanism to use for CRM correlation.**

> Security note: `custom_headers` are browser-supplied and therefore **untrusted input**.
> Treat the CRM contact id as a claim to be authorized against the authenticated agent
> (identified by the parked leg's telephony credential / `sip_username`), not as
> ground truth. Same discipline as Twilio TwiML POST params.

**(b) `clientState`** — VERIFIED BY INSPECTION in `ICallOptions`:
```ts
clientState?: string;
```
Appears in webhook payloads as `client_state`, described in the Voice API docs as
"Base64-encoded state passed through from a previous command" / "Use this field to add state
to every subsequent webhook. It must be a valid Base-64 encoded string."
(DOCUMENTED: https://developers.telnyx.com/docs/development/llms/calling-voice-api-llms-full-txt).
Server-side it is updatable mid-call via
`POST /v2/calls/:call_control_id/actions/client_state_update`.
It threads through *all* subsequent webhooks, so it is well-suited to carrying a correlation
id for the whole call session.

**(c) `userVariables`** — VERIFIED BY INSPECTION. Present on the internal
`IVertoCallOptions` (`lib/src/Modules/Verto/webrtc/interfaces.d.ts`) as
`userVariables?: Record<string, any>`, but **absent from the public `ICallOptions`** and
absent from the public docs reference. **Its propagation to webhooks is NOT DOCUMENTED.**
Do not build on it.

Also present on `ICallOptions` and worth noting for correlation:
`telnyxCallControlId`, `telnyxSessionId`, `telnyxLegId` — VERIFIED BY INSPECTION. Their
intended semantics for outbound calls are NOT DOCUMENTED in the reference table.

---

## 6. Server-side control — the security crux

### Answer: YES, Telnyx has a server-authoritative hook. It is called "Park Outbound Calls".

This is the direct structural equivalent of the Twilio TwiML-App webhook model.

### The architecture is explicitly documented as requiring a backend — DOCUMENTED

Source: https://developers.telnyx.com/docs/voice/webrtc/architecture.md

Telnyx states this in unusually blunt section headings:

> **"WebRTC Voice SDKs CANNOT be used on its own for calling"**
> "They merely lower the barriers for users to incorporate voice functionalities in their
> applications, i.e. instantiate a call leg."

> **"WebRTC Voice SDKs CANNOT be used on its own to orchestrate call flow"**
> "They merely allow some form of local control, e.g. un/hold, un/mute, sending DTMF digits.
> To orchestrate call flow or manipulate audio, TeXML or Call Control API must be used."
>
> "* **The call leg instantiated by the SDK must be parked via a setting on the SIP
> connection.**
> * The user's backend must
>   * respond to Telnyx webhooks,
>   * inject the necessary custom Text-To-Speach audio,
>   * **place another outbound leg to the intended PSTN destination** (or hangup due to
>     insufficient balance), and finally,
>   * **bridge the WebRTC call leg with the PSTN leg**"

And the canonical "Pattern 1" (same source / fundamentals page):

> "* A client-end application (Web or Mobile App) initiates a call.
> * **The call is temporarily parked by Telnyx.**
> * Telnyx issues a webhook event to the user's backend service.
> * User's backend service performs additional processing using Telnyx Voice API, TeXML or
>   Conferencing API.
> * Depending on user's business logic, a second call leg may be initiated by the user's
>   backend and bridged to the initial call leg…"

### What "Park Outbound Calls" does — DOCUMENTED

Source: https://support.telnyx.com/en/articles/4351104-sip-connection-settings

> "The Park Outbound Calls feature provides a simple mechanism for users to 'park' their
> outbound calls **instead of connecting them to their destination**. The call then awaits
> further orders from its connected voice api application. In the meantime, Telnyx will have
> generated a SIP 180 Ringing message to instruct the client to generate local ringback."

And the exact intended use case, spelled out:

> "The typical use case for enabling this feature on a SIP Connection with a webhook url is
> where you have:
> - A voice api application that shares the same webhook url as the SIP Connection.
> - Where the SIP Connection is using credentials as the authentication type
> - **Where the callers are typically using a WebRTC client to register with our WebRTC
>   gateway (rtc.telnyx.com)** using the credentials of the SIP Connection.
> - Where the callers of the WebRTC client make outbound calls from the SIP Connection.
> - Where the events are posted to the webhook url of the SIP Connection.
> - **That then knows to issue a dial command to the number the caller wants to connect with
>   while the caller is in a parked state.**
> - And when that leg of the call is answered, the backend application can issue a **bridge**
>   command via our API with the callers unique call control id in order to unpark the caller
>   and connect them with their destination."

That is precisely the trust model in question, described by Telnyx as the intended design.

### Enabling it — DOCUMENTED

Two settings on the credential connection
(https://developers.telnyx.com/docs/voice/webrtc/auth/credential-connections):

```http
PATCH /v2/credential_connections/:id HTTP/1.1
Host: api.telnyx.com
Authorization: Bearer XXX
Content-Type: application/json

{
    "webhook_event_url": "https://mywebhook.com/primary",
    "webhook_event_failover_url": "https://mywebhook.com/backup",
    "webhook_api_version": "2",
    "webhook_timeout_secs": 25,
    "outbound": {
        "call_parking_enabled": true,
        "outbound_voice_profile_id": "123412415234124"
    }
}
```

Note the docs label this exact block as: "For call flows that make use of **Pattern 1** …
the following additional configuration is required." Pattern 1 is the client-initiated,
park-and-bridge flow.

Webhook events available at the SIP Connection level (support article): Call Initiated,
Call Answered, Call Bridged, Call Hangup.

### The resulting flow — DOCUMENTED

Source: https://developers.telnyx.com/docs/voice/webrtc/use-cases/outbound-dialer.md

1. **Client registers** — `client.connect()` against `rtc.telnyx.com`.
2. **Client requests a call** — `client.newCall({ destinationNumber, callerNumber })`.
   Telnyx **parks** this leg. Docs: "This request is routed from the front-end WebRTC client
   application to the back-end server application, which acts as the intermediary between
   the client and Telnyx for controlling call logic."
3. **Backend receives `call.initiated`** with `"state": "parked"`, `"direction": "outgoing"`,
   `call_control_id`, `custom_headers`, `client_state`. Docs: "Telnyx acknowledges the
   initiation of the call process by triggering a `call.initiated` webhook to the backend
   server."
4. **Backend dials PSTN with a caller ID IT chooses:**
   ```bash
   curl -X POST https://api.telnyx.com/v2/calls \
     -H 'Authorization: Bearer YOUR_API_TOKEN' \
     -d '{
       "connection_id": "YOUR_CONNECTION_ID",
       "to":   "+E.164 PSTNNUMBER",
       "from": "+E.164 CALLERNUMBER",
       "webhook_url": "https://yourserver.app/telnyx-webhooks"
     }'
   ```
5. **`call.answered`** webhook when the PSTN side picks up.
6. **Backend bridges the two legs:**
   ```bash
   curl -X POST https://api.telnyx.com/v2/calls/{call_control_id_WebRTC}/actions/bridge \
     -H 'Authorization: Bearer YOUR_API_TOKEN' -d '{...}'
   ```
7. **`call.bridged`** webhook — agent and PSTN party are connected.
8. **`call.hangup`** on teardown.

### Why this resolves the security question

The caller ID presented to the callee is the **`from` field on the backend-originated
`POST /v2/calls` leg** — chosen by your server, authenticated with your server-side API key.
The browser's `callerNumber` on the parked leg is metadata on a leg that **never reaches the
destination**. The browser therefore **cannot dictate the presented caller ID**, exactly as
with TwiML. Your backend remains the sole authorization point, and it has the parked leg's
authenticated identity (`sip_username` / telephony credential) available for authorizing the
requested caller ID.

Additional relevant `POST /v2/calls` parameters — DOCUMENTED
(https://developers.telnyx.com/api-reference/call-commands/dial):

- `from` — the presented caller ID number.
- `from_display_name` — "The `from_display_name` string to be used as the caller id name
  (SIP From Display Name) presented to the destination (`to` number). The string should have
  a maximum of 128 characters… If ommited, the display name will be the same as the number in
  the `from` field."
- `custom_headers` — "Custom headers to be added to the SIP INVITE."
- `client_state` — Base64 state threaded through subsequent webhooks.
- `link_to` — "Use another call's control id for sharing the same call session id."
- `bridge_intent` / `bridge_on_answer` — for the bridge flow. Note the documented behavior of
  `bridge_intent`: "When `bridge_intent` is true, `link_to` becomes required and **the `from`
  number will be overwritten by the `from` number from the linked call**." Worth understanding
  before using it, since it changes which leg's `from` wins.

### Dual-channel recording — DOCUMENTED

Server-side, on the call control id, same as the Twilio setup:

```http
POST /v2/calls/:call_control_id/actions/record_start
```

Source: https://developers.telnyx.com/api-reference/call-commands/recording-start

The `channels` parameter schema:

```yaml
channels:
  description: >-
    When `dual`, final audio file will be stereo recorded with the first
    leg on channel A, and the rest on channel B.
  enum:
    - single
    - dual
  type: string
  example: single
```

So `{"channels": "dual", "format": "wav"}` gives dual-channel recording, initiated and
controlled entirely server-side. Other documented params include `client_state`,
`command_id`, `custom_file_name`, `play_beep`, `max_length`, `timeout_secs`.
Completion arrives as a `call.recording.saved` webhook.

Confirmed as a first-class positioning claim in the Voice API docs: "Call Control enables you
to quickly setup dynamic forwarding numbers, **toggle dual-channel recording**, join/leave
dynamic conferences, and pull post-call analytics."
(https://developers.telnyx.com/docs/development/llms/calling-voice-api-llms-full-txt)

### Caveats on Park Outbound Calls — DOCUMENTED

From the support article, all worth knowing before committing:

1. **Do not enable without a Voice API application.** "Please be careful enabling this
   setting if you are not using a voice api application to control the calls." Parked calls
   sit in ringback until a command arrives — with no backend, every outbound call hangs.
2. **Emergency calls bypass parking.** "When Park Outbound Calls is enabled, calls to
   emergency numbers (such as `911` in the US) will **not** be parked, they will be routed
   through the emergency flow as normal, ensuring critical calls always connect." Non-emergency
   special numbers (e.g. `711` relay) **are** parked. This is country-scoped to the caller's
   own country. **This means the server-authoritative caller-ID guarantee does not hold for
   emergency numbers** — a real, if narrow, gap to document in your threat model.
3. **Setting a webhook URL changes the call's billing/handling class.** "When setting a
   webhook url, it treats the call type as **programmable and not SIP trunking**." Combined
   with the AnchorSite warning: audio "may be anchored in a media server (anchorsite) further
   away than you intended because that region does not support programmable voice services
   yet. Example: Australia." Relevant to latency if you operate outside core regions.
4. **AnchorSite requires the username in the first INVITE.** "For credential based SIP
   Connections, please make sure to include the SIP Connections username in the contact
   header in your first SIP INVITE." Whether the JS SDK does this automatically is
   **NOT DOCUMENTED**.
5. **TeXML alternative.** Setting API Version to TeXML makes Telnyx "create a parked leg for
   your call and fetch the XML instructions that live on the webhook url you have specified"
   — form-encoded POST, closest 1:1 analogue to the current TwiML implementation. The
   Outbound Dialer guide notes: "SIP Connection with Park Outbound Calls Enabled (select
   TeXML option when using the TeXML approach)." This is likely the lowest-effort migration
   path from an existing TwiML backend.

### Cost — DOCUMENTED

"WebRTC call legs are billed at $0.002/minute. Other voice legs and add on features are
charged separately and independently."
(https://developers.telnyx.com/docs/voice/webrtc/fundamentals)
Note the park-and-bridge model means **two** legs per call (WebRTC leg + PSTN leg), both
billed.

---

## 7. MV3 / Chrome extension evidence

### Official documentation: NONE FOUND

No Telnyx page mentions Chrome extensions, Manifest V3, offscreen documents, or service
workers. Verified by grepping the complete WebRTC docs export (365,688 bytes,
https://developers.telnyx.com/docs/development/llms/calling-webrtc-llms-full-txt):

```
$ grep -niE 'chrome extension|extension|manifest|offscreen|service worker' webrtc-full.txt
665:  Android 14 requires explicit notification permissions… AndroidManifest.xml
822:  extension AppDelegate: PKPushRegistryDelegate {      # Swift
1146: #### 2. Configure the Android manifest
9848: …/ios-sdk/classes/call-extensions.md                  # Swift
```

Every hit is Android manifest or Swift `extension` syntax. **Zero browser-extension
content.** The supported-browsers table lists only Chrome/Firefox/Safari/Edge by OS — no
extension context.

### GitHub issues (`team-telnyx/webrtc`): NONE FOUND

```
$ curl "https://api.github.com/search/issues?q=repo:team-telnyx/webrtc+<query>"

QUERY: manifest+v3     → total_count: 0
QUERY: offscreen       → total_count: 0
QUERY: service+worker  → total_count: 0
QUERY: chrome+extension→ total_count: 2  (both false positives:
                            #190 "Dynamic bandwidth control",
                            #82  "docs: add typedoc on newCall method")
```

**No issue, PR, or discussion in the SDK repository references MV3, offscreen documents, or
service workers.**

### Community reports: NONE FOUND

A web search for `@telnyx/webrtc` + Chrome extension / offscreen / manifest v3 returned no
substantive result. The returned links were generic MV3/offscreen tutorials
(developer.chrome.com, openreplay, a StackOverflow question about *debugging* offscreen
pages) plus the Telnyx README and `team-telnyx/webrtc-demo-js` — the latter being a plain
React/TypeScript web app, **not** an extension. The search engine's AI-generated summary
asserted an offscreen-document approach, but it cited no primary source for
`@telnyx/webrtc` specifically and is **not treated as evidence here.**

### Assessment

**Evidence is ABSENT, not negative.** No one has documented running `@telnyx/webrtc` in an
MV3 extension, and equally no one has reported it failing. You would be first, with no
community precedent to lean on.

That said, the *technical* prerequisites check out by inspection (§1–§3):

| Requirement | Status |
|---|---|
| Prebuilt UMD bundle, no bundler | **YES** — VERIFIED BY INSPECTION |
| Attaches a global | **YES** — `TelnyxWebRTC` — VERIFIED BY INSPECTION |
| Self-contained (no `npm install`, no runtime `require`) | **YES** — VERIFIED BY INSPECTION |
| No `eval` / `new Function` (MV3 CSP) | **YES** — 0 occurrences — VERIFIED BY INSPECTION |
| No Node-only APIs / polyfills | **YES** — VERIFIED BY INSPECTION |
| Works in a DOM page (offscreen doc) | **YES** — uses `document`, `new Audio`, `sessionStorage` |
| Works in a service worker | **NO** — same DOM dependencies rule this out |
| Vendorable locally (MV3 no-remote-code) | **YES** — single 273,634-byte file |

The offscreen document is the correct host, and it is already in place for Twilio.

### Concrete integration notes for the shared offscreen document

- Vendor `lib/bundle.js` into the extension; **do not** load from jsDelivr/unpkg (MV3
  prohibits remotely-hosted code).
- Load as a classic script; access via `globalThis.TelnyxWebRTC.TelnyxRTC`.
- Offscreen document reason: Chrome documents both `AUDIO_PLAYBACK` and `WEB_RTC` reasons
  (https://developer.chrome.com/docs/extensions/reference/api/offscreen). Note the documented
  lifetime difference: "The `AUDIO_PLAYBACK` reason sets the document to close after 30
  seconds without audio playing. All other reasons don't set lifetime limits." Since the
  offscreen document is **shared with two other microphone features**, the existing reason
  set and lifetime management already have to accommodate this; adding `WEB_RTC` avoids the
  30-second idle close.
- CSP `connect-src` must permit `wss://rtc.telnyx.com`.
- The SDK wants a media element: `client.remoteElement = 'remoteMedia'` with
  `<audio id="remoteMedia" autoplay="true" />`. Because the offscreen document is shared,
  use the **per-call** `remoteElement` form to avoid the documented shared-element
  clobbering: README states "By default `client.remoteElement` is shared across all calls in
  a session — the last call to connect overwrites the element, and hanging up any call
  detaches the stream from it." Pass `remoteElement` inside `newCall({...})` /
  `answer({...})` instead.
- `hangupOnBeforeUnload` is an available `IClientOptions` flag (VERIFIED BY INSPECTION) —
  relevant given offscreen documents can be torn down by the browser.
- Microphone coexistence with the two other offscreen features: `micId` is settable per call
  and `call.setAudioInDevice(deviceId)` exists (VERIFIED BY INSPECTION), so device selection
  is controllable. Behavior when another feature holds the mic is **NOT DOCUMENTED**.

---

## Consolidated source list

All URLs below were actually fetched during this research.

**Telnyx developer docs**
- https://developers.telnyx.com/docs/voice/webrtc
- https://developers.telnyx.com/llms.txt
- https://developers.telnyx.com/docs/development/llms/calling-webrtc-llms-full-txt (365,688 B — complete WebRTC docs export)
- https://developers.telnyx.com/docs/development/llms/calling-voice-api-llms-full-txt (402,444 B — complete Voice API docs export)
- https://developers.telnyx.com/docs/voice/webrtc/architecture.md
- https://developers.telnyx.com/docs/voice/webrtc/fundamentals
- https://developers.telnyx.com/docs/voice/webrtc/sdk-commonalities
- https://developers.telnyx.com/docs/voice/webrtc/auth/credential-connections
- https://developers.telnyx.com/docs/voice/webrtc/auth/telephony-credentials
- https://developers.telnyx.com/docs/voice/webrtc/auth/jwt
- https://developers.telnyx.com/docs/voice/webrtc/use-cases/outbound-dialer.md
- https://developers.telnyx.com/docs/development/webrtc/js-sdk/reference/icalloptions.md
- https://developers.telnyx.com/api-reference/call-commands/dial
- https://developers.telnyx.com/api-reference/call-commands/recording-start

**Telnyx support**
- https://support.telnyx.com/en/articles/4351104-sip-connection-settings (Park Outbound Calls)

**GitHub / npm**
- https://github.com/team-telnyx/webrtc
- https://api.github.com/search/issues?q=repo:team-telnyx/webrtc+... (MV3/offscreen/SW searches)
- npm registry: `@telnyx/webrtc@2.27.10`
- https://cdn.jsdelivr.net/npm/@telnyx/webrtc , https://unpkg.com/@telnyx/webrtc

**Chrome**
- https://developer.chrome.com/docs/extensions/reference/api/offscreen

**Local inspection artifacts**
- `/tmp/telnyx-probe/telnyx-webrtc-2.27.10.tgz` (188,600 B)
- `/tmp/telnyx-probe/package/lib/bundle.js` (273,634 B, UMD)
- `/tmp/telnyx-probe/package/lib/bundle.mjs` (272,737 B, ESM)
- `/tmp/telnyx-probe/probe.js` (bare-VM classic-script load test)

---

## Explicit NOT DOCUMENTED list

Gaps where docs are silent — do not assume behavior here:

1. Any Content-Security-Policy requirement or guidance for `@telnyx/webrtc`.
2. Any mention of Chrome extensions, MV3, offscreen documents, or service workers.
3. A `browser`, `unpkg`, or `exports` field in `package.json` (absent — CDNs fall back to `main`).
4. Whether the JS SDK includes the SIP Connection username in the first INVITE's Contact
   header (required per the support article for AnchorSite selection to work as configured).
5. Propagation of `userVariables` to webhooks (present in internal typings only; absent from
   the public `ICallOptions` and from the docs reference).
6. Semantics of `telnyxCallControlId` / `telnyxSessionId` / `telnyxLegId` on outbound
   `newCall` (present in public typings, absent from the reference table).
7. Whether Telnyx server-side validates or restricts a browser-supplied `callerNumber` when
   Park Outbound Calls is **disabled**. (Moot if parking is enabled, which is the
   recommendation — but unverified, so do not run unparked.)
8. Microphone arbitration behavior when another consumer in the same offscreen document
   already holds the input device.
9. The README's stated bundler requirement is contradicted by Telnyx's own docs and by
   inspection; the UMD path is real but is **not** documented in the README.
