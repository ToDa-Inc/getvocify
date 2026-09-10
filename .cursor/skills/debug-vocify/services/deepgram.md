# Deepgram

File STT for HubSpot recordings, uploads, WhatsApp audio (`STT_PROVIDER=deepgram`).

| | |
|---|---|
| Env | `DEEPGRAM_API_KEY`, `STT_PROVIDER` |
| Logs | `deepgram`, `stt` |
| API | `https://api.deepgram.com` |
| Docs MCP | `user-developers.deepgram.com` → `searchDocs` |
| Docs | https://developers.deepgram.com |

```bash
.cursor/skills/debug-vocify-railway/scripts/vocify-railway.sh logs --filter "deepgram"
.cursor/skills/debug-vocify/scripts/vocify-http.sh deepgram GET /v1/projects
```
