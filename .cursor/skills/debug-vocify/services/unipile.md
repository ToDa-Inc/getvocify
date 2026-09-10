# Unipile

WhatsApp (and other channels) via Unipile instead of Meta Cloud API.

| | |
|---|---|
| Env | `UNIPILE_API_KEY`, `UNIPILE_BASE_URL`, `UNIPILE_WEBHOOK_SECRET` |
| Code | WhatsApp / Unipile webhook handlers under `backend/app` |
| Logs | `unipile`, `whatsapp` |
| API | `$UNIPILE_BASE_URL` (prod may differ from the code default) |
| Docs | https://www.unipile.com/docs (or Context7) |

```bash
.cursor/skills/debug-vocify-railway/scripts/vocify-railway.sh logs --filter "unipile"
.cursor/skills/debug-vocify/scripts/vocify-http.sh unipile GET /api/v1/accounts
```

Signature header is `unipile-signature`. If webhook secret is unset, anyone who
finds the URL can POST fake events.
