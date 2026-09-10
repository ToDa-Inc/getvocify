# Twilio

Default outbound calling (`CALLING_PROVIDER=twilio`). Caller ID is the user's
verified number.

| | |
|---|---|
| Env | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_API_KEY_SID`, `TWILIO_API_KEY_SECRET`, `TWILIO_TWIML_APP_SID`, `TWILIO_EDGE`, `TWILIO_REGION` |
| Code | `backend/app/services/telephony/` |
| Logs | `twilio`, `dial`, `outbound` |
| API | `https://api.twilio.com/2010-04-01/Accounts/{SID}` (Ireland accounts may use `api.{edge}.{region}.twilio.com`) |
| Docs | https://www.twilio.com/docs |

```bash
.cursor/skills/debug-vocify-railway/scripts/vocify-railway.sh logs --filter "twilio"
.cursor/skills/debug-vocify/scripts/vocify-http.sh twilio GET /Calls.json?PageSize=5
```

Helper uses basic auth SID:TOKEN. Ask before placing a live call.
