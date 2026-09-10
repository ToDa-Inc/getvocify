# Resend

Transactional mail: team invites, password reset, member removed.

| | |
|---|---|
| Env | `RESEND_API_KEY`, `RESEND_FROM_EMAIL` |
| Code | `backend/app/integrations/resend_client.py`, `backend/app/services/company.py` |
| Logs | `email`, `resend`, `invite` |
| API | `https://api.resend.com` |
| Docs | https://resend.com/docs — MCP `user-resend` (docs) if configured |
| Account MCP | `npx -y resend-mcp` or `https://mcp.resend.com/mcp` (needs key/OAuth; do not commit keys) |

`from` must be `email@domain` or `Name <email@domain>`. Vocify's verified
Resend domain is `mail.getvocify.com`, so use `hello@mail.getvocify.com`
(or similar). A bare domain becomes `Vocify <mail.getvocify.com>` and
Resend returns **422**. Code default `hello@getvocify.com` only works if
that domain is also verified.

```bash
.cursor/skills/debug-vocify-railway/scripts/vocify-railway.sh logs --filter "resend"
.cursor/skills/debug-vocify/scripts/vocify-http.sh resend GET /emails
.cursor/skills/debug-vocify/scripts/vocify-http.sh resend GET /domains
```

List emails, then `GET /emails/{id}` for the failed send. Confirm `RESEND_FROM_EMAIL`
is a real address (name only in chat). Ask before sending a test email.
