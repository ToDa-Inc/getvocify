# Vocify SaaS Production Audit — Findings

Last updated: 2026-08-11 (loop tick 1 — fixes verified)
Status: PARTIAL — reconnect HubSpot required for line items; billing still founder-led

## Fixes verified (Playwright)
- Book a demo link visible with HubSpot meetings URL
- Profile email shows dani@getvocify.com
- Settings shows line-items reconnect banner

## Environment
- Backend: http://localhost:8888 — healthy (Vertex AI)
- Frontend: http://localhost:8080 (vite; start.js log still says 5173 — misleading)
- Login API: works for dani@getvocify.com
- HubSpot portal: 147506535 (EU1), app_id 31731417
- Connected HubSpot user on token: itsdanilo.ai@gmail.com

## Critical
1. **Upgrade / Go Pro is dead UI**
   - `DashboardLayout.tsx` Upgrade button has no `onClick`, no `Link`, no Stripe/checkout.
   - Symptom: click does nothing.
   - Root cause: marketing stub with no billing product wired.

2. **HubSpot line-items scopes not on live OAuth grant**
   - App + backend authorize URL correctly request:
     `crm.objects.line_items.read/write`, `crm.schemas.line_items.read`
   - Live token scopes (10): contacts/companies/deals + schemas + oauth ONLY
   - Missing: all three line_items scopes
   - Evidence: schema `line_items` → HTTP 502/403 `deal-line-item-read` / missing scopes
   - Root cause: connection created before scopes were added; refresh_token does NOT expand scopes — user must reconnect OAuth.
   - HubSpot CLI: local `app-hsmeta.json` includes line item scopes; `hs project validate` OK. Deployed grant still stale until re-auth.

3. **`GET /api/v1/auth/me` returns empty email**
   - Hardcoded `email=""` in `auth.py` get_current_user and update_profile.
   - Profile UI may show blank email; comments say "MVP skip".

## High
4. **Settings HubSpot config: line items tab degraded**
   - Frontend swallows line_items schema failure (`.catch(() => null)`), tab shows opacity-60 with incomplete fields.
   - Users may think config is fine while line-item sync cannot work.

5. **Usage page backend OK; UX still thin**
   - `/memos/usage` returns real stats (25 memos, etc.).
   - Recent activity often "Untitled memo" — data quality / naming issue.
   - Change badges always styled as success green even for "No memos this week".

6. **start.js port messaging mismatch**
   - Prints Frontend :5173 but Vite serves :8080 → operator confusion.

## Medium / commits
7. Latest commits added line-item allowlists + OAuth scopes (`e6be0cf`, `03ef85a`, `4007aff`) — code asks for scopes; production grant not reconnected.
8. Uncommitted: extension company context + UI revamp; CRM company context endpoint — looks additive, needs E2E with extension.

## CRM token refresh (lookup logic)
Flow:
1. `crm_connections` row keyed by `user_id` + `provider=hubspot`
2. `get_hubspot_client_from_connection` / `_hubspot_access_token` → `ensure_fresh_hubspot_connection`
3. Refresh if expired or within 5-min buffer; per-connection lock; persist new tokens
4. Private apps without refresh_token skip refresh
5. Refresh failure → 401 "Please reconnect HubSpot"

Verdict: refresh implementation looks production-capable for access-token expiry.
Does NOT fix missing scopes — only reconnect expands scopes.

## Fixes applied (tick 1)
- `/auth/me` + profile update now return email from JWT (was hardcoded empty)
- Sidebar Upgrade stub → "Book a demo" linking to `DEMO_BOOKING_URL` (no Stripe yet)
- Settings HubSpot config shows reconnect banner when line-items schema fails

## Loop tick — HubSpot reconnect SUCCESS (2026-08-12 ~00:22)
- Live grant now 13/13 scopes including line_items
- `GET /crm/hubspot/schema?object_type=line_items` → **200** (134 properties)
- Previous blocker cleared

- Still no HubSpot reconnect (10 scopes, line_items 502); token refresh keeps working
- Fixed Settings: detect HubSpot via `listConnections` (not config row); empty state links to Integrations
- Heartbeat stretched to 60m while waiting on user reconnect

- Servers healthy; `/auth/me` email OK; token refresh OK
- Authorize asks line_items (13 scopes); notes not requested (correct after #9)
- Live grant still 10 scopes — line_items schema still 502
- HubSpot project #9 deployed; blocker remains user reconnect

- REVERTED `crm.objects.notes.write`: HubSpot marketplace deploy rejected scope as unrecognized (build #8 failed). Build #9 redeployed without it. Notes sync remains soft-fail until HubSpot exposes that scope for public apps.
- Line-items banner: no longer treats any schema null as missing scopes; checks permission/scope/deal-line-item in error detail.
- Auth email: DRY bearer helper; still JWT claim decode (token already auth'd by `get_user_id`).
- CTA copy: "Go Pro" → "Scale with us" + Book a demo (aligned).
- Migration 016 file present as untracked rename from colliding 014.

Agents: frontend UX, CRM token refresh, recent commits — all complete.

Shared production blockers:
1. HubSpot reconnect required (line items + now notes.write)
2. Dual HubSpot refresh implementations (oauth sync vs token_refresh async vs webhook)
3. Silent empty CRM context on extension auth failures
4. Settings/Usage UX gaps (partially fixed this tick)
5. Duplicate migration number 014 → renamed WhatsApp one to 016
6. Missing notes.write on OAuth (added to oauth.py + app-hsmeta + frontend types)

Still needs: HubSpot project upload/deploy for notes scope + user reconnect; unify refresh paths; Settings connection detection via listConnections.

## Playwright evidence (tick 1)
- Login → /dashboard OK
- Upgrade click: no nav / no dialog (pre-fix)
- Usage loads stats
- Settings HubSpot config visible; line_items schema 502
- Profile email empty (pre-fix)
