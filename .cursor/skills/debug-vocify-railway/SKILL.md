---
name: debug-vocify-railway
description: >
  Pull Vocify Railway production logs, deploy status, health, and variable
  names. Use when the user asks for Railway logs, 502s, crashed deploys, or
  api.getvocify.com infra. For vendor APIs (Resend, Stripe, Twilio, Telnyx)
  use the debug-vocify skill and services/ catalog.
---

# Debug Vocify on Railway

Leaf of the Vocify debug pipeline ([debug-vocify](../debug-vocify/SKILL.md)).
Use when the user asked to debug **Railway / API infra**, or when the parent
pipeline reaches Phase 2.

Vocify production API lives on Railway. Frontend is Vercel (`app.getvocify.com`)
and is not this service. If the dashboard "does not work", check the API first.

Login is already done (`toni@getvocify.com`). **Do not run `railway login`
unless `whoami` fails.** MCP `user-railway` reuses the same CLI session.

## Context (pass these IDs every time)

| | Name | ID |
|---|---|---|
| Project | `magnificent-celebration` | `4c68b2b8-116f-49fd-9a2e-1db9a4297d03` |
| Service | `getvocify` | `ac08092e-f71e-4536-bb84-66ec96106813` |
| Environment | `production` | `72257ae8-4260-4cb4-aaa6-9e5eb083f09b` |

Ignore the extra `prod` environment (failed/unused). Live domains:
`https://api.getvocify.com` and `getvocify-production.up.railway.app`.
Root directory on Railway is `backend`. GitHub repo `ToDa-Inc/getvocify`
auto-deploys `main`.

CLI binary: `$HOME/.railway/bin/railway` (or `source "$HOME/.railway/env"`).
Helper: [scripts/vocify-railway.sh](scripts/vocify-railway.sh).

```bash
source "$HOME/.railway/env"
export RAILWAY_CALLER="skill:debug-vocify-railway"
PROJECT=4c68b2b8-116f-49fd-9a2e-1db9a4297d03
SERVICE=ac08092e-f71e-4536-bb84-66ec96106813
ENV=production
```

## Tool routing

Prefer Railway MCP when it is connected (`get_logs`, `list_deployments`,
`environment_status`, `list_variables`, `set_variables`). Fall back to the
CLI helper. Never print secret values in chat (API keys, JWT, Twilio, etc.).
Name-only is fine: `RESEND_FROM_EMAIL` is a domain/address, not a key.

## Debug workflow

1. **Health** — `curl -sS -o /dev/null -w "%{http_code}\n" --max-time 15 https://api.getvocify.com/health`
   - `200` → API is up; keep going for app-level errors.
   - `502` / timeout → service is down; jump to deploys.
2. **Deploys** — latest `production` / `getvocify` status (`SUCCESS`, `CRASHED`, `FAILED`, `BUILDING`).
3. **Logs** — last 2–6h, bounded (`--lines 150–200`). Start with errors, then a keyword (`email`, `resend`, `invite`, traceback).
4. **Map to code** — cite the file/line from the traceback. Confirm whether `origin/main` still has the bug vs local WIP.
5. **Fix** — smallest change that unblocks prod. If shipping, hotfix from `origin/main` in a worktree. **Do not push local Telnyx/WIP.** Watch the new deploy to `SUCCESS`, then re-check `/health`.

```bash
.cursor/skills/debug-vocify-railway/scripts/vocify-railway.sh health
.cursor/skills/debug-vocify-railway/scripts/vocify-railway.sh deploys
.cursor/skills/debug-vocify-railway/scripts/vocify-railway.sh errors
.cursor/skills/debug-vocify-railway/scripts/vocify-railway.sh logs --filter "email"
```

## Mutations

Ask before `variable set`, `redeploy`, `restart`, or `up`.
Redeploying a crashed commit will crash again — ship a new commit first.

## Auth recovery

```bash
source "$HOME/.railway/env"
railway whoami
```

If unauthorized, run `railway login` (opens the user's browser). Then retry.
Do not use `--browserless` on this machine.

Vendor APIs and symptom routing: [debug-vocify/SKILL.md](../debug-vocify/SKILL.md).
