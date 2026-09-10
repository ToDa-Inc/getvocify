# Stripe

Workspace plans (Starter/Pro × monthly/yearly): checkout, customer portal, webhooks.

| | |
|---|---|
| Env | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` (optional `STRIPE_PRICE_STARTER_MONTHLY` / `PRO` / yearly) |
| Code | `backend/app/services/billing/stripe_service.py`, `backend/app/api/stripe_webhooks.py` |
| Webhook | `POST /api/v1/webhooks/stripe` |
| Logs | `stripe` |
| API | `https://api.stripe.com/v1` |
| MCP | `user-stripe` — run `mcp_auth` if `needsAuth` |
| Docs | https://docs.stripe.com |

```bash
.cursor/skills/debug-vocify-railway/scripts/vocify-railway.sh logs --filter "stripe"
.cursor/skills/debug-vocify/scripts/vocify-http.sh stripe GET /v1/balance
```

Prefer Stripe MCP for customers/subscriptions once authenticated. Ask before
refunds, price changes, or writing webhook secrets.
