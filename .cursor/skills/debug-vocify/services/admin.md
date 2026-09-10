# Admin / master key

Staff access to every Vocify account and company (Hugo's tenant impersonation).

`MASTER_KEY` is in `backend/.env` and Railway production. The helper loads it
at runtime. **Never print the key or impersonation tokens.**

| | |
|---|---|
| Header | `X-Master-Key` |
| Base | `https://api.getvocify.com/api/v1/admin` (prod) or `http://localhost:8888/api/v1/admin` |
| Code | `backend/app/api/admin.py`, `backend/app/deps.py` `require_master_key` |
| UI | `app.getvocify.com/admin` |
| Helper | `.cursor/skills/debug-vocify/scripts/vocify-admin.sh` |

## When to use

Phase 0 of the debug pipeline when the user names a customer email, company,
or "login as" / subaccount. This is how you inspect **their** CRM, seats,
invites, and memos — not only platform logs.

## Safe reads (default)

```bash
.cursor/skills/debug-vocify/scripts/vocify-admin.sh runtime
.cursor/skills/debug-vocify/scripts/vocify-admin.sh accounts --search ada@acme.com
.cursor/skills/debug-vocify/scripts/vocify-admin.sh account <user_id>
.cursor/skills/debug-vocify/scripts/vocify-admin.sh companies --search Acme
.cursor/skills/debug-vocify/scripts/vocify-admin.sh company <company_id>
.cursor/skills/debug-vocify/scripts/vocify-admin.sh stuck-memos
```

`GET /accounts/{id}` returns profile, CRM connection **status** (not raw
OAuth tokens if the assembler redacts them — still treat the payload as
sensitive). Quote email, company_id, seat counts, memo status only.

## Impersonate (ask first)

`POST /accounts/{user_id}/impersonate` mints a real user session (audited).
Use only when the user asked to act as that account (replay a tenant API,
confirm what they see).

```bash
.cursor/skills/debug-vocify/scripts/vocify-admin.sh as-user <user_id> GET /api/v1/auth/me
```

The helper uses the minted JWT for that one request and **does not print
tokens**. Do not paste `access_token` / `refresh_token` into chat.

## Mutations (ask first)

Invite, seat limit, recover stuck memos, transfer owner — admin POST/PATCH/DELETE.
Prefer the smallest read that answers the question.
