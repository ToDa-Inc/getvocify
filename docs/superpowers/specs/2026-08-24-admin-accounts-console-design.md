# Vocify Admin Accounts Console — Design

**Date**: 2026-08-24  
**Status**: Ready for implementation  
**Scope**: Phase 1 only (accounts, Login as, gated recovery)  
**Out of scope**: Landwork, GSC, debug agent / Hugo, billing, promotions, telemetry

---

## 1. Goal

Give founders a staff console on `app.getvocify.com/admin` that lists every Vocify account, shows how that account is configured (CRM, STT, glossary, product context), and lets staff **Login as** that user with a **master key**. Same ops pattern as SignalCore's Businesses tab, implemented in Vocify's existing Vite + FastAPI + Supabase stack — not a port of SignalCore's Next.js admin.

---

## 2. Auth model

Staff identity is a shared secret, not a role on `user_profiles`.

| Layer | Mechanism |
|-------|-----------|
| Backend | `X-Master-Key` must match `settings.MASTER_KEY` via `secrets.compare_digest`. Dependency: `require_master_key` in `backend/app/deps.py`. |
| Frontend unlock | Password-style input. Key is **not** hardcoded in the client (SignalCore still hardcodes a UI gate string; do not copy that). |
| Browser storage | `localStorage` key `vocify_admin_master_key_session` = `{ key, expiresAt }` with a 7-day TTL. Same idea as SignalCore `admin-auth.ts`. |
| Customer auth | Unchanged. Impersonation mints a **real** Supabase user session for the target account. |

If `MASTER_KEY` is unset or blank: every admin route returns **503** `"Admin is not configured"`. Do **not** fail the whole API boot — customers must keep working if admin is not set yet.

If the header is missing or wrong: **401** `"Invalid master key"`. Never log the provided key.

Production: set `MASTER_KEY` in Railway (random, `openssl rand -hex 32`). Document in `.env.example` with no sample value.

Admin HTTP routes do **not** use the customer Bearer JWT. The master key is sufficient. A founder may also be logged in as themselves; that session is irrelevant to admin APIs.

---

## 3. Routes

### Backend (`backend/app/api/admin.py`, prefix `/api/v1/admin`)

All endpoints: `Depends(require_master_key)`.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/accounts` | Paginated list. Query: `skip`, `limit` (default 20, max 100), `search`. |
| `GET` | `/accounts/{user_id}` | Full account detail. |
| `POST` | `/accounts/{user_id}/impersonate` | Mint that user's session. |
| `GET` | `/stuck-memos` | Memos in `transcribing` / `extracting` past the recovery threshold. |
| `POST` | `/recover-stuck-memos` | Call existing `RecoveryService.recover_all_stuck_memos()`. |
| `GET` | `/runtime` | Read-only: `stt_provider`, `llm_provider`, `extraction_model`, `copilot_model`, `environment`. No secrets. |

### Existing recover endpoint

`POST /health/recover-stuck-memos` today has **no auth**. Gate it with `require_master_key` as well. Startup recovery in `main.py` stays internal (no HTTP).

### Frontend (React Router in `src/App.tsx`)

| Path | Shell | Page |
|------|-------|------|
| `/admin` | `AdminLayout` (not `DashboardLayout`) | Unlock gate + accounts table |
| `/admin/accounts/:userId` | `AdminLayout` | Account detail |

Do **not** add `/admin` to `LANDING_PATHS`. `getvocify.com/admin` already redirects to `app.getvocify.com/admin` via `LandingDomainRedirect`.

---

## 4. Data shapes

An "account" is one `auth.users` row + `user_profiles` (`id` = auth user id). There is no org/business table.

### List item (`AdminAccountListItem`)

- `id`, `email`, `full_name`, `company_name`, `phone`
- `created_at`, `last_sign_in_at` (from `auth.users`)
- `crm`: array of `{ provider, status, token_expires_at }`
- `memo_count`, `approved_count`, `failed_count`, `last_memo_at`

### Detail (`AdminAccountDetail`)

Everything in the list item, plus:

- Profile: `product_context`, `stt_languages`, `glossary` (length + preview), `primary_crm_connection_id`
- Each CRM connection's `crm_configurations` row: pipeline/stage names, allowed field arrays, auto-create flags, `lost_lead_status_value`, `on_hold_lead_status_value`
- Last 20 memos: `id`, `status`, `source`, `created_at`, company name from extraction, `error_message` if failed
- Usage rollup: same numbers as `GET /memos/usage` but for this `user_id`

### List query (no new SQL views)

For one page of profile rows:

1. `user_profiles` — `range(skip, skip+limit-1)`, optional `or` ilike on `full_name` / `company_name` / `id`. If `search` contains `@`, also match `auth.users.email`.
2. `auth.users` via existing PostgREST pattern (`supabase.postgrest.schema("auth").from_("users")`) for `id, email, last_sign_in_at`.
3. `crm_connections` for those `user_id`s.
4. `memos` `select user_id, status, created_at` for those `user_id`s, aggregate in Python.

Current tenant count is small (founder-led). If this query becomes heavy, add a SQL view later — not in this spec.

### Impersonate response

Same wire shape as login (`AuthResponse`): `user`, `access_token`, `refresh_token`. Frontend maps snake_case like `authApi.login`.

Implementation: extract the existing `generate_link` + `verify_otp` path from `_reissue_session_for_verified_claims` in `backend/app/api/auth.py` into `mint_session_for_email(email) -> RefreshResponse`. Impersonate resolves email via `auth.admin.get_user_by_id`, then calls that helper. Refresh reissue keeps using it.

If the user has no email: **400**. If mint fails: **503**.

---

## 5. Login as — frontend session dance

Storage keys (all `localStorage`):

| Key | Role |
|-----|------|
| `vocify_admin_master_key_session` | Master key + TTL. Survives impersonation. |
| `vocify_token` / `vocify_refresh` | Active customer session (unchanged names). |
| `vocify_admin_saved_session` | Founder's own tokens, if they were logged in before Login as. |
| `vocify_admin_impersonation` | `{ accountId, email, fullName, startedAt }` |

**Login as**

1. POST impersonate with `X-Master-Key`.
2. Copy current `vocify_token` / `vocify_refresh` into `vocify_admin_saved_session` (or clear that key if none).
3. Write `vocify_admin_impersonation`.
4. Write the minted tokens into `vocify_token` / `vocify_refresh` (same helpers as login).
5. `window.location.assign('/dashboard')` so AuthProvider remounts as that user.

**Return to admin**

1. Restore `vocify_admin_saved_session` into token keys, or clear customer tokens.
2. Remove `vocify_admin_impersonation`.
3. Leave the master-key session in place.
4. `window.location.assign('/admin')`.

**Banner** on `DashboardLayout` when impersonation meta exists: “Viewing as {email}” + **Return to admin**. Sidebar Logout while impersonating calls Return to admin (does not wipe the master key).

**Admin 401**: wrong master key. Do **not** run the customer JWT refresh/clear path. Exclude paths starting `/admin` from `shouldAttemptRefreshForEndpoint` in `src/shared/lib/api-client.ts`.

---

## 6. Audit

No staff user id exists with a master key. Still record:

Table `admin_audit_log` (migration `023_admin_audit_log.sql`):

- `id` uuid pk
- `action` text (`impersonate`, `recover_stuck_memos`)
- `target_user_id` uuid null
- `metadata` jsonb default `{}`
- `created_at` timestamptz default now()

RLS on; no anon policies. Backend uses service role. Insert on impersonate and recover. Fail-open: if insert fails, still complete the action and log a warning — ops must not be blocked by audit.

---

## 7. UI

Vocify theme (`THEME_TOKENS`, cream/beige), not a SignalCore clone.

**Unlock** (`/admin` with no valid stored key): single field + Unlock. Invalid key shows the API 401.

**Accounts table**: search, pagination, columns Email, Name, Company, CRM (provider + status badge), Memos, Last memo, Created. Row click → detail. Row action **Login as**.

**Detail**: profile block, CRM config block(s), recent memos, **Login as**, link back to list. Runtime strip on the list page (STT / LLM / models) from `GET /runtime`. Stuck-memos count + Recover button on the list page.

No edit-account, no plan/balance, no delete user in this phase.

---

## 8. Security constraints

- Never ship `MASTER_KEY` in the frontend bundle or `.env.example` as a real value.
- Constant-time compare.
- Admin pages are a normal SPA route; secrecy is the key, not obscurity. Still keep them off the marketing domain via the existing redirect.
- Impersonation is a full customer session. Staff can approve CRM writes as that user. That is intended. Audit it.
- `POST /health/recover-stuck-memos` must not stay public.

---

## 9. Testing

Backend (pytest, same style as `backend/tests/test_auth_session.py`):

- `verify_master_key`: missing config → 503; mismatch → 401; match → ok.
- Account list assembler: given fake profile / auth / crm / memo rows, returns the expected list item.
- Impersonate: missing email → 400 (unit on the guard).

Frontend (`node --test`):

- Admin master-key TTL store: set, get, expire, clear.
- Impersonation meta: set / clear / detect.

No live Supabase or Railway in unit tests.

---

## 10. Explicit non-goals (later phases)

- Landwork / GSC / sitemap CMS
- Debug agent (SQL/codebase/Railway logs)
- Stripe / plans
- Feature-flag CMS
- Editing another user's CRM allowlists from admin (read-only now; Login as is how you change them)
