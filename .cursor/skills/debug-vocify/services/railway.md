# Railway

Hosts the FastAPI API. Frontend is Vercel. Same service, two environments.

| | |
|---|---|
| Project | `magnificent-celebration` `4c68b2b8-116f-49fd-9a2e-1db9a4297d03` |
| Service | `getvocify` `ac08092e-f71e-4536-bb84-66ec96106813` |
| production | `72257ae8-4260-4cb4-aaa6-9e5eb083f09b` — health `https://api.getvocify.com/health` |
| staging | `2b38e5b7-ebed-43f8-88e4-baab117a144c` — health `https://getvocify-staging.up.railway.app/health` |
| MCP | `user-railway` (`get_logs`, `list_deployments`, `list_variables`) — pass `environment_id` |
| CLI | `$HOME/.railway/bin/railway` — session `toni@getvocify.com` |
| Helper | `~/.agents/skills/debug-vocify-railway/scripts/vocify-railway.sh` |

Do not `railway login` unless `whoami` fails. Default env is production.
Pass `--env staging` (or MCP `environment_id`) when the user is on staging.

```bash
~/.agents/skills/debug-vocify-railway/scripts/vocify-railway.sh health
~/.agents/skills/debug-vocify-railway/scripts/vocify-railway.sh --env staging deploys
~/.agents/skills/debug-vocify-railway/scripts/vocify-railway.sh --env staging logs --filter "resend"
```

Full workflow: [debug-vocify-railway/SKILL.md](../../debug-vocify-railway/SKILL.md).
