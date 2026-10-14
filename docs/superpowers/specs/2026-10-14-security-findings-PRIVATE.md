# Security findings — PRIVATE, do not commit while open

**Date**: 2026-10-14
**Why private**: `ToDa-Inc/getvocify` is a public repository. This file is excluded from git on this machine via `.git/info/exclude`. Move the content into a committed doc (or delete this file) only after every item is fixed.
**Found during**: the backend reliability study, see [backend reliability plan](2026-10-14-backend-reliability-plan.md).
**Code read at**: `origin/main` 4c874309.

Each item says how it was confirmed.

---

## 1. TLS certificate verification disabled process-wide (API and live service)

- **Where**: `backend/app/api/transcription.py:31-41`. On import it replaces `ssl.create_default_context` with a version that sets `check_hostname = False` and `verify_mode = CERT_NONE`, and sets `ssl._create_default_https_context = ssl._create_unverified_context`.
- **Reach**: the API imports it through `backend/app/api/router.py:33, 91`; the live service imports it directly.
- **Verified by running it**: an `httpx.Client()` created before importing the router has `verify_mode=2`, `check_hostname=True`; one created after has `verify_mode=0`, `check_hostname=False`. httpx 0.28 builds its SSL context through `ssl.create_default_context` (`httpx/_config.py:35-54`).
- **Impact**: every outbound HTTPS call (Supabase with the service-role key, Twilio, Stripe, HubSpot tokens, LLM providers, STT providers, Resend) accepts any certificate. Anyone positioned to intercept traffic can impersonate those services and read the credentials sent to them.
- **Fix**: delete the monkeypatch. If a provider websocket genuinely needs a CA bundle, pass `ssl.create_default_context(cafile=certifi.where())` to that one connection (the file already sets `WEBSOCKETS_CA_BUNDLE`). Add a test that asserts a fresh `httpx.Client()` has `verify_mode == ssl.CERT_REQUIRED` after importing `app.main` and `app.live_main`.

## 2. Unauthenticated live-transcription websocket on the API

- **Where**: `backend/app/api/transcription.py`, `@router.websocket("/live")` → `live_transcription`. It accepts and calls `serve_live(websocket, websocket.query_params.get("user_id"), service="api")`. Mounted on the API via `api/router.py:91`.
- **Verified by reading the code.** The `live` service's copy (`live_router`, same file) requires a signed ticket as the first message.
- **Users of the unauthenticated route** (from code reading): web recorder `src/features/recording/hooks/useRealtimeTranscription.ts:187-191`, Chrome extension `chrome-extension/background.js:552, 621-628`, `offscreen.js:30`.
- **Impact**: anyone can open paid real-time transcription sessions attributed to any user ID; session start also loads that user's glossary, call languages and voice enrollment.
- **Fix**: require the same ticket auth on the API route (clients already can call `POST /api/v1/transcription/ticket`), then move those clients to the `live` service and remove the API route.

## 3. Unauthenticated Speechmatics webhook

- **Where**: `backend/app/api/webhooks.py:416`, `/webhooks/speechmatics`. Matches the memo by `memo_id` from the query string; no signature or token.
- **Verified by reading the code**: on `status=error` it updates that memo to failed; otherwise it can overwrite the transcript and start extraction.
- **From code reading**: nothing in the repo registers a Speechmatics `notification_url` (`services/speechmatics_batch.py` never called with it), so the route is dead.
- **Impact**: anyone with a memo ID can mark it failed or replace its transcript.
- **Fix**: delete the route. If ever revived, require a per-job secret in the notification URL.

## 4. Unipile (WhatsApp) webhook accepts unsigned requests in production

- **Where**: `backend/app/api/webhooks.py:180-199`. If `UNIPILE_WEBHOOK_SECRET` is empty it logs "accepted without UNIPILE_WEBHOOK_SECRET (dev only)" and processes the request.
- **Verified**: production Railway (`getvocify`, production) has `UNIPILE_API_KEY` set and **no `UNIPILE_WEBHOOK_SECRET`** (checked 2026-10-14, names only).
- **Impact**: anyone can inject WhatsApp messages, which run the full pipeline (STT, LLM extraction, memo creation, replies) at Vocify's cost and into a user's CRM flow.
- **Fix**: set `UNIPILE_WEBHOOK_SECRET` on Railway from Unipile's dashboard (Dani), then make the code fail closed in production when the secret is missing (as the Twilio and Telnyx paths do).

## Lower severity (from code reading, not re-verified)

- WhatsApp (Meta) and HubSpot webhooks also fail open when their secret is unset (`webhooks.py:126-130`, `:376-380`); both secrets **are set in production (verified)**, so not exploitable today, but they should fail closed in production.
- Recall webhook: `RECALL_WEBHOOK_SECRET` **not set (verified)**; with only `RECALL_API_KEY` the handler accepts unsigned requests but re-reads the data from Recall's API (`webhooks.py:1618-1628`), which limits forged content. Set the secret anyway.
- HubSpot/Salesforce/Pipedrive OAuth `decode_state` does not check which provider minted the state (`services/hubspot/oauth.py:102-116`, `salesforce/oauth.py:51-58`, `pipedrive/oauth.py:55-62`); HubSpot authorize lacks `require_crm_write_access` (`api/crm.py:755-794`); the HubSpot callback puts `error` unencoded into the redirect (`crm.py:814`).
- `/public/hubspot/recordings/{call_sid}` authorizes by the CallSid in the path (`api/hubspot_recordings.py:47-58`).
- A GitHub personal access token is embedded in the git remote URL of `~/signalcore/signalcore-frontend` (another repo, seen 2026-10-14). Revoke it and switch the remote to SSH.
