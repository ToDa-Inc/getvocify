# Twilio outbound calling — setup

## Database migration (required)

Apply both outbound-calling migrations before enabling calling:

```bash
psql "$DATABASE_URL" -f backend/migrations/025_outbound_calling.sql
psql "$DATABASE_URL" -f backend/migrations/026_dialer.sql
```

Verify:

```sql
\d user_caller_ids
\d outbound_calls
SELECT id, public FROM storage.buckets WHERE id = 'call-recordings';
-- public must be false
```

Confirm `memos.source` includes `vocify_call`:

```sql
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname = 'memos_source_check';
```

## Twilio console, once per environment

1. **API Key** (Account → API keys & tokens → Create standard key).
   → `TWILIO_API_KEY_SID`, `TWILIO_API_KEY_SECRET`
2. **TwiML App** (Voice → TwiML → TwiML Apps → Create).
   Voice Request URL: `https://<BACKEND_PUBLIC_URL>/webhooks/twilio/voice`, method `POST`.
   → `TWILIO_TWIML_APP_SID`
3. Copy Account SID and Auth Token → `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`.
   The Auth Token is used only to validate webhook signatures.
4. **Region.** This account lives in **Ireland (IE1)**. Set `TWILIO_EDGE=dublin` and
   `TWILIO_REGION=ie1`. Requests to `api.twilio.com` (US1) return 401 even with a valid
   Auth Token. The Python SDK needs **both** `edge` and `region`; region alone still
   routes to US1. Voice Access Tokens must set `region=ie1` so the browser SDK connects
   to Dublin.
5. **Do not buy a phone number.** Caller ID comes from each user's verified personal or office number, so there is no number rental and no regulatory bundle.

### Webhook endpoints

The TwiML App Voice Request URL is `/webhooks/twilio/voice`. The backend also exposes:

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/webhooks/twilio/voice` | Outbound dial TwiML (TwiML App target) |
| `POST` | `/webhooks/twilio/whisper` | Recording disclosure played to the called party |
| `POST` | `/webhooks/twilio/caller-id-status` | Caller-ID verification outcome (correlates via `CallSid`, not `To`) |
| `POST` | `/webhooks/twilio/recording` | Recording-ready callback |

Signature validation rebuilds the signed URL from `BACKEND_PUBLIC_URL` + request path. The TwiML App Voice URL and `BACKEND_PUBLIC_URL` must share the same public origin or every webhook returns 403.

## HubSpot, once per app

### Recording endpoint registration (outstanding)

Task 6 Step 7 was **not** run at implementation time. Register the recording provider before HubSpot can play call recordings.

**`HUBSPOT_APP_ID`** is a real app setting (in `.env` / Settings). Set it to the numeric app ID from HubSpot developer account → your app → Overview.

**`HUBSPOT_DEV_TOKEN`** is a one-off shell export for this registration command only — a developer-scoped HubSpot private-app or test-account token with permission to write calling-extension recording settings. It is **not** a runtime secret, **not** in `.env.example`, and **not** loaded by Settings. Export it in the shell, run the command once, then discard it.

Where to get it: HubSpot developer account → your app's test account, or create a private app token that can `POST /crm/extensions/calling/2026-03/{appId}/settings/recording`.

```bash
export HUBSPOT_DEV_TOKEN='pat-...'   # one-off; not in .env.example
# HUBSPOT_APP_ID must already be set in .env or exported here

cd backend && .venv/bin/python -c "
import asyncio, os
from app.services.hubspot.client import HubSpotClient
from app.services.hubspot.calling_settings import (
    recording_endpoint_url, register_recording_endpoint,
)
from app.config import settings

async def main():
    client = HubSpotClient(os.environ['HUBSPOT_DEV_TOKEN'])
    url = recording_endpoint_url(settings.BACKEND_PUBLIC_URL)
    print(url)
    print(await register_recording_endpoint(client, settings.HUBSPOT_APP_ID, url))

asyncio.run(main())
"
```

The printed URL must end in `/public/hubspot/recordings/%s`. Confirm after registration:

```
GET /crm/extensions/calling/2026-03/{appId}/settings/recording
```

Without `HUBSPOT_APP_ID`, `build_call_properties` raises on an empty `app_id` and HubSpot call logging is skipped (caught as a warning).

### Hub ID and recording access

`hubspot_hub_id` on `outbound_calls` is populated at log time from `crm_connections.metadata.portal_id` — never from the browser. The public recording endpoint fail-closes with 403 when:

- `hubspot_hub_id` is empty
- `externalAccountId` is missing on the request
- `externalAccountId` does not match `hubspot_hub_id`

## Extension UI

The side-panel calling UI appears only when `GET /api/v1/calls/config` returns `enabled: true`. That requires `telephony_configured()` — all of `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_API_KEY_SID`, `TWILIO_API_KEY_SECRET`, and `TWILIO_TWIML_APP_SID` must be set. It is not gated by an org feature flag. The same endpoint also includes `hubspotLogging` (true when `HUBSPOT_APP_ID` is set). Calls still place when it is false; HubSpot engagements will not be created.

### Caller ID verification

Twilio's verification call is **English-only from a US number**. Number management lives on **Settings → Caller ID** (`/dashboard/settings`). The side panel only dials; "Añadir número" opens that page. If the user misses the call, they retry from Settings; a previously verified number is not downgraded by a retry.

`CALLING_RECORDING_ANNOUNCEMENT_ENABLED` (default `false`) plays the AEPD disclosure to the prospect before bridging. The `/webhooks/twilio/whisper` route stays mounted so flipping the flag needs no redeploy.

## Live call checks (after first real call)

Record these against a real Twilio call before relying on post-call polling:

- `activeCall.parameters.CallSid` should equal `outbound_calls.twilio_call_sid`. If it does not, the extension must poll `GET /calls/history?limit=1` instead of `GET /calls/{sid}`.
- Mute mutes the far end, not just the UI.
- DTMF reaches an IVR.
- Two back-to-back calls reuse the Device without "Device destroyed".
- With the announcement flag off, the WAV is still dual-channel.

## Local development

Twilio must reach the webhooks, so tunnel the backend and point the TwiML App at the tunnel:

```bash
make backend          # uvicorn on port 8000
make ngrok            # ngrok http 8000
make ngrok-url        # print the HTTPS base URL
```

Set `BACKEND_PUBLIC_URL` to the tunnel URL (no trailing slash). The signature check rebuilds the signed URL from it, so a mismatch produces 403.

`TWILIO_SKIP_SIG_CHECK=1` bypasses signature validation **only when `ENVIRONMENT` is not `production`**. This repo's local `.env` often sets `ENVIRONMENT=production`, which makes the skip hatch inert. For local webhook testing, either:

- set `ENVIRONMENT=development`, or
- send real Twilio-signed requests (tunnel + TwiML App pointed at the tunnel).

Do not rely on `TWILIO_SKIP_SIG_CHECK` when `ENVIRONMENT=production`.

## Cost per connected minute (Spain, Spanish caller ID)

| Component | $/min |
|---|---|
| PSTN to Spanish mobile, EEA origination | 0.0486 |
| PSTN to Spanish landline | 0.0178 |
| Browser leg (billed separately from voice) | 0.0040 |
| Recording | 0.0025 |
| Storage | 0.0005 /min/month (first 10,000 min free) |
| Deepgram Nova-3 batch | 0.0043 |

Roughly $0.059/min to mobile and $0.029/min to landline. Twilio bills only answered calls but **rounds each up to the next minute**, so short calls are disproportionately expensive at SDR volumes.

A Spanish caller ID is what earns the EEA origination rate: the same call with non-EEA origination is $0.1800/min, 3.7x more. Confirm the live rate with the Pricing API for a real number before committing to a price:

```
GET https://pricing.twilio.com/v2/Voice/Numbers/{destination}?OriginationNumber={spanish_cli}
```

Two figures were not verifiable from public docs and should be confirmed with Twilio: whether dual-channel recording bills at 1x or 2x per minute, and the maximum number of Verified Caller IDs per (sub)account.

## Compliance

- **AEPD Circular 1/2023** requires telling the person at the start of the call that it is being recorded and why. `TWILIO_RECORDING_ANNOUNCEMENT` plays to the called party via `<Number url>` and, because `record-from-answer-dual` starts at answer, the disclosure is inside the recording — which is the proof.
- Recordings must not be reused for purposes beyond the stated one without a separate legal basis. The `call-recordings` bucket is private; agree a retention period and add a deletion job before rolling out broadly.
- **Orden TDF/149/2025** restricts mobile numbers as caller ID for commercial calls. Steer users toward a geographic office number, not a personal mobile.
- Twilio's caller ID verification call is English-only from a US number. The side panel must show the code and warn about this, or activation will suffer.
