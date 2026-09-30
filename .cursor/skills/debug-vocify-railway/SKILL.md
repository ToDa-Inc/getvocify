---
name: debug-vocify-railway
description: >
  Pull Vocify Railway production or staging logs, deploy status, health, and
  variable names. Use when the user asks for Railway logs, 502s, crashed
  deploys, api.getvocify.com, getvocify-staging, or staging.getvocify.com
  infra. For vendor APIs (Resend, Stripe, Twilio, Telnyx) use the
  debug-vocify skill and services/ catalog.
---

# Debug Vocify on Railway

Leaf of the Vocify debug pipeline ([debug-vocify](../debug-vocify/SKILL.md)).
Use when the user asked to debug **Railway / API infra**, or when the parent
pipeline reaches Phase 2.

Vocify API lives on Railway (production + staging). Frontend is Vercel
(`app.getvocify.com` / `staging.getvocify.com`) and is not this service.
If the dashboard "does not work", check the matching API first.

**Pick the env in Phase 0.** Default **production**. Use **staging** when
they say staging, `staging.getvocify.com`, `getvocify-staging`, or the
git branch `staging`. Do not mix logs: a prod 502 is not a staging deploy.

Login is already done (`toni@getvocify.com`). **Do not run `railway login`
unless `whoami` fails.** MCP `user-railway` reuses the same CLI session.

## Context (pass these IDs every time)

| | Name | ID |
|---|---|---|
| Project | `magnificent-celebration` | `4c68b2b8-116f-49fd-9a2e-1db9a4297d03` |
| Service | `getvocify` | `ac08092e-f71e-4536-bb84-66ec96106813` |
| Environment | `production` (default) | `72257ae8-4260-4cb4-aaa6-9e5eb083f09b` |
| Environment | `staging` | `2b38e5b7-ebed-43f8-88e4-baab117a144c` |

Same service, two environments. MCP calls must include `environment_id`
for the env you picked. Live domains:

| Env | Health | Hosts |
|---|---|---|
| production | `https://api.getvocify.com/health` | `api.getvocify.com`, `getvocify-production.up.railway.app` |
| staging | `https://getvocify-staging.up.railway.app/health` | `getvocify-staging.up.railway.app` (frontend: `staging.getvocify.com`) |

Root directory on Railway is `backend`. GitHub `ToDa-Inc/getvocify`:
`main` → production, `staging` → staging.

CLI binary: `$HOME/.railway/bin/railway` (or `source "$HOME/.railway/env"`).
Helper: [scripts/vocify-railway.sh](scripts/vocify-railway.sh).

```bash
source "$HOME/.railway/env"
export RAILWAY_CALLER="skill:debug-vocify-railway"
PROJECT=4c68b2b8-116f-49fd-9a2e-1db9a4297d03
SERVICE=ac08092e-f71e-4536-bb84-66ec96106813
# production | staging
ENV=production
```

## Tool routing

Prefer Railway MCP when it is connected (`get_logs`, `list_deployments`,
`environment_status`, `list_variables`, `set_variables`). Fall back to the
CLI helper. Never print secret values in chat (API keys, JWT, Twilio, etc.).
Name-only is fine: `RESEND_FROM_EMAIL` is a domain/address, not a key.

## Debug workflow

1. **Health** — production `https://api.getvocify.com/health` or staging
   `https://getvocify-staging.up.railway.app/health`.
   - `200` → API is up; keep going for app-level errors.
   - `502` / timeout → service is down; jump to deploys.
2. **Deploys** — latest deploy on **that env** (`SUCCESS`, `CRASHED`,
   `FAILED`, `BUILDING`). Staging tracks branch `staging`.
3. **Logs** — last 2–6h, bounded (`--lines 150–200`), same env. Start with
   errors, then a keyword (`email`, `resend`, `invite`, traceback).
4. **Map to code** — cite the file/line from the traceback. Confirm
   `origin/main` (prod) or `origin/staging` vs local WIP.
5. **Fix** — smallest change that unblocks that env. Prod hotfix from
   `origin/main` in a worktree. Staging: branch `staging`. **Do not push
   local Telnyx/WIP to production.** Watch the new deploy to `SUCCESS`,
   then re-check that env's `/health`.

```bash
# production (default)
~/.agents/skills/debug-vocify-railway/scripts/vocify-railway.sh health
~/.agents/skills/debug-vocify-railway/scripts/vocify-railway.sh deploys
~/.agents/skills/debug-vocify-railway/scripts/vocify-railway.sh errors

# staging
~/.agents/skills/debug-vocify-railway/scripts/vocify-railway.sh --env staging health
~/.agents/skills/debug-vocify-railway/scripts/vocify-railway.sh --env staging deploys
~/.agents/skills/debug-vocify-railway/scripts/vocify-railway.sh --env staging errors
~/.agents/skills/debug-vocify-railway/scripts/vocify-railway.sh --env staging logs --filter "email"
```

From the getvocify repo root: `.cursor/skills/debug-vocify-railway/scripts/vocify-railway.sh`.

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
