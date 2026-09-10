---
name: debug-vocify
description: >
  Vocify-only production debug pipeline (Hugo-style). Use only when the user
  asks to debug Vocify — production, logs, 502, emails, invites, billing,
  calls, WhatsApp, STT, CRM, or a named vendor (Resend, Stripe, Twilio,
  Telnyx, Unipile, Deepgram, OpenRouter, Railway). Do not use for routine
  feature work, refactors, or other products.
---

# Debug Vocify

Vocify-specific ops pipeline. **Run only when the user requests a debug.**
Not SignalCore, not other repos, not everyday coding.

Railway CLI/MCP login is already stored (`toni@getvocify.com`). Do not ask
them to log in again unless `railway whoami` fails.

## Pipeline (do not skip)

Copy and tick:

```
Debug Vocify
- [ ] 0 Identity — company/user/time/env; admin search if they named a customer
- [ ] 1 Health — api.getvocify.com/health (Vercel is not the API)
- [ ] 2 Railway — deploy status + bounded error/keyword logs
- [ ] 3 Vendor — open services/<name>.md, then GET via vocify-http.sh or MCP
- [ ] 4 Code — only after evidence; origin/main vs local WIP
- [ ] 5 Fix — smallest change; hotfix from origin/main; re-verify
```

Cards and IDs: [services/INDEX.md](services/INDEX.md).
Full playbook: [pipeline.md](pipeline.md).

```bash
.cursor/skills/debug-vocify-railway/scripts/vocify-railway.sh health
.cursor/skills/debug-vocify-railway/scripts/vocify-railway.sh errors
.cursor/skills/debug-vocify/scripts/vocify-http.sh resend GET /emails
```

## Evidence (Hugo, non-negotiable)

Operators may act on this in production. Invented logs have caused harm.

1. Do not say logs/HTTP/DB were **confirmed**, **verified**, or **logs show**
   unless that fact is in **this conversation's tool output**. Quote a short
   redacted snippet.
2. Docs or guesswork → label **Hypothesis (not verified):** then run a tool
   or ask for time window / email / company_id.
3. Failed or empty tool → say so. Do not invent a plausible body.
4. State what you checked and what you did not.

## Subagents

Parent keeps identity + synthesis. Dispatch when domains are independent
(e.g. Railway crash **and** Resend 422 **and** Stripe webhook). One subagent
per domain, in parallel. Each prompt must include: Vocify-only, time window,
[pipeline.md](pipeline.md) evidence rules, the service card path, and
"return evidence quotes + what you did not check — no fix unless asked."

| Domain | Agent | Card |
|---|---|---|
| Deploy / 502 / API logs | `shell` or `explore` | [railway.md](services/railway.md) |
| Named customer / company | `shell` | [admin.md](services/admin.md) |
| Vendor API / docs | `generalPurpose` | matching `services/*.md` |
| Code path after evidence | `explore` | repo, not vendor |

Do not spawn subagents for a single linear issue (one failed invite email).

## Symptom → card

| Symptom | Card |
|---|---|
| 502 / dashboard dead | [railway.md](services/railway.md) |
| Invite / password email | [resend.md](services/resend.md) |
| Seats / checkout | [stripe.md](services/stripe.md) |
| Twilio calls | [twilio.md](services/twilio.md) |
| Telnyx calls | [telnyx.md](services/telnyx.md) |
| WhatsApp | [unipile.md](services/unipile.md) |
| File STT | [deepgram.md](services/deepgram.md) |
| Live copilot STT | [speechmatics.md](services/speechmatics.md) |
| LLM / extraction | [openrouter.md](services/openrouter.md) |
| Auth / RLS | [supabase.md](services/supabase.md) |
| CRM | [hubspot.md](services/hubspot.md) / [salesforce.md](services/salesforce.md) |
| Named customer / “login as” / seats | [admin.md](services/admin.md) |
| Frontend-only | [vercel.md](services/vercel.md) |

## Mutations

Ask before `variable set`, redeploy, vendor POST, sending mail, or
`as-user` impersonation. Never print `MASTER_KEY` or minted JWTs.
Redeploying a crashed commit will crash again. Do not push local Telnyx/WIP.

## Reply shape

```
## Status
one sentence

## Evidence (this conversation)
- quote / status / deploy id

## Hypothesis (unverified)
- only if still unproven

## Next
- concrete tool or question
```
