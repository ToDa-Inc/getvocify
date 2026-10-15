# Calls (dialer: dashboard dock and desktop island)

Outbound calls through Vocify (Twilio in production). The same call engine
(`src/features/calling/callEngine.ts`) runs in the dashboard dock and in the
desktop app's island, so one call leaves the same trail in both.

## One call, three places that must agree

| Where | Key |
|---|---|
| Twilio | parent call `CA…` (direction `inbound`, from the SDK) and its child `outbound-dial` (to the prospect) |
| DB `outbound_calls` | `carrier_call_id` = the parent `CA…`; `call_disposition`, `status`, `answered_at`, `memo_id` |
| HTTP log (`vocify-railway.sh logs --http`) | path `/api/v1/calls/<CA…>` |

`outbound_calls.memo_id` → `memos.id` (memo URL `/dashboard/memos/<id>`).
Dispositions: `connected`, `voicemail`, `no_answer`, `busy`, `canceled`, `failed`.

## Signature of a healthy call in `--http` logs

1. `POST /api/v1/calls/token` (the dialer asks for a Twilio token)
2. `POST /webhooks/twilio/voice` from `TwilioProxy` (Twilio reached us; the row is inserted)
3. `GET /api/v1/calls/<CA…>` about every 2 s while it rings (the dialer follows its call)
4. `POST /webhooks/twilio/dial-status` when the prospect leg ends
5. answered only: `POST /webhooks/twilio/recording`, then the memo appears

Missing step 3 after step 2 means the dialer stopped following its own call
(it thinks the call ended). That was the 2026-10-15 bug (commit `d4918b79`):
a call placed under 3 minutes after an unanswered one was closed on screen
by the previous call's `no_answer` and kept ringing unseen.

## Read-only recipe

```bash
# Twilio: the window's calls, small fields only (default output is capped at 8000 chars)
~/.agents/skills/debug-vocify/scripts/vocify-http.sh twilio GET \
  "/Calls.json?PageSize=50&StartTime%3E=2026-10-15T14:40:00Z&StartTime%3C=2026-10-15T14:52:00Z" \
  --pick sid,parent_call_sid,direction,status,duration,date_created

# The request trail of one minute (UTC; 200 lines unless --lines)
~/.agents/skills/debug-vocify-railway/scripts/vocify-railway.sh logs --http \
  --since 2026-10-15T14:48:00Z --until 2026-10-15T14:49:00Z
```

DB side: see the read-only recipe in [supabase.md](supabase.md) (`outbound_calls`,
filter by `user_id` and `created_at`).

## What cannot be seen from here

The dialer's own steps (`call:dial`, `call:ringing`, `call:accept`, `call:call-error`…)
are written to the desktop app's log on the rep's Mac, behind its test switch.
Ask for that log when the HTTP trail and Twilio agree but the screen did not.
Without it, a conclusion about what the screen showed is an inference.
