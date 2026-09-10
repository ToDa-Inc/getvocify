# Railway

Hosts the FastAPI API (`api.getvocify.com`). Frontend is Vercel.

| | |
|---|---|
| Project | `magnificent-celebration` `4c68b2b8-116f-49fd-9a2e-1db9a4297d03` |
| Service | `getvocify` `ac08092e-f71e-4536-bb84-66ec96106813` |
| Environment | `production` `72257ae8-4260-4cb4-aaa6-9e5eb083f09b` |
| MCP | `user-railway` (`get_logs`, `list_deployments`, `list_variables`) |
| CLI | `$HOME/.railway/bin/railway` — session `toni@getvocify.com` |
| Helper | `.cursor/skills/debug-vocify-railway/scripts/vocify-railway.sh` |

Do not `railway login` unless `whoami` fails. Ignore the unused `prod` env.

```bash
.cursor/skills/debug-vocify-railway/scripts/vocify-railway.sh health
.cursor/skills/debug-vocify-railway/scripts/vocify-railway.sh deploys
.cursor/skills/debug-vocify-railway/scripts/vocify-railway.sh logs --filter "resend"
```

Full workflow: [debug-vocify-railway/SKILL.md](../../debug-vocify-railway/SKILL.md).
