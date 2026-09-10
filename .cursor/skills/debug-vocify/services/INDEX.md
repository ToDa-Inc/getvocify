# Vocify service catalog

Each card: what Vocify uses it for, env names, code, logs keyword, live API, docs/MCP.

| Service | Card | Env (names only) | Live access |
|---|---|---|---|
| Railway (API host) | [railway.md](railway.md) | — | CLI + MCP `user-railway` |
| Admin / subaccounts | [admin.md](admin.md) | `MASTER_KEY` | `vocify-admin.sh` (`X-Master-Key`) |
| Vercel (web app) | [vercel.md](vercel.md) | `VITE_API_URL` | Dashboard / `gh` |
| Resend | [resend.md](resend.md) | `RESEND_API_KEY`, `RESEND_FROM_EMAIL` | `vocify-http.sh resend` |
| Stripe | [stripe.md](stripe.md) | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | MCP `user-stripe` / curl |
| Twilio | [twilio.md](twilio.md) | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_*` | `vocify-http.sh twilio` |
| Telnyx | [telnyx.md](telnyx.md) | `TELNYX_API_KEY`, `TELNYX_*` | `vocify-http.sh telnyx` |
| Unipile | [unipile.md](unipile.md) | `UNIPILE_API_KEY`, `UNIPILE_BASE_URL` | `vocify-http.sh unipile` |
| Deepgram | [deepgram.md](deepgram.md) | `DEEPGRAM_API_KEY` | docs MCP + curl |
| Speechmatics | [speechmatics.md](speechmatics.md) | `SPEECHMATICS_API_KEY` | docs + logs |
| OpenRouter | [openrouter.md](openrouter.md) | `OPENROUTER_API_KEY` | docs MCP + curl |
| Supabase | [supabase.md](supabase.md) | `SUPABASE_URL`, `SUPABASE_*` | MCP `supabase2` |
| HubSpot | [hubspot.md](hubspot.md) | `HUBSPOT_CLIENT_*` | logs + HubSpot API |
| Salesforce | [salesforce.md](salesforce.md) | `SALESFORCE_CLIENT_*` | logs + SF API |

Keys live in Railway production vars and local `backend/.env`. The HTTP helper
reads them at runtime and never prints them.
