# Speechmatics

Live copilot WebSocket STT (not file STT).

| | |
|---|---|
| Env | `SPEECHMATICS_API_KEY`, `SPEECHMATICS_RT_LANGUAGE` |
| Logs | `speechmatics`, `copilot` |
| Docs | https://docs.speechmatics.com |

There is no first-party MCP here. Use Railway logs + official docs / Context7.
Realtime `multi` must be a real ISO code (`es`, `en`); `auto` is batch-only.
