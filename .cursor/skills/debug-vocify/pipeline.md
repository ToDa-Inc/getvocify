# Vocify debug playbook

Hugo patterns adapted to Cursor. Parent skill: [SKILL.md](SKILL.md).

## Layers (do not mix)

| Layer | What it is | How to inspect |
|---|---|---|
| Vercel | `app.getvocify.com` HTML/JS | [vercel.md](services/vercel.md) |
| Railway | FastAPI `api.getvocify.com` | [railway.md](services/railway.md) |
| Supabase | Auth + Postgres | [supabase.md](services/supabase.md) |
| Vendor | Resend, Stripe, Twilio, … | matching card + `vocify-http.sh` |

A 200 dashboard page with failed XHR is Railway (or the vendor), not Vercel.

## Phase 0 — Identity

Before tools, lock:

- **env**: production (default) vs local (`localhost:8080` / `:8888`)
- **when**: UTC window (or "last 2h")
- **who**: user email and/or `company_id` if known
- **what**: exact user-visible failure

Vocify has no `business_id`. Scope with `company_id`, user email, memo id,
call id, or invite email.

If they named a customer, resolve via master key ([admin.md](services/admin.md)):

```bash
.cursor/skills/debug-vocify/scripts/vocify-admin.sh accounts --search email@x.com
.cursor/skills/debug-vocify/scripts/vocify-admin.sh companies --search Acme
.cursor/skills/debug-vocify/scripts/vocify-admin.sh account <user_id>
.cursor/skills/debug-vocify/scripts/vocify-admin.sh company <company_id>
```

`MASTER_KEY` is already in `backend/.env` / Railway. The helper sends
`X-Master-Key` and never prints the key. Impersonate (`as-user`) only after
the user asks — it mints a real session and is audited.

## Phase 1 — Health

`GET https://api.getvocify.com/health`

- `200` → API up; keep going for app/vendor errors
- `502` / timeout → Phase 2 deploys; skip vendors until the API boots

## Phase 2 — Railway

IDs are on the railway card. Prefer MCP `get_logs` / `list_deployments`.
Fallback: `vocify-railway.sh`.

Always bound logs (`--lines 150–200`, `--filter`, last 2–6h). Start `@level:error`,
then the card's keyword.

Deploy statuses: `SUCCESS`, `CRASHED`, `FAILED`, `BUILDING`, `DEPLOYING`.
A crashed commit will crash again if redeployed.

## Phase 3 — Vendor

1. Open `services/<vendor>.md` — do not invent hosts or paths.
2. Confirm current docs (that card's MCP, Context7, or official URL).
3. GET via `vocify-http.sh` or vendor MCP. Non-GET needs `--write` and user OK.
4. Never print secrets. `RESEND_FROM_EMAIL` (an address) is safe.

Helper reads `backend/.env` (or repo `.env`) at runtime:

```bash
.cursor/skills/debug-vocify/scripts/vocify-http.sh <vendor> GET <path>
```

Vendors: `resend`, `stripe`, `twilio`, `telnyx`, `unipile`, `deepgram`, `openrouter`.

## Phase 4 — Code

Only after Phase 2/3 evidence. Check whether `origin/main` still has the bug
vs dirty local WIP. `codebase_search` / grep for the traceback file.

## Phase 5 — Fix

Smallest production change. Hotfix from `origin/main` in a worktree.
Watch Railway to `SUCCESS`, then re-hit `/health` and the original symptom.
Do not claim fixed without that verify step.

## Subagent prompts

Give each subagent everything; they have no parent chat.

```
Vocify-only debug. Follow .cursor/skills/debug-vocify/pipeline.md evidence rules.
Do not fix unless asked. Return: Status, Evidence quotes (redact secrets),
what you did not check.

Env: production
Window: <UTC>
Symptom: <one line>
Card: .cursor/skills/debug-vocify/services/<name>.md
Commands allowed: vocify-railway.sh, vocify-http.sh GET, named MCP tools
```

Parent merges quotes and decides the next phase. Conflicting stories → say so
and re-run the disputed tool.

## Common Vocify mistakes

- Treating Vercel 200 as "API is fine"
- Redeploying `CRASHED` without a new commit
- `RESEND_FROM_EMAIL=mail.getvocify.com` (domain, not address) → Resend 422
- Assuming Telnyx is live when production `CALLING_PROVIDER=twilio`
- Pushing local Telnyx/WIP as a hotfix
- Guessing Stripe/Twilio/Unipile paths instead of reading the card/docs
