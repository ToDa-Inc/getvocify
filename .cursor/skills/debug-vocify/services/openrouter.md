# OpenRouter

LLM routing for extraction, sanitize, copilot (`LLM_PROVIDER=openrouter`).

| | |
|---|---|
| Env | `OPENROUTER_API_KEY`, `EXTRACTION_MODEL`, `COPILOT_MODEL`, `TRANSCRIPT_SANITIZE_MODEL` |
| Logs | `openrouter`, `llm` |
| API | `https://openrouter.ai/api/v1` |
| Docs MCP | `user-openrouter.ai` (re-auth if discovery failed) |
| Docs | https://openrouter.ai/docs |

```bash
.cursor/skills/debug-vocify-railway/scripts/vocify-railway.sh logs --filter "openrouter"
.cursor/skills/debug-vocify/scripts/vocify-http.sh openrouter GET /api/v1/models
```

Do not paste the key. `/health` may echo a truncated prefix — omit it in chat.
