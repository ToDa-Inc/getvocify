# Telnyx outbound calling — setup

Telnyx is a **cost swap** of the existing Vocify dialer, not a Spain caller-ID fix.
It is behind `CALLING_PROVIDER`. The code default stays `twilio`. Do not flip the
default in `backend/app/config.py` or `.env.example`.

Plan:
[`docs/superpowers/plans/2026-09-08-telnyx-outbound-calling.md`](../superpowers/plans/2026-09-08-telnyx-outbound-calling.md).
Design:
[`docs/superpowers/specs/2026-09-08-telnyx-outbound-calling-design.md`](../superpowers/specs/2026-09-08-telnyx-outbound-calling-design.md).

## Live gate status

**in progress (2026-09-09)** — API key authenticates (`GET /v2/balance` 200,
available credit **$14.73**). This account is on Telnyx’s **TPVE**
framework (Account Levels: Trial / Paid / Verified / Enterprise), not
legacy L1/L2. `GET /v2/verifications` still returns the leftover
`verification_level: 1` / `verified_by_telnyx: null` payload; there is
**no** public API for TPVE level. The official check is
[Account Levels](https://portal.telnyx.com/#/account/account-levels).
Dashboard **Verified** is the gate, not that legacy field.

Configured against live Mission Control (no secrets in this file):

- Outbound Voice Profile Destinations now include **ES** (plus US, CA)
- Credential Connection: parking on; Call Control App “Vocify Dialer PSTN”
  active. Both webhooks point at the local ngrok tunnel
  (`/webhooks/telnyx/voice`, API v2) — not production.
- `POST /v2/verified_numbers` for the account +34 number returned **200**
  (SMS then voice). OTP confirm succeeded on **2026-09-08** via
  `POST /v2/verified_numbers/+34…/actions/verify` **200**; Telnyx lists **1**
  verified number. Steps 7–9 are **not done**. Park-and-dial reached PSTN
  (dashboard 2026-09-08 ~19:14–20:19Z) but every attempt ended SIP **486**
  before answer — no dual WAV, memo, or answered CDR.

  Latest Vocify Dialer PSTN CDRs (`recv_refuse`, hangup 17, `connected=0`,
  `cost=0.0`, STIR **B**, `is_local_calling=false`): Telnyx **did** send
  `from` = the verified +34 (Dial command + `call.initiated`, not the
  WebRTC SIP username). The far end refused in ~1s. Same BYO CLI on Twilio
  **US1** completed; this is interconnect/attestation, not a missing Dial
  `from`. Overnight the local ngrok tunnel died — webhooks were restored
  before the next attempt. Credential Connection localization is **ES**
  (national number format, not Frankfurt origination). Dial INVITE PAI/PPI
  use `<sip:+E164@sip.telnyx.com>` (Telnyx reads the SIP user-part) and
  `sip_transport_protocol=TLS` (Identity is not sent on UDP; Dial retries
  UDP if Telnyx 422s TLS on PSTN).

  Live 2026-09-09 09:55 local (`c9dedeb0-ac23-11f1-928c-02420a1f1070`)
  actually exercised TLS + PAI: Telnyx stored Dial had
  `sip_transport_protocol=TLS`, `privacy=none`, and PAI/PPI/RPID
  `<sip:+34669701069@sip.telnyx.com>`. `POST /v2/calls` **200** (no UDP
  retry). Destination `+34648739267`. PSTN hangup `user_busy` / SIP **486**
  / `hangup_details=recv_refuse` in ~1s. CDR `connected=0`, `cost=0.0`,
  webhook `call.cost` `total_cost=0.0000` (sip-trunking + call-control
  parts both `0.0000`). STIR **B**, `is_local_calling=false`. Vocify is
  dialing correctly; the far end still refuses. The webhook now persists
  `call.cost` onto `outbound_calls.provider_state.pstn_cost`. That figure
  is **not** the step-8 answered-call cost.

  Same morning: milly `+34622915103` (10:07–10:08, twice) and Fernando
  `+34646266037` (10:11, session `08588568-ac26-11f1-852e-02420a1f0d70`)
  also SIP **486** in ~1s, Dial **200**, `from=+34669701069`, webhook
  `total_cost=0.0000`. Three different Spanish mobiles, same refuse.

Do not invent a CDR `cost` or a handset-CLI result.

## OTP confirm

Telnyx Verified Numbers send an OTP to the handset (`needsCodeSubmit: true`).
Dashboard **Settings → Caller ID** collects that code and posts it. Vocify never
generates or displays the Telnyx OTP. The extension still opens Settings; it
does not collect the code itself.

```
POST /api/v1/calls/caller-ids/confirm
```

JSON body: `{ "phoneNumber": "+34…", "code": "<otp>" }` (`code` is 4–12
characters). Requires a Vocify user session. Twilio returns 400 on this route
(Twilio still uses the keypad on the verification call). Never invent or echo a
Telnyx code.

## Migration 029

Apply `backend/migrations/029_telnyx_carrier.sql` before enabling
`CALLING_PROVIDER=telnyx`. Numbered 029 so it does not collide with
`028_companies.sql` on other branches.

This file is **additive**. It does not rename `twilio_call_sid` or
`twilio_validation_sid`. Triggers keep those columns in sync with
`carrier_call_id` / `verification_sid` so `main` Twilio keeps working.
It also adds `outbound_calls.call_disposition` if 027 was skipped
(PostgREST `PGRST204` otherwise blocks HubSpot missed-call logging).

Paste the file into the Supabase SQL editor (or):

```bash
psql "$DATABASE_URL" -f backend/migrations/029_telnyx_carrier.sql
```

Verify:

```sql
select column_name from information_schema.columns
where table_name = 'outbound_calls'
  and column_name in ('twilio_call_sid','carrier_call_id','carrier','provider_state');
select to_regclass('public.user_telephony_credentials');
```

## Env (no live secrets in this file)

Set these only on the Telnyx environment. Leave `CALLING_PROVIDER=twilio` everywhere
else.

| Variable | What it is |
|---|---|
| `CALLING_PROVIDER` | `telnyx` on this env only. Default in code is `twilio`. |
| `TELNYX_API_KEY` | Mission Control API key |
| `TELNYX_PUBLIC_KEY` | Ed25519 public key for webhook signatures |
| `TELNYX_CONNECTION_ID` | Credential Connection id (WebRTC / park) |
| `TELNYX_CALL_CONTROL_APP_ID` | Call Control Application id (`POST /v2/calls`) |
| `TELNYX_OUTBOUND_VOICE_PROFILE_ID` | Outbound Voice Profile with Spain enabled |
| `BACKEND_PUBLIC_URL` | Public origin, no trailing slash. Webhook is `{BACKEND_PUBLIC_URL}/webhooks/telnyx/voice` |

`telephony_configured()` is true for Telnyx when API key, public key,
credential connection id, and Call Control App id are all set. The
side-panel calling UI appears only when `GET /api/v1/calls/config`
returns `enabled: true`.

Park answers the WebRTC leg immediately, so the browser plays a **local**
ringback WAV (`/call-ringback.wav`, capped at 35s). Server-side
`playback_start` was removed — it looped forever and blocked hangup UX when
PSTN failed before bridge.

When PSTN hangup arrives (busy/no-answer), the webhook persists
`call_disposition` immediately and tears down the parked leg; the dashboard
polls `GET /api/v1/calls/outbound/latest-disposition` to toast **Ocupado** /
**Sin respuesta** even if Telnyx WebRTC does not forward SIP 486.

`CALLING_RECORDING_ANNOUNCEMENT_ENABLED` (default `false`) plays the AEPD
disclosure on the **PSTN / callee leg only**, then bridges. Flip per environment;
no redeploy needed.

## Mission Control + live acceptance (in order)

Do not paste API keys, connection ids, or public keys into this file.

- [x] **1. Mission Control account level.** Telnyx has two frameworks
  ([Account Verification](https://support.telnyx.com/en/articles/1130595-account-verification));
  an account is never on both. This org uses **TPVE** (Account Levels
  page), not the legacy Verifications / Level 2 tab.

  **Check (dashboard, only authority):**
  https://portal.telnyx.com/#/account/account-levels — current level
  should read **Verified** (owner screenshot / portal). Upgrade page:
  https://portal.telnyx.com/#/account/account-levels/upgrade

  **What the API can and cannot say (queried 2026-09-09 10:22):**
  - There is **no** `GET /v2/account/levels` (404).
  - `GET /v2/verifications` is the **legacy** object:
    `verification_level: 1`, `verified_by_telnyx: null`, requirements
    still list `complete_company_info` + `request_telnyx_verification`.
    Do **not** treat that as “not verified” on a TPVE account.
  - `GET /v2/balance` → credit `$14.73` (not Trial-empty).
  - `GET /v2/verified_numbers` → `+34669701069` verified
    (`verified_at` 2026-09-08T15:17:53Z). That is caller-ID, not
    account level.
  - `GET /v2/organization` → name `Vocify`, owner `dani@getvocify.com`.

  TPVE **Verified** is not STIR **A**. A is owned Telnyx numbers.
- [x] **2. Create Credential Connection.** Auth type credentials. Local test webhook
  pointed at the 8888 ngrok tunnel (`/webhooks/telnyx/voice`), API v2. Not production.
- [x] **3. PATCH connection:** `outbound.call_parking_enabled=true`, attach Outbound Voice Profile with Spain enabled.
- [x] **3b. Create a Call Control Application** with the same webhook URL.
  `POST /v2/calls` rejects a Credential Connection id (422 / `10015`:
  “Only Call Control Apps with valid webhook URL are accepted”). That is
  why parked WebRTC produced no ringtone until this id existed. Put it in
  `TELNYX_CALL_CONTROL_APP_ID`.
- [x] **4. Copy API key, credential connection id, Call Control App id, Ed25519 public key into env.** Do not flip the code default; `CALLING_PROVIDER` stays `twilio` in `config.py`.
- [x] **5. Apply migration 029** (additive). `twilio_call_sid` kept;
  `carrier_call_id` / `user_telephony_credentials` present.
  `outbound_calls.call_disposition` applied on the live DB (2026-09-08).
- [x] **6. Verify one real +34 number.** Start **200**; OTP confirm **200**
  (`verified_at` 2026-09-08T15:17:53Z). Do not invent or record the code.
- [ ] **7. Place one answered call.** Confirm: audio both ways, disclosure only on callee if flag on, dual WAV in Supabase, memo created, HubSpot engagement.
- [ ] **8. Read CDR `cost` for that call.** Write the number in this runbook (do not invent a band).
- [ ] **9. Photograph/note handset CLI.** Connected ≠ delivered.
- [ ] **10. After a week of staging, compute share of calls ≤6 s.** If >15%, talk to Telnyx about SDC before production.

### Step 6 notes (+34 verify)

Spain +34 Verified Numbers are undocumented at Telnyx. A 4xx is a user-visible
failure, not a hang. Confirm the OTP in Settings → Caller ID (same
`POST /api/v1/calls/caller-ids/confirm`). If Telnyx 4xx on start, **stop** —
do not ship BYO CLI for that country.

### Step 7 notes (answered call)

Park → server `POST /v2/calls` with `from` from `resolve_caller_id` (never the
browser) → optional speak on the PSTN leg → bridge with
`record_channels=dual`, `record_format=wav`. Do **not** set `bridge_intent` on
dial. Check:

- Two-way audio
- Disclosure on callee only when the announcement flag is on (SDR does not hear it)
- Dual-channel WAV in the private `call-recordings` bucket
- `vocify_call` memo created
- HubSpot engagement with opaque `carrier_call_id`

### Step 8 — CDR `cost` (do not invent)

Read `cost` from the Telnyx CDR for the step-7 call. Write the live figure here.
Do not copy the published rate card or invent a band.

| Field | Value |
|---|---|
| Call / CDR id | _none — step 7 not executed. Unanswered 486 samples: `7a036876-abb9` (2026-09-08T19:14Z), `c9dedeb0-ac23-11f1-928c-02420a1f1070` (2026-09-09 09:55 local, TLS+PAI live)_ |
| CDR `cost` | _not written — unanswered `0.0` / webhook `0.0000` is not the answered-call figure_ |
| Notes | Vocify Dialer PSTN rows so far: `attempted=1`, `connected=0`, `cost=0.0`, CLI `+34669701069`, `hangup_details=recv_refuse`, `sip_invite_failure_status=486`, `shaken_stir=B`, `is_local_calling=false`. 09:55 Dial `from` was the verified +34 with TLS + `<sip:+E164@sip.telnyx.com>` PAI. Same BYO-CLI model as Twilio **US1**. TPVE dashboard Verified (legacy `GET /v2/verifications` still says 1). Telnyx support 2026-09-09: Tata-ICA 486 + `fail_on_single_reject` USER_BUSY (no failover); `intl_conv_eea_orig`. The ~$0.27 spend on 2026-09-08 was OTP (`call_verification` CLI `+1816…` + SMS `$0.142`), not answered dialer minutes. |

### Step 9 — handset CLI

A connected call is not a delivered caller ID. Spanish carriers may suppress or
flag the CLI (handset shows “Número privado”) while our logs show success.

| Field | Value |
|---|---|
| Handset display | _not observed — live gate not executed_ |

### Step 10 — Short Duration (SDC)

Once more than 15% of a month’s calls are ≤6 seconds, Telnyx applies $0.01 per
call retroactively to **all** of them. SDR unanswered rings and voicemail drops
are mostly sub-6 s. After a week of staging, compute that share. If >15%, talk
to Telnyx about SDC **before** production.

## Webhook

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/webhooks/telnyx/voice` | Call Control JSON. Ed25519 over `timestamp\|raw_body` |

Headers: `telnyx-signature-ed25519`, `telnyx-timestamp`. Reject if
`|now - timestamp| > 300s`. Read the raw body once; do not re-serialize JSON.

Local tunnel (Telnyx must reach the webhook):

```bash
make backend          # uvicorn
make ngrok            # ngrok http <backend port>
make ngrok-url        # print the HTTPS base URL
```

Set `BACKEND_PUBLIC_URL` to the tunnel URL (no trailing slash). Point the
Credential Connection webhook at `{BACKEND_PUBLIC_URL}/webhooks/telnyx/voice`.

## Telnyx support diagnosis (2026-09-09)

Support diagnosed sessions `c9dedeb0` and `08588568`. This matches our CDRs.

- First-priority carrier **Tata-ICA** returns SIP **486** in <1s (screening, not a timeout).
- CLI `+34669701069` is PAI `<sip:+34669701069@sip.telnyx.com>`, STIR **B**.
- All 6 routes: `vendor_local_calling=false`, group `intl_conv_eea_orig`.
- `fail_on_single_reject` includes **USER_BUSY**, so 486 does not try
  Ibasis_Zone1, BTS-EEA, BICS-EEA-OBR, Wavecrest-Eea, DIDWW-ICA.

`fail_on_single_reject` is **not** on our public objects (Credential
Connection, Call Control App “Vocify Dialer PSTN”, OVP `Default`
`service_plan=global` / ES+US+CA). It is Telnyx routing. We cannot PATCH
it. They queued a human for: remove USER_BUSY from that fail list, local
calling for ES mobiles, PCAP on Tata-ICA, try the other five carriers.

A Telnyx-owned ES DID would be STIR **A**. That is a product change
(owned CLI, not BYO). Do not buy unless asked.

### Reply to the queued ticket

Please remove USER_BUSY / 486 from fail_on_single_reject on Call Control
app 3044633068150195974 / OVP 3044421853813671360 so Tata-ICA 486
failovers to Ibasis_Zone1, BTS-EEA, BICS-EEA-OBR, Wavecrest-Eea,
DIDWW-ICA. Also enable vendor_local_calling / domestic ES treatment for
ES-to-ES with Verified Number CLI +34669701069 (today
intl_conv_eea_orig). We are not changing Vocify Dial headers further
until that routing change is live. Sessions c9dedeb0-ac23-11f1-928c-02420a1f1070
and 08588568-ac26-11f1-852e-02420a1f0d70.

## Ask Telnyx sales in writing (still open)

1. Does the Short Duration surcharge apply to outbound SDR dialling where short
   calls are unanswered rings and voicemail, not intentional short-duration
   traffic?
2. Which origination band does a `+34` caller ID fall into — in-country or EEA?
   Worth ~33× on landline, and not published.
3. ES-to-ES Call Control Dial with a **Verified Number** CLI (`from=+34…`, no
   Telnyx DID): CDRs show `is_local_calling=false`, STIR **B**,
   `hangup_details=recv_refuse`, SIP **486** in ~1s (`connected=0`). Twilio US1
   with the same BYO CLI completed. What route/attestation does L2 or an
   owned ES DID change? Session example: `85985fa8-abc2-11f1-8f5c-02420a1f0d70`.

### Paste into Mission Control → Support

Outbound Call Control Dial, no Telnyx DID. CLI is Verified Number
`+34669701069`. Destinations `+34648739267`, `+34622915103`,
`+34646266037`. All SIP 486 in ~1s, hangup_details=recv_refuse,
connected=0, STIR B, is_local_calling=false. Sessions:
`c9dedeb0-ac23-11f1-928c-02420a1f1070` (09:55 TLS+PAI),
`08588568-ac26-11f1-852e-02420a1f0d70` (Fernando), milly 10:07–10:08.
Same CLI on Twilio US1 connects. What do you need so ES mobiles actually
ring?

## Compliance (unchanged from Twilio)

- **AEPD Circular 1/2023** — tell the person at the start that the call is
  recorded and why. Disclosure is callee-only when the flag is on.
- **Orden TDF/149/2025** and the 2026-10-17 **400** range still apply. Switching
  carriers does not fix Spanish CLI. This runbook is not a Spain CLI remediation.
