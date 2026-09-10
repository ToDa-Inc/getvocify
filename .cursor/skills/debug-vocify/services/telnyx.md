# Telnyx

Optional outbound path when `CALLING_PROVIDER=telnyx`. Local WIP may not be
on production `main`.

| | |
|---|---|
| Env | `TELNYX_API_KEY`, `TELNYX_PUBLIC_KEY`, `TELNYX_CONNECTION_ID`, `TELNYX_CALL_CONTROL_APP_ID`, `TELNYX_OUTBOUND_VOICE_PROFILE_ID` |
| Code | `backend/app/services/telephony/telnyx_client.py`, webhooks in `backend/app/api/webhooks.py` |
| Logs | `telnyx` |
| API | `https://api.telnyx.com/v2` |
| Docs | https://developers.telnyx.com |

```bash
.cursor/skills/debug-vocify-railway/scripts/vocify-railway.sh logs --filter "telnyx"
.cursor/skills/debug-vocify/scripts/vocify-http.sh telnyx GET /v2/balance
```

Confirm production `CALLING_PROVIDER` before assuming Telnyx is live.
