# Admin Accounts Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a master-key-gated `/admin` console that lists Vocify accounts, shows CRM/STT configuration, impersonates a user into a real dashboard session, and gates stuck-memo recovery.

**Architecture:** FastAPI `/api/v1/admin/*` with `X-Master-Key` (`secrets.compare_digest` against `MASTER_KEY`). Vite React Router pages outside `DashboardLayout`. Impersonation reuses the existing GoTrue `generate_link` + `verify_otp` path already used by refresh reissue. Customer JWT refresh must not run on `/admin` 401s.

**Tech Stack:** FastAPI, Pydantic, Supabase service-role client, pytest; Vite, React Router 6, TanStack Query, Tailwind / existing `THEME_TOKENS`, `node --test`.

## Global Constraints

- Phase 1 only: accounts list/detail, Login as, runtime strip, stuck-memo recover. No Landwork, GSC, debug agent, billing, or account edits.
- Do not hardcode a master key in frontend source.
- If `MASTER_KEY` is unset, admin routes return 503; the rest of the API still boots.
- `POST /health/recover-stuck-memos` must require the master key.
- Follow existing naming: backend snake_case JSON, frontend camelCase mappers like `src/features/auth/api.ts`.
- Backend tests: `cd backend && python -m pytest tests/test_<file>.py -v`
- Frontend tests: `node --test src/lib/admin-auth.test.ts src/lib/admin-impersonation.test.ts`
- Production build: `npm run build`

## File map

**Create**

- `backend/app/api/admin.py`
- `backend/app/services/admin_accounts.py`
- `backend/app/services/admin_session.py`
- `backend/migrations/023_admin_audit_log.sql`
- `backend/tests/test_admin_auth.py`
- `backend/tests/test_admin_accounts.py`
- `src/lib/admin-auth.ts`
- `src/lib/admin-auth.test.ts`
- `src/lib/admin-impersonation.ts`
- `src/lib/admin-impersonation.test.ts`
- `src/features/admin/types.ts`
- `src/features/admin/api.ts`
- `src/pages/admin/AdminAccountsPage.tsx`
- `src/pages/admin/AdminAccountDetailPage.tsx`
- `src/components/admin/AdminLayout.tsx`
- `src/components/admin/ImpersonationBanner.tsx`

**Modify**

- `backend/app/config.py` — `MASTER_KEY: Optional[str] = None`
- `backend/app/deps.py` — `verify_master_key` / `require_master_key`
- `backend/app/api/router.py` — include admin router
- `backend/app/api/health.py` — gate recover
- `backend/app/api/auth.py` — call `mint_session_for_email`
- `.env.example` — commented `MASTER_KEY`
- `src/App.tsx` — `/admin` routes
- `src/shared/lib/api-client.ts` — skip refresh for `/admin`; optional headers on get/post
- `src/components/dashboard/DashboardLayout.tsx` — impersonation banner + logout override

---

### Task 1: Master-key dependency

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/deps.py`
- Create: `backend/tests/test_admin_auth.py`

**Interfaces:**
- Consumes: `settings` from `app.config`
- Produces: `verify_master_key(provided: Optional[str]) -> str`, `require_master_key(...) -> str`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_admin_auth.py`:

```python
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.deps import verify_master_key


def test_unset_master_key_is_unavailable():
    with patch("app.deps.settings") as settings:
        settings.MASTER_KEY = None
        with pytest.raises(HTTPException) as exc:
            verify_master_key("anything")
        assert exc.value.status_code == 503


def test_blank_master_key_is_unavailable():
    with patch("app.deps.settings") as settings:
        settings.MASTER_KEY = "   "
        with pytest.raises(HTTPException) as exc:
            verify_master_key("   ")
        assert exc.value.status_code == 503


def test_wrong_key_is_unauthorized():
    with patch("app.deps.settings") as settings:
        settings.MASTER_KEY = "correct-key-value"
        with pytest.raises(HTTPException) as exc:
            verify_master_key("wrong")
        assert exc.value.status_code == 401


def test_missing_header_is_unauthorized():
    with patch("app.deps.settings") as settings:
        settings.MASTER_KEY = "correct-key-value"
        with pytest.raises(HTTPException) as exc:
            verify_master_key(None)
        assert exc.value.status_code == 401


def test_matching_key_returns_the_key():
    with patch("app.deps.settings") as settings:
        settings.MASTER_KEY = "correct-key-value"
        assert verify_master_key("correct-key-value") == "correct-key-value"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_admin_auth.py -v`

Expected: FAIL — `verify_master_key` is not defined.

- [ ] **Step 3: Implement config + verifier**

In `backend/app/config.py`, inside `class Settings`, after the metrics/Sentry block, add:

```python
    # Internal admin console. Unset = admin routes return 503; app still boots.
    MASTER_KEY: Optional[str] = None
```

In `backend/app/deps.py`, add imports `secrets` (already has `Header`, `HTTPException`, `Optional`) and:

```python
def verify_master_key(provided: Optional[str]) -> str:
    expected = (getattr(settings, "MASTER_KEY", None) or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin is not configured",
        )
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid master key",
        )
    return provided


def require_master_key(
    x_master_key: Optional[str] = Header(None, alias="X-Master-Key"),
) -> str:
    return verify_master_key(x_master_key)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_admin_auth.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/app/deps.py backend/tests/test_admin_auth.py
git commit -m "$(cat <<'EOF'
feat(admin): add master-key verifier for staff API routes

EOF
)"
```

---

### Task 2: Session mint helper (shared by refresh + impersonate)

**Files:**
- Create: `backend/app/services/admin_session.py`
- Modify: `backend/app/api/auth.py` (`_reissue_session_for_verified_claims`)
- Test: extend `backend/tests/test_admin_auth.py` with a mint-email guard test if you add a pure helper; otherwise the impersonate endpoint tests in Task 4 cover this.

**Interfaces:**
- Consumes: `get_supabase()`, `get_supabase_auth()`, `RefreshResponse` from `app.api.auth` — **do not import RefreshResponse from auth.py into a service** (circular). Define a small dataclass in the service.
- Produces: `mint_session_for_email(email: str) -> MintedSession` where `MintedSession` has `access_token`, `refresh_token`, `expires_in: int`

- [ ] **Step 1: Add `backend/app/services/admin_session.py`**

```python
from dataclasses import dataclass

from fastapi import HTTPException, status

from app.deps import get_supabase, get_supabase_auth


@dataclass
class MintedSession:
    access_token: str
    refresh_token: str
    expires_in: int


def mint_session_for_email(email: str) -> MintedSession:
    resolved = (email or "").strip()
    if not resolved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account has no email; cannot impersonate",
        )
    admin = get_supabase()
    link = admin.auth.admin.generate_link({"type": "magiclink", "email": resolved})
    props = getattr(link, "properties", None)
    email_otp = getattr(props, "email_otp", None) if props else None
    hashed = getattr(props, "hashed_token", None) if props else None
    if not email_otp and not hashed:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service temporarily unreachable. Please try again.",
        )
    auth_client = get_supabase_auth()
    if email_otp:
        verified = auth_client.auth.verify_otp(
            {"email": resolved, "token": email_otp, "type": "magiclink"}
        )
    else:
        verified = auth_client.auth.verify_otp(
            {"token_hash": hashed, "type": "magiclink"}
        )
    session = getattr(verified, "session", None)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service temporarily unreachable. Please try again.",
        )
    return MintedSession(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_in=session.expires_in or 3600,
    )
```

Copy this from the `generate_link` / `verify_otp` block inside `_reissue_session_for_verified_claims` (approx. lines 492–522 of `backend/app/api/auth.py`). Then replace that block with:

```python
    from app.services.admin_session import mint_session_for_email

    minted = mint_session_for_email(resolved_email)
    logger.warning(
        "Supabase refresh broken (oauth_client_id); re-issued session via verified JWT for %s",
        resolved_email,
    )
    return RefreshResponse(
        access_token=minted.access_token,
        refresh_token=minted.refresh_token,
        expires_in=minted.expires_in,
    )
```

Keep the existing `if not resolved_email` 503 branch **before** calling mint (refresh must not become a 400).

- [ ] **Step 2: Run existing auth tests**

Run: `cd backend && python -m pytest tests/test_auth_session.py tests/test_admin_auth.py -v`

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/admin_session.py backend/app/api/auth.py
git commit -m "$(cat <<'EOF'
refactor(auth): extract session mint for admin impersonation

EOF
)"
```

---

### Task 3: Account list/detail assembler

**Files:**
- Create: `backend/app/services/admin_accounts.py`
- Create: `backend/tests/test_admin_accounts.py`

**Interfaces:**
- Consumes: raw dict rows from PostgREST
- Produces: `assemble_account_list_items(profiles, auth_users, connections, memos) -> list[dict]` and `assemble_account_detail(...)` used by the API in Task 4.

- [ ] **Step 1: Write the failing assembler tests**

Create `backend/tests/test_admin_accounts.py`:

```python
from app.services.admin_accounts import assemble_account_list_items

USER = "11111111-1111-1111-1111-111111111111"


def test_assemble_list_item_joins_email_crm_and_memo_counts():
    items = assemble_account_list_items(
        profiles=[{
            "id": USER,
            "full_name": "Ada",
            "company_name": "Acme",
            "phone": "+1555",
            "created_at": "2026-01-01T00:00:00+00:00",
        }],
        auth_users=[{
            "id": USER,
            "email": "ada@acme.com",
            "last_sign_in_at": "2026-08-01T00:00:00+00:00",
        }],
        connections=[{
            "user_id": USER,
            "provider": "hubspot",
            "status": "connected",
            "token_expires_at": "2026-09-01T00:00:00+00:00",
        }],
        memos=[
            {"user_id": USER, "status": "approved", "created_at": "2026-08-20T00:00:00+00:00"},
            {"user_id": USER, "status": "failed", "created_at": "2026-08-19T00:00:00+00:00"},
        ],
    )
    assert len(items) == 1
    row = items[0]
    assert row["email"] == "ada@acme.com"
    assert row["memo_count"] == 2
    assert row["approved_count"] == 1
    assert row["failed_count"] == 1
    assert row["last_memo_at"] == "2026-08-20T00:00:00+00:00"
    assert row["crm"][0]["provider"] == "hubspot"


def test_assemble_list_item_without_auth_row_has_empty_email():
    items = assemble_account_list_items(
        profiles=[{"id": USER, "full_name": None, "company_name": None, "phone": None, "created_at": ""}],
        auth_users=[],
        connections=[],
        memos=[],
    )
    assert items[0]["email"] == ""
    assert items[0]["memo_count"] == 0
    assert items[0]["crm"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_admin_accounts.py -v`

Expected: FAIL — module not found.

- [ ] **Step 3: Implement assembler**

Create `backend/app/services/admin_accounts.py` with `assemble_account_list_items` that indexes `auth_users` and `connections` by id/`user_id`, counts memo statuses per `user_id`, and returns dicts with keys: `id`, `email`, `full_name`, `company_name`, `phone`, `created_at`, `last_sign_in_at`, `crm` (list of `{provider, status, token_expires_at}`), `memo_count`, `approved_count`, `failed_count`, `last_memo_at`.

Also add `assemble_account_detail(profile, auth_user, connections, configurations, recent_memos, usage) -> dict` used in Task 4. Keep it a pure join: profile fields + `product_context`, `stt_languages`, `glossary`, `primary_crm_connection_id`; nested `connections` each with matching `crm_configurations` (pipeline names, allowed_* arrays, auto-create, lost/on-hold status values); `recent_memos` as provided; `usage` as provided.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_admin_accounts.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/admin_accounts.py backend/tests/test_admin_accounts.py
git commit -m "$(cat <<'EOF'
feat(admin): assemble cross-tenant account list rows

EOF
)"
```

---

### Task 4: Admin HTTP API + audit log + gated recover

**Files:**
- Create: `backend/app/api/admin.py`
- Create: `backend/migrations/023_admin_audit_log.sql`
- Modify: `backend/app/api/router.py`
- Modify: `backend/app/api/health.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `require_master_key`, `assemble_account_list_items`, `mint_session_for_email`, `RecoveryService`, `_user_response` from `app.api.auth`
- Produces: routes under `/api/v1/admin` listed in the spec

- [ ] **Step 1: Add migration `backend/migrations/023_admin_audit_log.sql`**

```sql
CREATE TABLE IF NOT EXISTS admin_audit_log (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  action TEXT NOT NULL,
  target_user_id UUID,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE admin_audit_log ENABLE ROW LEVEL SECURITY;
```

No anon policies. Service role bypasses RLS.

- [ ] **Step 2: Implement `backend/app/api/admin.py`**

Router:

```python
router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
```

Helpers (same file or `admin_accounts.py`):

- `_emails_and_signins(supabase, ids)` — `supabase.postgrest.schema("auth").from_("users").select("id,email,last_sign_in_at").in_("id", ids)`
- `_write_audit(supabase, action, target_user_id=None, metadata=None)` — try insert; on failure log warning and continue

Endpoints:

1. `GET /accounts?skip=0&limit=20&search=`  
   Clamp limit to 1..100. Load `user_profiles` ordered by `created_at` desc. If `search` is set: `or_(f"full_name.ilike.%{q}%,company_name.ilike.%{q}%,id.eq.{q}")` when q is a uuid, else ilike name/company. If search contains `@`, query `auth.users` for email ilike and filter profile ids. Then load connections + memos for the page ids, assemble, return `{ "accounts": [...], "total": int, "skip", "limit" }`. Total = count query on the same profile filter (`count="exact", head=True`).

2. `GET /accounts/{user_id}`  
   404 if no profile. Load auth user, connections, configurations (`crm_configurations` for those connection ids), last 20 memos (`id,status,source,created_at,extraction,error_message` ordered desc). Build usage counts from those memo rows plus a wider select of `status,created_at,audio_duration,extraction` capped at 2000 like `get_usage`. Return assembled detail.

3. `POST /accounts/{user_id}/impersonate`  
   Load auth user by id. 404 if missing. `mint_session_for_email(email)`. Load profile (empty dict ok). Return `{ "user": _user_response(...), "access_token", "refresh_token" }` matching `AuthResponse`. Audit `impersonate`.

4. `GET /stuck-memos` — `RecoveryService.find_stuck_memos()`; return `{ "memos": [{id, user_id, status, processing_started_at, error_message}] }`

5. `POST /recover-stuck-memos` — `recover_all_stuck_memos()`; audit; return the recovery dict.

6. `GET /runtime` — `{ "stt_provider": settings.STT_PROVIDER, "llm_provider": settings.LLM_PROVIDER, "extraction_model": settings.EXTRACTION_MODEL, "copilot_model": settings.COPILOT_MODEL, "environment": settings.ENVIRONMENT }`

Every endpoint: `_: str = Depends(require_master_key)` and `supabase: Client = Depends(get_supabase)`.

- [ ] **Step 3: Mount and gate health recover**

In `backend/app/api/router.py`:

```python
from app.api import admin
api_router.include_router(admin.router)
```

In `backend/app/api/health.py`, add `require_master_key` to `recover_stuck_memos`:

```python
async def recover_stuck_memos(
    supabase: Client = Depends(get_supabase),
    _: str = Depends(require_master_key),
):
```

- [ ] **Step 4: Document env**

In `.env.example`, after the Supabase block, add:

```
# Internal admin (/admin). Generate with: openssl rand -hex 32
# Unset = admin API returns 503; the rest of the app still runs.
# MASTER_KEY=
```

Do not put a real or placeholder secret.

- [ ] **Step 5: Run backend tests**

Run: `cd backend && python -m pytest tests/test_admin_auth.py tests/test_admin_accounts.py tests/test_auth_session.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/admin.py backend/app/api/router.py backend/app/api/health.py backend/migrations/023_admin_audit_log.sql .env.example
git commit -m "$(cat <<'EOF'
feat(admin): add account list, impersonate, and gated recovery APIs

EOF
)"
```

---

### Task 5: Frontend admin auth + impersonation storage

**Files:**
- Create: `src/lib/admin-auth.ts`
- Create: `src/lib/admin-auth.test.ts`
- Create: `src/lib/admin-impersonation.ts`
- Create: `src/lib/admin-impersonation.test.ts`

**Interfaces:**
- Produces: `getStoredAdminMasterKey()`, `setStoredAdminMasterKey(key)`, `clearStoredAdminMasterKey()`, `ADMIN_MASTER_KEY_TTL_MS`; `getImpersonation()`, `setImpersonation(meta)`, `clearImpersonation()`, `saveCustomerSessionForReturn()`, `restoreCustomerSessionAfterImpersonation()`

- [ ] **Step 1: Write failing tests**

`src/lib/admin-auth.test.ts` — copy the 7-day TTL behavior from SignalCore `lib/admin/admin-auth.ts` but with key `vocify_admin_master_key_session`:

```ts
import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import {
  getStoredAdminMasterKey,
  setStoredAdminMasterKey,
  clearStoredAdminMasterKey,
  ADMIN_MASTER_KEY_TTL_MS,
} from "./admin-auth.ts";

describe("admin master key session", () => {
  beforeEach(() => {
    const store: Record<string, string> = {};
    globalThis.localStorage = {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v; },
      removeItem: (k: string) => { delete store[k]; },
      clear: () => { for (const k of Object.keys(store)) delete store[k]; },
      key: () => null,
      length: 0,
    } as Storage;
  });

  it("returns null when empty", () => {
    assert.equal(getStoredAdminMasterKey(), null);
  });

  it("round-trips a key", () => {
    setStoredAdminMasterKey("secret");
    assert.equal(getStoredAdminMasterKey(), "secret");
  });

  it("expires after TTL", () => {
    setStoredAdminMasterKey("secret");
    const raw = JSON.parse(localStorage.getItem("vocify_admin_master_key_session")!);
    raw.expiresAt = Date.now() - 1;
    localStorage.setItem("vocify_admin_master_key_session", JSON.stringify(raw));
    assert.equal(getStoredAdminMasterKey(), null);
    assert.equal(localStorage.getItem("vocify_admin_master_key_session"), null);
  });

  it("uses a 7-day TTL", () => {
    assert.equal(ADMIN_MASTER_KEY_TTL_MS, 7 * 24 * 60 * 60 * 1000);
  });
});
```

`src/lib/admin-impersonation.test.ts`:

```ts
import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import {
  getImpersonation,
  setImpersonation,
  clearImpersonation,
  saveCustomerSessionForReturn,
  restoreCustomerSessionAfterImpersonation,
} from "./admin-impersonation.ts";

describe("admin impersonation storage", () => {
  beforeEach(() => {
    const store: Record<string, string> = {};
    globalThis.localStorage = {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v; },
      removeItem: (k: string) => { delete store[k]; },
      clear: () => { for (const k of Object.keys(store)) delete store[k]; },
      key: () => null,
      length: 0,
    } as Storage;
  });

  it("stores viewing-as meta", () => {
    setImpersonation({ accountId: "u1", email: "a@b.c", fullName: "Ada", startedAt: "t" });
    assert.equal(getImpersonation()?.email, "a@b.c");
    clearImpersonation();
    assert.equal(getImpersonation(), null);
  });

  it("saves and restores customer tokens", () => {
    localStorage.setItem("vocify_token", "old-access");
    localStorage.setItem("vocify_refresh", "old-refresh");
    saveCustomerSessionForReturn();
    localStorage.setItem("vocify_token", "impersonated");
    localStorage.setItem("vocify_refresh", "imp-refresh");
    restoreCustomerSessionAfterImpersonation();
    assert.equal(localStorage.getItem("vocify_token"), "old-access");
    assert.equal(localStorage.getItem("vocify_refresh"), "old-refresh");
  });

  it("clears tokens when there was no prior session", () => {
    saveCustomerSessionForReturn();
    localStorage.setItem("vocify_token", "impersonated");
    restoreCustomerSessionAfterImpersonation();
    assert.equal(localStorage.getItem("vocify_token"), null);
  });
});
```

If `node --test` cannot polyfill `localStorage` this way, implement a tiny `storage` injectable in the modules for tests only — prefer the global stub above; it matches how the app reads `window.localStorage`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test src/lib/admin-auth.test.ts src/lib/admin-impersonation.test.ts`

Expected: FAIL — modules missing.

- [ ] **Step 3: Implement the two modules**

`src/lib/admin-auth.ts`: same JSON `{ key, expiresAt }` pattern as SignalCore `signalcore-frontend/lib/admin/admin-auth.ts`, storage key `vocify_admin_master_key_session`, TTL 7 days. No hardcoded key string.

`src/lib/admin-impersonation.ts`:

- Storage key `vocify_admin_impersonation` for the meta object.
- Storage key `vocify_admin_saved_session` for `{ accessToken, refreshToken } | null`.
- `saveCustomerSessionForReturn` reads `vocify_token` / `vocify_refresh`; if both present, save them; else save `null`.
- `restoreCustomerSessionAfterImpersonation` writes them back or removes both keys, then deletes `vocify_admin_saved_session` and impersonation meta.

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test src/lib/admin-auth.test.ts src/lib/admin-impersonation.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lib/admin-auth.ts src/lib/admin-auth.test.ts src/lib/admin-impersonation.ts src/lib/admin-impersonation.test.ts
git commit -m "$(cat <<'EOF'
feat(admin): persist master key and impersonation session locally

EOF
)"
```

---

### Task 6: Admin API client + api-client header/refresh changes

**Files:**
- Create: `src/features/admin/types.ts`
- Create: `src/features/admin/api.ts`
- Modify: `src/shared/lib/api-client.ts`

**Interfaces:**
- Consumes: `getStoredAdminMasterKey()`, `api.get` / `api.post` with extra headers
- Produces: `adminApi.listAccounts`, `getAccount`, `impersonate`, `stuckMemos`, `recoverStuckMemos`, `runtime`; `adminKeys`

- [ ] **Step 1: Allow optional headers on get/post and skip refresh for `/admin`**

In `src/shared/lib/api-client.ts`, update `shouldAttemptRefreshForEndpoint`:

```ts
function shouldAttemptRefreshForEndpoint(endpoint: string): boolean {
  if (endpoint.startsWith("/admin")) return false;
  return (
    endpoint !== "/auth/refresh" &&
    endpoint !== "/auth/login" &&
    endpoint !== "/auth/signup"
  );
}
```

Change `get` / `post` signatures to accept optional `RequestInit`:

```ts
get<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  return this.request<T>(endpoint, { method: "GET", ...options });
}

post<T>(endpoint: string, data?: unknown, options: RequestInit = {}): Promise<T> {
  return this.request<T>(endpoint, {
    method: "POST",
    body: data ? JSON.stringify(data) : undefined,
    ...options,
  });
}
```

Existing callers stay valid (optional last arg).

- [ ] **Step 2: Types + API**

`src/features/admin/types.ts` — TypeScript interfaces matching the spec (camelCase): `AdminCrmConnection`, `AdminAccountListItem`, `AdminAccountDetail`, `AdminStuckMemo`, `AdminRuntime`, `AdminAccountListResponse`.

`src/features/admin/api.ts`:

```ts
function masterHeaders(): HeadersInit {
  const key = getStoredAdminMasterKey();
  return key ? { "X-Master-Key": key } : {};
}

export const adminApi = {
  listAccounts: (args: { skip?: number; limit?: number; search?: string }) => {
    const params = new URLSearchParams();
    if (args.skip) params.set("skip", String(args.skip));
    if (args.limit) params.set("limit", String(args.limit));
    if (args.search) params.set("search", args.search);
    const q = params.toString();
    return api.get<RawList>(`/admin/accounts${q ? `?${q}` : ""}`, { headers: masterHeaders() }).then(mapList);
  },
  getAccount: (id: string) =>
    api.get<RawDetail>(`/admin/accounts/${id}`, { headers: masterHeaders() }).then(mapDetail),
  impersonate: (id: string) =>
    api.post<Record<string, unknown>>(`/admin/accounts/${id}/impersonate`, undefined, {
      headers: masterHeaders(),
    }),
  stuckMemos: () => api.get<RawStuck>(`/admin/stuck-memos`, { headers: masterHeaders() }),
  recoverStuckMemos: () =>
    api.post<Record<string, unknown>>(`/admin/recover-stuck-memos`, undefined, {
      headers: masterHeaders(),
    }),
  runtime: () => api.get<AdminRuntime>(`/admin/runtime`, { headers: masterHeaders() }),
};
```

Map snake_case → camelCase the same way `authApi` maps users. `impersonate` should return `{ user, accessToken, refreshToken }` using the same `mapRawUser` logic (duplicate a small mapper here; do not import private helpers from auth/api).

- [ ] **Step 3: Typecheck**

Run: `npm run build`

Expected: PASS (pages not wired yet; unused exports are fine if TS doesn't noUnusedLocals-fail — if it does, the pages in Task 7 land in the same commit... prefer Task 7 immediately after. If build fails on unused, skip build until Task 7.)

- [ ] **Step 4: Commit**

```bash
git add src/features/admin/types.ts src/features/admin/api.ts src/shared/lib/api-client.ts
git commit -m "$(cat <<'EOF'
feat(admin): add staff API client with master-key header

EOF
)"
```

---

### Task 7: Admin UI — unlock, list, detail, routes

**Files:**
- Create: `src/components/admin/AdminLayout.tsx`
- Create: `src/pages/admin/AdminAccountsPage.tsx`
- Create: `src/pages/admin/AdminAccountDetailPage.tsx`
- Modify: `src/App.tsx`

**Interfaces:**
- Consumes: `adminApi`, `getStoredAdminMasterKey`, `setStoredAdminMasterKey`, `THEME_TOKENS`
- Produces: `/admin` and `/admin/accounts/:userId` working against a live API when `MASTER_KEY` is set

- [ ] **Step 1: `AdminLayout`**

Minimal shell: cream background, Vocify `Logo`, title “Admin”, **Lock** button that `clearStoredAdminMasterKey()` and reloads `/admin`. If `getStoredAdminMasterKey()` is null, render an unlock form (input `type="password"`, submit sets the key and `navigate(0)` or local state `unlocked`). Validate by calling `adminApi.runtime()`; on 401 clear key and show “Invalid master key”; on 503 show “Admin is not configured”. Do not put the key in source.

- [ ] **Step 2: Accounts page**

TanStack Query `adminKeys.accounts(skip, search)` → `adminApi.listAccounts`. Table columns from the spec. Search input with debounce 300ms. Pagination using `total`. **Login as** button per row (wire the click in Task 8; for now the handler can be a prop `onLoginAs(id)` passed from a hook that Task 8 fills — or call the Task 8 helper if it already exists). Runtime strip from `adminApi.runtime()`. Stuck memos: query `stuckMemos`, show count, Recover button → `recoverStuckMemos` + invalidate.

Row click → `/admin/accounts/${id}`.

- [ ] **Step 3: Detail page**

`useParams().userId` → `adminApi.getAccount`. Sections: profile, each CRM connection + configuration, recent memos (link to `/dashboard/memos/:id` is **wrong while not impersonating** — show memo id/status only, no customer-route link). **Login as** button. Back link to `/admin`.

- [ ] **Step 4: Register routes in `src/App.tsx`**

Inside `<Routes>`, next to `/login`:

```tsx
<Route path="/admin" element={<AdminLayout />}>
  <Route index element={<AdminAccountsPage />} />
  <Route path="accounts/:userId" element={<AdminAccountDetailPage />} />
</Route>
```

`AdminLayout` uses `<Outlet />` for children after unlock.

Do not wrap with `ProtectedRoute` (that is customer JWT).

- [ ] **Step 5: Build**

Run: `npm run build`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/components/admin/AdminLayout.tsx src/pages/admin/AdminAccountsPage.tsx src/pages/admin/AdminAccountDetailPage.tsx src/App.tsx
git commit -m "$(cat <<'EOF'
feat(admin): add accounts console UI behind master-key unlock

EOF
)"
```

---

### Task 8: Login as + Return to admin banner

**Files:**
- Create: `src/components/admin/ImpersonationBanner.tsx`
- Modify: `src/pages/admin/AdminAccountsPage.tsx`
- Modify: `src/pages/admin/AdminAccountDetailPage.tsx`
- Modify: `src/components/dashboard/DashboardLayout.tsx`
- Modify: `src/features/auth/context.tsx` only if logout must be intercepted — prefer handling in the layout, not auth core.

**Interfaces:**
- Consumes: `adminApi.impersonate`, `saveCustomerSessionForReturn`, `setImpersonation`, `restoreCustomerSessionAfterImpersonation`, `api.setToken`
- Produces: full page load into `/dashboard` as the target user; banner to return

- [ ] **Step 1: Shared `loginAsAccount` helper**

Put in `src/lib/admin-impersonation.ts`:

```ts
export async function loginAsAccount(args: {
  accountId: string;
  email: string;
  fullName: string | null;
  impersonate: (id: string) => Promise<{ accessToken: string; refreshToken: string }>;
}): Promise<void> {
  const session = await args.impersonate(args.accountId);
  saveCustomerSessionForReturn();
  setImpersonation({
    accountId: args.accountId,
    email: args.email,
    fullName: args.fullName,
    startedAt: new Date().toISOString(),
  });
  localStorage.setItem("vocify_token", session.accessToken);
  localStorage.setItem("vocify_refresh", session.refreshToken);
  window.location.assign("/dashboard");
}

export function returnToAdmin(): void {
  restoreCustomerSessionAfterImpersonation();
  window.location.assign("/admin");
}
```

Add a test that `loginAsAccount` writes impersonation meta and token keys (mock `impersonate`, stub `window.location.assign`).

- [ ] **Step 2: Wire buttons**

List + detail **Login as** call `loginAsAccount({ ..., impersonate: async (id) => { const raw = await adminApi.impersonate(id); return { accessToken: raw.accessToken, refreshToken: raw.refreshToken }; } })`.

- [ ] **Step 3: Banner**

`ImpersonationBanner`: if `getImpersonation()` is null, return null. Else a full-width bar above the dashboard header: “Viewing as {email}” + button “Return to admin” → `returnToAdmin()`.

In `DashboardLayout`, render `<ImpersonationBanner />` at the top of the shell. If impersonating, the sidebar Logout button should call `returnToAdmin()` instead of `logout()`.

- [ ] **Step 4: Verify tests + build**

Run: `node --test src/lib/admin-auth.test.ts src/lib/admin-impersonation.test.ts`

Run: `npm run build`

Expected: both PASS.

- [ ] **Step 5: Manual check (when `MASTER_KEY` is in backend `.env`)**

1. Open `http://localhost:8080/admin` (or 5173 — whatever `start.js` prints). Unlock with the key.
2. See at least your own account (email, CRM, memo counts).
3. Open detail: STT languages, HubSpot allowlists, recent memos.
4. Login as → lands on `/dashboard` as that user; banner visible.
5. Return to admin → `/admin` still unlocked (master key session intact).
6. `curl -X POST http://localhost:8888/health/recover-stuck-memos` without header → 401/503. With `X-Master-Key` → 200.

- [ ] **Step 6: Commit**

```bash
git add src/lib/admin-impersonation.ts src/lib/admin-impersonation.test.ts src/components/admin/ImpersonationBanner.tsx src/pages/admin/AdminAccountsPage.tsx src/pages/admin/AdminAccountDetailPage.tsx src/components/dashboard/DashboardLayout.tsx
git commit -m "$(cat <<'EOF'
feat(admin): impersonate accounts and return to the staff console

EOF
)"
```

---

## Spec coverage

| Spec section | Task |
|--------------|------|
| Master key compare / 503 / 401 | Task 1 |
| Mint session / impersonate API | Tasks 2, 4 |
| Account list/detail data | Tasks 3, 4 |
| Gate `/health/recover-stuck-memos` | Task 4 |
| Runtime + stuck memos | Tasks 4, 7 |
| Audit log | Task 4 |
| Frontend key storage | Task 5 |
| Skip JWT refresh on `/admin` | Task 6 |
| UI unlock/list/detail | Task 7 |
| Login as + banner | Task 8 |
| No hardcoded key | Tasks 1, 5, 7 |
| Landwork / debug agent | Explicitly omitted |
