# Telnyx outbound calling — setup

Telnyx is a **cost swap** of the existing Vocify dialer, not a Spain caller-ID fix.
It is behind `CALLING_PROVIDER`. The code default stays `twilio`. Do not flip the
default in `backend/app/config.py` or `.env.example`.

Plan:
[`docs/superpowers/plans/2026-09-08-telnyx-outbound-calling.md`](../superpowers/plans/2026-09-08-telnyx-outbound-calling.md).
Design:
[`docs/superpowers/specs/2026-09-08-telnyx-outbound-calling-design.md`](../superpowers/specs/2026-09-08-telnyx-outbound-calling-design.md).

## Live gate status

**not executed** — needs Verified (L2) account. This environment has no Telnyx L2
credentials. Steps 6–9 below are **not done**. Do not treat this document as a
passed acceptance gate. Do not invent a CDR `cost` or a handset-CLI result.

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

```bash
psql "$DATABASE_URL" -f backend/migrations/029_telnyx_carrier.sql
```

Verify:

```sql
\d outbound_calls
\d user_caller_ids
\d user_telephony_credentials
-- outbound_calls.carrier, carrier_call_id, provider_state
-- user_caller_ids.verification_sid (not twilio_validation_sid)
```

## Env (no live secrets in this file)

Set these only on the Telnyx environment. Leave `CALLING_PROVIDER=twilio` everywhere
else.

| Variable | What it is |
|---|---|
| `CALLING_PROVIDER` | `telnyx` on this env only. Default in code is `twilio`. |
| `TELNYX_API_KEY` | Mission Control API key |
| `TELNYX_PUBLIC_KEY` | Ed25519 public key for webhook signatures |
| `TELNYX_CONNECTION_ID` | Credential Connection id |
| `TELNYX_OUTBOUND_VOICE_PROFILE_ID` | Outbound Voice Profile with Spain enabled |
| `BACKEND_PUBLIC_URL` | Public origin, no trailing slash. Webhook is `{BACKEND_PUBLIC_URL}/webhooks/telnyx/voice` |

`telephony_configured()` is true for Telnyx when API key, public key, and
connection id are all set. The side-panel calling UI appears only when
`GET /api/v1/calls/config` returns `enabled: true`.

`CALLING_RECORDING_ANNOUNCEMENT_ENABLED` (default `false`) plays the AEPD
disclosure on the **PSTN / callee leg only**, then bridges. Flip per environment;
no redeploy needed.

## Mission Control + live acceptance (in order)

Do not paste API keys, connection ids, or public keys into this file.

- [ ] **1. Upgrade Mission Control to Verified (L2).** Paid limits cannot pilot a team.
- [ ] **2. Create Credential Connection.** Auth type credentials. Webhook `https://<BACKEND_PUBLIC_URL>/webhooks/telnyx/voice`, API v2.
- [ ] **3. PATCH connection:** `outbound.call_parking_enabled=true`, attach Outbound Voice Profile with Spain enabled.
- [ ] **4. Copy API key, connection id, Ed25519 public key into env.** `CALLING_PROVIDER=telnyx`.
- [ ] **5. Apply migration 029.**
- [ ] **6. Verify one real +34 number** (`POST /v2/verified_numbers`). If it 4xx, stop — do not ship BYO for that country.
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
| Call / CDR id | _not measured — live gate not executed_ |
| CDR `cost` | _not measured — live gate not executed_ |

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

## Ask Telnyx sales in writing (still open)

1. Does the Short Duration surcharge apply to outbound SDR dialling where short
   calls are unanswered rings and voicemail, not intentional short-duration
   traffic?
2. Which origination band does a `+34` caller ID fall into — in-country or EEA?
   Worth ~33× on landline, and not published.

## Compliance (unchanged from Twilio)

- **AEPD Circular 1/2023** — tell the person at the start that the call is
  recorded and why. Disclosure is callee-only when the flag is on.
- **Orden TDF/149/2025** and the 2026-10-17 **400** range still apply. Switching
  carriers does not fix Spanish CLI. This runbook is not a Spain CLI remediation.
