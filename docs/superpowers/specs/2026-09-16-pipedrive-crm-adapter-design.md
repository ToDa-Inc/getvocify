# Pipedrive CRM adapter — design spec

**Date:** 2026-09-16 (revised 2026-09-17)  
**Status:** Ready for implementation plan (Phase 0+1). Phase 2/3 stay deferred.  
**Repos:** getvocify  
**Baseline:** HubSpot (full product). Salesforce is the only existing second-CRM adapter.

Every Pipedrive fact is from Pipedrive’s published developer docs ([Sources](#sources)). If a mapping is not documented on both sides, it is **cannot adapt**, **fail-loud**, or **unknown — do not implement**. Locked decisions below override earlier wording in this file when they conflict.

---

## Decision (recommended)

Do **not** invent a new CRM framework. Add Pipedrive the same way Salesforce was added:

1. `PipedriveClient` + focused services (oauth, search, schema, matching, preview, sync, notes, activities, call_logs).
2. `PipedriveCRMProvider` implementing the existing `crm_providers` protocols.
3. One factory branch. Memo / WhatsApp / approve keep calling `build_crm_provider`.
4. Provider-specific REST under `/api/v1/crm/pipedrive/*`, mirroring `crm_salesforce.py`.
5. Where Pipedrive has no documented analogue, **fail loud** with a stable `error_code` (Salesforce pattern). Never silent-skip a write the preview promised (preview must not promise skipped work).

Do **not** expand the protocol surface in Phase 1. Do **not** request `admin`. Do **not** claim Chrome-extension or inbound-recording parity.

---

## Locked contract (do not reopen while implementing)

These close every “pick at implementation” / internal contradiction from the draft review. If a later section disagrees, this table wins.

| Topic | Lock |
|-------|------|
| Architecture | **C** (Salesforce folder + existing protocols). Not A, not B. |
| First ship | **Phase 0 + Phase 1 in the same release.** Do not ship a Settings card that fallthrough-searches HubSpot. |
| Phase 1 writes | Org, person, deal, note, next-step activities (if a type exists). Identity + skip_deal. No CallLogs, no owner stamp, no deal products, no `hubspot_*` writes, no webhooks, no Chrome. |
| Phase 2 | Vocify outbound → CallLogs + recording. New spec not required if this file’s Phase 2 table is followed; do not start it in the Phase 1 plan. |
| Scopes Phase 1 | `deals:full`, `contacts:full`, `activities:full`, `search:read`, `users:read`. **No** `phone-integration`, **no** `admin`. Re-consent in Phase 2 when adding `phone-integration`. |
| `deal_url` | **Omit** in Phase 1. `MemoDetail` already hides the link when `deal_url` is missing. Do not invent `{api_domain}/deal/{id}`. |
| Persist ids | Write Pipedrive deal id to `memos.matched_deal_id` (generic column; `memos.py` already does this on approve). Person/org ids: `SyncResult.contact_id` / `company_id` + `crm_updates` only. **Never** write Pipedrive ids into `hubspot_deal_id` / `hubspot_contact_id` / `hubspot_engagement_id`. |
| Identity return | Build `IdentityResolution` + `ContactAnchor` from `hubspot/contact_identity.py` (same dataclasses WhatsApp/preview already consume). `contact_id` = str(Pipedrive person id). Do not invent a third DTO. Do not refactor that module out in Phase 1. |
| Identity cascade | Same as HubSpot: (1) preferred id (2) real email auto-lock (3) phone auto-lock if exactly one (4) name → candidates only (5) company-only → no silent person lock. Reuse `is_real_contact_email` / `real_contact_email_or_none`. |
| `CRMSchema.object_type` | API/DTO literals only: `deals` \| `contacts` \| `companies`. Cache `crm_schemas.object_type` with those same strings (not `deal`/`person`/`organization`, not `Opportunity`). |
| `ProposedUpdate.object_type` | `deals` / `contacts` / `companies` / `task`. Person fields → `contacts`, org → `companies`. |
| Extraction snapshot | Phase 1: if `matched_deal_id` set, `GET /api/v2/deals/{id}` for allowlisted keys. Else `{}`. Same weakness as Salesforce when no id yet — not a wrong write. |
| Call outcomes Phase 1 | `CallOutcomeAvailability(converted=False, on_hold=False, lost=False)`. Any `call_outcome` on approve → `CALL_OUTCOME_UNSUPPORTED`. Matches Salesforce **and** PAYPER notes (do not treat Converted/On Hold/Lost as call-outcome buttons). Do **not** write `status=lost` in Phase 1. |
| Next-step activities | Discover `GET /api/v1/activityTypes`. Prefer `key_string == "task"`, else `icon_key == "task"`. If none: `tasks_warning`, sync still succeeds. Never use Projects **Tasks** API. |
| Owner | Phase 1: do not set `owner_id` (Salesforce). Pipedrive defaults to the installing user. |
| Line items | Ignore. Preview warning. Sync succeeds. |
| New deal `title` | `companyName` if set, else `contactName`, else `Vocify memo {YYYY-MM-DD}`. Do not invent marketing copy. |
| Amount / close | `dealAmount` → `value`; `dealCurrency` → `currency`; `closeDate` → `expected_close_date`. |
| Spoken stage | Match `dealStage` to a stage **label** in the configured pipeline (casefold). No match → keep `default_stage_id`. Do not create stages. |
| Person create | Requires `name` (`POST /persons`). Email/phone only → no create, warning. Emails/phones: official v2 arrays (`value`, `primary`, label). Confirm key names against first live `personFields` / GET person; if they differ, use live keys and document in the PR, do not guess a third shape. |
| Search `q` | Trim. If length < 2: return `[]`, do not call Pipedrive (min 2 chars unless `exact_match`). |
| Token TTL | `token_expires_at = now + expires_in` from the token JSON. Never hardcode 60 minutes. |
| Partial failure | No rollback (Pipedrive has none; HubSpot/SF don’t either). `success=False`; `crm_updates` records what landed; retry rematches. |
| `create_note=false` | Honor it. No Note. |
| WhatsApp | Processor already uses `build_crm_provider`. Phase 1 change: `_crm_display_name` must return `"Pipedrive"` when `provider=="pipedrive"` (today it says `"CRM"`). Token refresh stays inside `PipedriveClient`. |
| Files we may touch besides `pipedrive/` | `factory.py`, `api/router.py`, `src/lib/api/crm.ts` (provider switch, no HubSpot fallthrough), `SettingsPage.tsx`, `extraction_context.py` (optional GET-by-id), `whatsapp/processor.py` display name only. **No** HubSpot service behavior changes. |
| Telephony Phase 1 | Unchanged. Pipedrive-primary companies do not get CRM call logging until Phase 2. `attach_hubspot_contact_by_phone` must not run when resolved CRM is not HubSpot — if that function is reached for a Pipedrive-only company it already no-ops/warns on missing HubSpot connection; do not teach it Pipedrive in Phase 1. |
| CallLog `outcome` (Phase 2 only) | Map Vocify `call_disposition` → Pipedrive enum **only** where both exist: `connected`→`connected`, `busy`→`busy`, `no_answer`→`no_answer`, `voicemail`→`left_voicemail`. `failed` / `canceled` / unknown → **no CallLog** (write a Note). Do not map failed→busy. |
| Marketplace ops (not code) | Register a Pipedrive app. Callback URL === `PIPEDRIVE_REDIRECT_URI`. Phase 1 scopes only. |

---

## Phase 1 acceptance (definition of done)

All of these must be true before calling Phase 1 done. Not “and also CallLogs.”

1. HubSpot and Salesforce connect / preview / approve tests still pass unchanged.
2. `build_crm_provider` for `pipedrive` returns `PipedriveCRMProvider`; unknown provider still 501.
3. Settings: connect OAuth → `crm_connections` row `provider=pipedrive`, `metadata.api_domain` set, unique `(company_id, provider)`.
4. Configure pipeline + stage + allowlists; new deal create fails with `PIPEDRIVE_STAGE_REQUIRED` if those ids are missing.
5. Preview + approve: create/update person (when named), org, deal; one Note attached to every id we have; WhatsApp confirm uses the same `approve_memo_core`.
6. `skip_deal`: person + note, zero `POST /deals`.
7. Converted/On Hold/Lost buttons off; sending `call_outcome` errors.
8. `searchCrmDeals` / `searchContacts` with primary Pipedrive hit `/crm/pipedrive/search/*`, never HubSpot.
9. Chrome extension on a HubSpot tab still uses HubSpot routes if HubSpot is also connected.
10. No Pipedrive id in any `hubspot_*` column.
11. `deal_url` is null; memo page does not show a broken “view in CRM” link.

---

## What “no breaking paths” means

HubSpot and Salesforce users must keep the same routes, payloads, and outcomes they have today.

| Rule | How |
|------|-----|
| Existing factory keys unchanged | `build_crm_provider` still returns HubSpot / Salesforce for those `provider` strings. Pipedrive is a new `if`. |
| Memo APIs stay provider-agnostic | `POST /memos/{id}/preview`, `/match`, `/approve` already go through the factory. Pipedrive rides that. No new memo routes. |
| HubSpot-direct routes stay HubSpot-direct | `/crm/hubspot/*`, `/webhooks/hubspot`, recordings, calling settings. Pipedrive does not reuse them. |
| Multi-CRM already fail-loud | `AmbiguousPrimaryCRMError` when 2+ connected and no primary. Pipedrive as a third connected CRM uses the same rule. |
| Unsupported writes fail-loud | Phase 1: `CALL_OUTCOME_UNSUPPORTED`, `PIPEDRIVE_STAGE_REQUIRED`, `PIPEDRIVE_AUTH_EXPIRED`. Do **not** emit `SKIP_DEAL_UNSUPPORTED` (skip_deal is supported). Never return `success=True` after dropping a promised write. |
| Search routing | `crmApi.searchCrmDeals` branches Salesforce vs **defaults to HubSpot**. A Pipedrive-primary company today would query HubSpot. Enabling the Settings card without a Pipedrive branch is a break. Contact search and the Chrome extension are HubSpot-only. |
| Column names | See locked contract: `matched_deal_id` + `SyncResult` / `crm_updates` only. No Pipedrive ids in `hubspot_*`. HubSpot-direct routes stay HubSpot ids. |

A Pipedrive row in `crm_connections` is already allowed by the DB CHECK (`'hubspot' | 'salesforce' | 'pipedrive'`). Today `build_crm_provider` raises `UnsupportedCRMProviderError` → HTTP 501. That is the correct current behavior. Implementing the adapter replaces 501 with real work; leaving the provider unregistered is safer than a half-wired path.

---

## Sources

### Pipedrive (official)

- OAuth: https://pipedrive.readme.io/docs/marketplace-oauth-authorization
- Scopes: https://pipedrive.readme.io/docs/marketplace-scopes-and-permissions-explanations
- Rate limits: https://pipedrive.readme.io/docs/core-api-concepts-rate-limiting
- API v2 overview: https://pipedrive.readme.io/docs/pipedrive-api-v2
- About the API / activities vs call logs: https://pipedrive.readme.io/docs/core-api-concepts-about-pipedrive-api
- Webhooks: https://pipedrive.readme.io/docs/guide-for-webhooks
- Deals: https://developers.pipedrive.com/docs/api/v1/Deals
- Persons: https://developers.pipedrive.com/docs/api/v1/Persons
- Organizations: https://developers.pipedrive.com/docs/api/v1/Organizations
- Notes: https://developers.pipedrive.com/docs/api/v1/Notes
- Activities: https://developers.pipedrive.com/docs/api/v1/Activities
- Activity types: https://developers.pipedrive.com/docs/api/v1/ActivityTypes
- Call logs: https://developers.pipedrive.com/docs/api/v1/CallLogs
- Deal products: https://developers.pipedrive.com/docs/api/v1/DealProducts
- Deal fields: https://developers.pipedrive.com/docs/api/v1/DealFields
- Item search: https://developers.pipedrive.com/docs/api/v1/ItemSearch
- Pipelines: https://developers.pipedrive.com/docs/api/v1/Pipelines
- Stages: https://developers.pipedrive.com/docs/api/v1/Stages
- Files: https://developers.pipedrive.com/docs/api/v1/Files
- Users: https://developers.pipedrive.com/docs/api/v1/Users
- Channels (messaging, not phone): https://developers.pipedrive.com/docs/api/v1/Channels
- CallLogs OAuth scope changelog: https://developers.pipedrive.com/changelog/post/phone-calls-integration-oauth-scope

### Vocify (this repo)

- Protocols: `backend/app/services/crm_providers/protocols.py`
- Factory: `backend/app/services/crm_providers/factory.py`
- HubSpot / Salesforce facades: `*_provider.py`
- Salesforce as the second-adapter playbook: `backend/app/services/salesforce/`
- Approve path: `backend/app/services/memo_approval.py`
- Config: `backend/app/services/crm_config.py`, `backend/app/models/crm_config.py`
- WhatsApp: `backend/app/services/whatsapp/processor.py`
- HubSpot-direct leftovers: `backend/app/api/crm.py`, `hubspot/call_processor.py`, `hubspot/call_log.py`, `telephony/call_processor.py`
- Settings: `src/pages/dashboard/SettingsPage.tsx` (HubSpot + Salesforce only)
- Chrome extension: `chrome-extension/` (`https://*.hubspot.com/*` only)

### Meetings (product intent, not API)

PAYPER / Pipedrive pilot notes: transcribe → map fields → WhatsApp confirm → write after accept; prefer a **call activity** with summary/transcript over a duplicate note; associate contact + company + deal. [[0]](https://notes.granola.ai)

Meetings do not define endpoints. Where a meeting wish has no Pipedrive API, the spec says so.

---

## Vocify surfaces to cover

These are the actions Vocify actually performs today. Salesforce column is the existing “second CRM” bar.

| # | Surface | HubSpot | Salesforce | Through `crm_providers`? |
|---|---------|---------|------------|--------------------------|
| 1 | OAuth connect / callback / disconnect / test | Yes (+ private-app PAT) | Yes (OAuth only) | No — per-CRM routes |
| 2 | Token refresh | Yes | Yes (inside client) | Partial |
| 3 | Primary CRM + connections list | Shared | Shared | Shared |
| 4 | Configuration (pipeline, stage, allowlists, auto-create) | Full 4 objects + call-outcome maps | Opportunity + stage only | Config stored shared; consumed by protocol |
| 5 | Schema → LLM field specs | Deal, contact, company, line item | Opportunity only | Yes |
| 6 | Existing CRM values into extraction | HubSpot only | Missing (`{}`) | No (`extraction_context.py`) |
| 7 | Deal match + manual search | Yes | Yes | Match yes; search routes per-CRM |
| 8 | Contact / identity resolve | Yes | Stub `None` | Yes |
| 9 | Approval preview | Full | Deal diffs only | Yes |
| 10 | Approve / `sync_memo` | Deal, contact, company, line items, note, tasks, associations, owner, call outcome | Opp + auto Account/Contact; fail-loud skip_deal + call_outcome | Yes |
| 11 | WhatsApp confirm / retarget / approve | Uses provider | Same, degraded (no identity) | Yes |
| 12 | Vocify outbound call → CRM Call + recording | `log_call_to_hubspot` | None | No |
| 13 | Inbound CRM recording → transcribe | HubSpot webhook + call processor | None | No |
| 14 | Chrome extension on CRM page | HubSpot.com only | Broken if primary is SF | No |
| 15 | Owners | Email → `hubspot_owner_id` | None | Inside HS sync |
| 16 | Line items | Create + associate | Not implemented | Protocol args exist; SF deletes them |

`deal_lookup.py` is HubSpot-only and **not imported**. Ignore it.

---

## Approaches

### A — Salesforce-thin (deal fields only)

Implement OAuth + schema + match + preview + `sync_memo` for Deal / Person / Organization fields. Drop notes, activities, call logs, identity, skip_deal.

- Fastest.
- Contradicts PAYPER (call activity as the canonical record) and leaves WhatsApp contact-first broken the same way Salesforce is.
- Rejected for a Pipedrive pilot that is supposed to feel like HubSpot.

### B — New “CRM write bus” / generic object layer

Replace protocols with a generic object matcher + JSONB config (the old Phase 2/3 in `ARCHITECTURE_NOTES.md`).

- Speculative. One implementation would still be Pipedrive.
- Breaks the “don’t rewrite HubSpot/Salesforce to add a third” rule.
- Rejected (YAGNI, SOLID Open/Closed).

### C — Salesforce folder shape, HubSpot-complete protocol, Pipedrive-native writes (recommended)

Same package layout as `backend/app/services/salesforce/`. Provider implements **every** protocol method. Writes use Pipedrive objects that the docs actually have (Deal, Person, Organization, Note, Activity, CallLog). Fail-loud where the docs have no analogue (HubSpot lead-status outcomes, ad-hoc line items, inbound recording webhook, Chrome on pipedrive.com).

- No HubSpot/Salesforce behavior change.
- Matches how we already add a CRM.
- Uses Pipedrive CallLogs for phone (documented), not Channels (messaging).

**Choose C.**

---

## SOLID

| Letter | Application |
|--------|-------------|
| **S** | `PipedriveClient` = HTTP + 401 refresh. Search / schema / matching / preview / sync / notes / activities / call_logs are separate modules. Provider is a facade (copy HubSpot/Salesforce). |
| **O** | New CRM = new package + factory branch + `/crm/pipedrive` router. Do not change HubSpot *behavior*. Allowed non-Pipedrive edits: factory, router, `crm.ts` provider switch, Settings, WhatsApp display name, `extraction_context` GET-by-id. |
| **L** | Provider implements all protocol methods. Phase 1: call-outcome availability all false; `call_outcome` set → `CALL_OUTCOME_UNSUPPORTED`. Never `pass`. |
| **I** | Keep the five existing protocols. No `CRMRecordingProtocol`. Phase 2 telephony is a helper next to `log_call_to_hubspot`, not a new protocol. |
| **D** | `memo_approval`, `memo_crm`, WhatsApp depend on protocols + `build_crm_provider`. They must not import `app.services.pipedrive`. |

Do not “fix” HubSpot type leakage (`SyncResult` lives in `hubspot/types.py`) as a prerequisite. Salesforce already returns that type. Pipedrive does the same. A later rename is unrelated.

---

## Object analogies (documented only)

| Vocify / HubSpot concept | Salesforce (existing) | Pipedrive (docs) | Notes |
|--------------------------|----------------------|------------------|--------|
| Deal | Opportunity | **Deal** | `title`, `value`, `currency`, `pipeline_id`, `stage_id`, `status`, `expected_close_date`, `person_id`, `org_id`, `owner_id`, `lost_reason`, `custom_fields` |
| Contact | Contact | **Person** | `name`, `emails[]`, `phones[]`, `org_id`, `owner_id`, `custom_fields`. Persons ≠ Users. |
| Company | Account | **Organization** | `name`, `address`, `website`, `owner_id`, `custom_fields`. One org, many persons. |
| Pipeline + stage IDs | Flattened to `StageName` | **Pipeline + Stage** | `GET /api/v2/pipelines`, `GET /api/v2/stages?pipeline_id=`. Same shape as HubSpot config columns. |
| Deal owner | — | `owner_id` (Pipedrive **user** id) | `GET /api/v1/users/find?term=&search_by_email=1` |
| Note on deal/contact/company | Not implemented | **Note** (`POST /api/v1/notes`) | HTML `content`, max ~100k chars. One note may set `deal_id` **and** `person_id` **and** `org_id` together (each optional, at least one of deal/person/org/lead/project/task required). This is the documented way to make the note visible on all three. |
| Next-step Task | Not implemented | **Activity** with a type whose `key_string` is discovered via `GET /api/v1/activityTypes` | No documented guarantee of a `task` type. Resolve at runtime; if none, `tasks_warning` (not a failed sync). Projects **Tasks** API: do not use. |
| HubSpot Call engagement | — | **Call log** (`POST /api/v1/callLogs`) | Official: call logs “are also considered activities” but “only receive the information needed to describe the phone call.” Required: `outcome`, `to_phone_number`, `start_time`, `end_time`. Optional: `person_id`, `org_id`, `deal_id` **xor** `lead_id`, `note` (HTML), `duration` (seconds as string), `from_phone_number`, `user_id`. Recording: `POST /api/v1/callLogs/{id}/recordings` multipart `file` (HTML5 audio). Scope: `phone-integration`. |
| HubSpot Call `hs_call_status` / duration | — | CallLog `outcome` enum | Pipedrive values: `connected`, `no_answer`, `left_message`, `left_voicemail`, `wrong_number`, `busy`. **These are phone-connect outcomes, not sales outcomes.** |
| Vocify `call_outcome` Converted / On Hold / Lost | Fail-loud | See [Call outcomes](#call-outcomes-converted--on-hold--lost) | Lost has a deal-level analogue. Converted / On Hold do not. |
| Line item | — | **Deal product** | `POST /api/v2/deals/{id}/products` requires existing `product_id`, `item_price`, `quantity`. Not a freeform line item. |
| Product catalog | HubSpot products | `GET /api/v2/products/search` | Needed only if we attach deal products. |
| Lead inbox | HubSpot lead status on **contact** | Pipedrive **Lead** (separate object, UUID) | Not the same thing. Vocify does not sync HubSpot Leads today. Do not map memos to Pipedrive Leads in v1. |
| Messaging inbox | — | **Channels** API | Messaging app extension (WhatsApp-in-Pipedrive). Deprecated endpoints. **Not** a phone/CRM-sync path. Out of scope. |
| File / recording attachment | HubSpot engagement recording | CallLog recordings **or** `POST /api/v1/files` | Files can attach to deal, person, org, activity, lead, product. Call recording playback in Pipedrive is documented on CallLogs, not Files. Prefer CallLogs for phone. |
| Search | HS search API | `GET /api/v2/itemSearch` and wrappers `/deals/search`, `/persons/search`, `/organizations/search` | Term min 2 chars (1 if `exact_match`). Person fields include `phone`, `email`, `name`. Deal fields: `title`, `notes`, `custom_fields`. Searchable custom types only: `address`, `varchar`, `text`, `varchar_auto`, `double`, `monetary`, `phone`. |
| Schema | Property API | `GET /api/v2/dealFields`, `personFields`, `organizationFields` | Custom keys are **40-character hashes**. v2 deal/person/org writes put them in `custom_fields`. Monetary/daterange/timerange have a sibling key (`{hash}_currency`, etc.). `include_fields=required_fields` describes **web UI** required-at-stage rules, not API rejection. |
| Current user / company domain | Portal id | `GET /api/v1/users/me` + OAuth `api_domain` | `api_domain` is the request base URL. |

Deal `status` (docs): **open | won | lost**. `lost_reason` “can only be set if deal status is lost.”

---

## API version policy

Pipedrive is migrating to v2. v2 is not backward compatible with v1. Official v2 coverage includes Activities, Deals, Deal products, Fields (deal/person/org/product/activity), Organizations, Persons, Products, Pipelines, Stages, Search.

**Use v2** for those resources.

**Use v1** only where v2 is not published: Notes, CallLogs, Files, Users, ActivityTypes, Webhooks, OAuth.

Client base: `{api_domain}/api/v2/...` or `{api_domain}/api/v1/...` with `Authorization: Bearer {access_token}`.

---

## OAuth and connection

Mirror Salesforce (Marketplace OAuth only). Do not add a Pipedrive personal API-token paste unless a later decision asks for it. HubSpot’s private-app PAT is HubSpot-specific.

### Flow (docs)

1. `GET https://oauth.pipedrive.com/oauth/authorize?client_id=&redirect_uri=&state=`
2. Callback: `code` or `error=user_denied`. `code` expires in **5 minutes**.
3. `POST https://oauth.pipedrive.com/oauth/token`  
   - Header: `Authorization: Basic base64(client_id:client_secret)`  
   - Body (`application/x-www-form-urlencoded`): `grant_type=authorization_code`, `code`, `redirect_uri`
4. Store `access_token`, `refresh_token`, `expires_in`, `api_domain`, `scope`.
5. Refresh: same token URL, `grant_type=refresh_token`. Persist `expires_in` from the **response** (docs contradict themselves: prose says ~60 minutes, example JSON shows `7200`). Never hardcode TTL. Refresh token idle expiry is **60 days**; unused refresh → user reinstalls.
6. Token length: Pipedrive recommends **minimum varchar(768)**. Our `crm_connections.access_token` / `refresh_token` are `TEXT` — sufficient.

Sign `state` with existing `JWT_SECRET` (same as HubSpot/Salesforce) so the callback cannot bind another company’s connection.

### Metadata to persist

```json
{
  "api_domain": "https://example.pipedrive.com",
  "company_domain": "example",
  "pipedrive_user_id": 123,
  "pipedrive_company_id": 456,
  "user_email": "...",
  "user_name": "...",
  "scope": "..."
}
```

`company_domain` is already on the frontend `CRMConnectionMetadata` type. Prefer `api_domain` for requests (that is what the token response gives).

After exchange, call `GET /api/v1/users/me` to fill user/company fields (documented for this purpose).

### Env

`PIPEDRIVE_CLIENT_ID`, `PIPEDRIVE_CLIENT_SECRET`, `PIPEDRIVE_REDIRECT_URI`.

Do not enable the Settings card if these are unset (Salesforce `salesforce_oauth_enabled()` pattern).

### Scopes (request only what v1 uses)

From the official scope list:

| Scope | Why |
|-------|-----|
| `deals:full` | Create/update deals, notes, files. Read deal fields, pipelines, stages. |
| `contacts:full` | Create/update persons and organizations, notes, files. |
| `activities:full` | Create/update activities (next steps). |
| `search:read` | `itemSearch` / persons/deals/orgs search. |
| `users:read` | `users/me`, `users/find` for owner mapping. |
| `phone-integration` | CallLogs + recordings. **Phase 2 only** (re-consent). Do not request in Phase 1. |

**Do not request `admin` in v1.** Admin is required to create pipelines/stages/fields and to **create webhooks via API**. Non-admin installs fail or degrade. v1 does not create fields or webhooks.

`deals:full` / `contacts:full` do **not** include activity write (except last/next activity on a deal). That is why `activities:full` is required for next-step activities.

### Routes

Mirror Salesforce:

- `GET /api/v1/crm/pipedrive/authorize`
- `GET /api/v1/crm/pipedrive/callback` (redirect to Settings `?pipedrive=connected` / `error`)
- `GET /api/v1/crm/pipedrive/connection`
- `POST /api/v1/crm/pipedrive/test` → `GET /users/me` + `GET /api/v2/dealFields?limit=1`
- `DELETE /api/v1/crm/pipedrive/disconnect` (clear primary if this row was primary)
- `GET/POST /api/v1/crm/pipedrive/configuration` (shared `CRMConfigurationService`)
- `GET /api/v1/crm/pipedrive/schema`
- `GET /api/v1/crm/pipedrive/pipelines` + `/stages`
- `GET /api/v1/crm/pipedrive/search/deals?q=`
- `GET /api/v1/crm/pipedrive/search/persons?q=`
- `GET /api/v1/crm/pipedrive/search/organizations?q=`

Frontend: add Pipedrive to `SettingsPage` `LIVE` list and `crm.ts` the same way Salesforce was added. Flip `CRM_PROVIDER_CONFIGS.pipedrive.available` to `true` only when OAuth env is documented as required for that deploy.

---

## Client, refresh, rate limits

`PipedriveClient`:

- Holds `api_domain`, access/refresh tokens, `connection_id`, supabase.
- On 401: refresh once, persist **both** tokens + `token_expires_at`, retry once.
- On 429: read `x-ratelimit-reset`; backoff; surface `PIPEDRIVE_RATE_LIMITED` to the user. Do not busy-loop.
- Prefer v2 costs (officially lower).

Official limits:

- Daily **token budget** per company: `30000 × plan multiplier × seats` (Lite 1, Growth 2, Premium 5, Ultimate 7). Reset midnight **server** TZ.
- Example costs (reference table): get-one ~2, list ~20, update ~10, search ~40. Actual cost is per-endpoint in the API reference (CallLog create = 10, attach recording = 10, v2 activity create = 5, v2 itemSearch = 20).
- Burst (OAuth apps, per token, 2s window): Lite 80, Growth 160, Premium 400, Ultimate 480.
- Search burst: **10 / 2s** on every plan.
- Headers: `x-ratelimit-limit`, `x-ratelimit-remaining`, `x-ratelimit-reset`.
- Persistent 429 abuse on `api_token` can become Cloudflare 403. OAuth apps still must back off.

Memo sync is a handful of writes. Burst is the real risk if matching does N+1 searches. Matching must batch: one person search, one org search, then `GET /api/v2/deals?person_id=` / `?org_id=` (documented deal list filters).

---

## Schema and field allowlists

### Fetch

- `GET /api/v2/dealFields?include_fields=required_fields,important_fields`
- `GET /api/v2/personFields`
- `GET /api/v2/organizationFields`
- Cache in `crm_schemas` with `object_type` `deals` / `contacts` / `companies` (matches `CRMSchema` literals).

### Map into existing `HubSpotProperty`-shaped `CRMSchema`

Salesforce already does this. Keep the DTO so Settings / preview do not fork.

| Pipedrive `field_type` | Vocify `CRMFieldType` / HubSpotProperty.type |
|------------------------|-----------------------------------------------|
| `varchar`, `varchar_auto`, `phone` | `string` |
| `text` | `string` + fieldType textarea |
| `double` | `number` |
| `monetary` | `number` (document currency sibling; do not invent currency writes unless the allowlist includes `{key}_currency`) |
| `date` | `date` |
| `daterange`, `timerange`, `time` | expose as string; **do not** claim we can fill ranges until a real extraction needs them |
| `enum` | `select` / enumeration |
| `set` | `multiselect` |
| `user`, `org`, `people`, `address` | show in schema; v1 allowlist **default excludes** them (IDs, not spoken values) |

System deal fields to offer in the allowlist (keys are the **API field names**, not hashes): `title`, `value`, `currency`, `expected_close_date`, `pipeline_id`, `stage_id`, `status`, `lost_reason`, `probability`. Default allowlist for a new Pipedrive config: `title`, `value`, `expected_close_date` (analogous to HubSpot `dealname`, `amount`, `closedate`). Do **not** default-allow `status` or `lost_reason` — those are outcome writes.

Person defaults: `name`, emails, phones (internal keys as returned by personFields — use the documented field keys from the live schema, do not hardcode HubSpot `firstname`).

Organization defaults: `name`.

### Custom fields

- Allowlist stores the **hash key** (and system key).
- v2 write body: `{ "title": "...", "custom_fields": { "<hash>": value } }`.
- Clear: `null`. For `set`, docs forbid `[]` — use `null`.
- Enum/set: write the **option id** Pipedrive returns, not the label. Preview must show label; sync writes id.
- Searchable custom types only (if we search by field): listed above. Other types are write-only via id.

### Required-at-stage (PAYPER)

DealFields `required_fields` is documented as **web UI** mandatory. The API does not say it rejects incomplete deals.

v1 behavior:

- Preview lists configured-required fields that are empty after the proposed write (read `required_fields.stage_ids` / `statuses` from schema).
- Sync does **not** invent an API pre-check that Pipedrive does not document.
- Do not create Pipedrive fields (`POST /dealFields` needs admin). Mapping is onto **existing** fields only.

### LLM specs

`get_extraction_field_specs` returns deal + person + organization allowlists (HubSpot-complete, unlike Salesforce). Line-item specs: **omit** in v1 (see line items).

`extraction_context.load_existing_crm_values` today returns `{}` unless HubSpot. Phase 1: if `matched_deal_id` is set, GET that deal’s allowlisted fields. Otherwise `{}`.

---

## Matching and identity

Prefer phone, then email, then name (product + meetings). Implement with documented search fields.

### Person

`GET /api/v2/persons/search?term={phone_or_email_or_name}&fields=phone,email,name`

- Phone: pass the digits we already normalize for HubSpot telephony. Term minimum 2 characters.
- If multiple persons, return candidates (HubSpot identity), do not pick silently.

### Organization

`GET /api/v2/organizations/search?term={company_name}&fields=name`

### Deals for a person/org

`GET /api/v2/deals?person_id=` and/or `?org_id=` and/or `?pipeline_id=` (list filters are documented). **Omit `status`** on list (docs: omitted → all not-deleted). Do not send `status=open` on list.

Manual picker: `GET /api/v2/deals/search?term=` (wrapper of itemSearch; can filter `person_id` / `org_id`).

### Identity protocol

Implement `resolve_contact_anchor` / `resolve_identity` (do **not** stub like Salesforce). Return the same structures HubSpot matching already returns so WhatsApp / preview contact-first keep working.

`skip_deal`: supported. Sync person (± org) + note/activity/call-log without creating a deal. Pipedrive notes and call logs do not require a deal.

---

## Preview

`build_preview` must show every write `sync_memo` will attempt:

- Person create/update diffs (allowed person fields)
- Organization create/update diffs
- Deal create/update diffs (allowed deal fields + default pipeline/stage on create)
- Note: yes/no + which of deal/person/org it will attach to
- Next-step activities: subject, due, type key
- Call log: **Phase 2 only**. Phase 1 preview never promises a CallLog.
- Line items: preview warning “not written”; sync ignores them.

Reuse `ApprovalPreview`. Do not add Pipedrive-only preview fields the UI cannot render. `HubSpotSyncPreview.tsx` is already the generic preview (name is leftover).

---

## `sync_memo` write contract

Order (same as HubSpot/Salesforce: org → person → deal → associations → note / activities → outcomes):

1. **Organization** — find or create if `auto_create_companies` and we have a name. `POST /api/v2/organizations` requires `name`.
2. **Person** — find or create if `auto_create_contacts` and we have a **name** (docs: `name` required on create). Email/phone-only with no name → do **not** invent a name; skip create and surface a preview/sync warning. Set `org_id` when we have an org. Emails/phones as arrays with `primary` flags (field shapes from live `personFields`, not guessed).
3. **Deal** — unless `skip_deal`.  
   - Update: `PATCH /api/v2/deals/{id}` with allowlisted system fields + `custom_fields`.  
   - Create: `POST /api/v2/deals` with required `title`, `pipeline_id` / `stage_id` from config, `person_id`, `org_id`.  
   - New deals: a deal “must be placed in a stage” (Deals docs). Config `default_pipeline_id` + `default_stage_id` are required before create (same as HubSpot).
4. **Participant** — if the person is not already the deal’s `person_id`, `POST /api/v1/deals/{id}/participants` with `person_id` (documented).
5. **Note** — if `create_note` and we have transcript/summary. One `POST /api/v1/notes` with HTML `content`. Do **not** call `format_hubspot_note_body` as-is (`hubspot_call`, `hs_lead_status`, `hubspot_owner_id` skips). Share only the generic HTML escape/markdown bits, or fork a Pipedrive formatter. Attach all of `deal_id` / `person_id` / `org_id` that exist.
6. **Next-step activities** — for each extracted next step: `POST /api/v2/activities` with `subject`, `type` (resolved key), `due_date` / `due_time` if present, `deal_id` / `org_id`, `participants: [{person_id, primary: true}]`. `done: false`. If `GET /activityTypes` has no usable next-step type: set `SyncResult.tasks_warning` (HubSpot already treats task failure as non-blocking). **Do not** fail the whole memo (`NEXT_STEP_ACTIVITY_TYPE_MISSING` is a warning, not a sync error).
7. **Owner** — Phase 1: skip (see locked contract).
8. **Call outcome** — Phase 1: reject if present (`CALL_OUTCOME_UNSUPPORTED`).
9. **Audit** — existing `CRMUpdatesService` action types: `upsert_company`, `upsert_contact`, `create_deal`, `update_deal`, `create_note`, `create_tasks`.

`SyncResult`: fill `contact_id`, `company_id`, `deal_id`, `deal_name`. Leave `deal_url` **null** (locked). After approve, persist deal id on `memos.matched_deal_id` only.

### What sync must not do

- Create Pipedrive **Leads**.
- `POST /dealFields` / create pipelines.
- Attach deal products. v1: **ignore** extracted line items (Salesforce already drops them). Preview warning only. Do **not** fail approve because the LLM emitted line items.
- Write `status=won` because Vocify said “Converted”.
- Create a CallLog for a voice memo that is not a phone call (missing `to_phone_number` / start / end).
- Use Channels API.

---

## Call outcomes (Converted / On Hold / Lost)

**Phase 1:** availability all false; any `call_outcome` → `CALL_OUTCOME_UNSUPPORTED`. Table below is for a later phase only — do not implement Lost→`status=lost` in Phase 1.

HubSpot maps these to `hs_lead_status` + dealstage + a lost-reason property. That model **does not exist** on Pipedrive persons.

| Vocify outcome | Pipedrive documented analogue | v1 behavior |
|----------------|------------------------------|-------------|
| **Lost** + `lost_reason` | Deal `status=lost` + `lost_reason` (only valid when status is lost) | `get_call_outcome_availability` has **no deal id** (protocol). Availability `lost=true` only if Pipedrive config opts into “write lost on deal”. At sync: if `call_outcome=lost` and there is no deal (`skip_deal` or none created) → `CALL_OUTCOME_UNSUPPORTED`. |
| **Converted** | None. Pipedrive Lead→Deal conversion is a different API (`/deals/{id}/convert/lead` is Deal→Lead, the opposite direction). | `get_call_outcome_availability().converted = false`. If payload sends `call_outcome=converted` → `CALL_OUTCOME_UNSUPPORTED`. |
| **On Hold** | None. | Same as Converted. |

Do **not** reuse CallLog `outcome` (`connected` / `no_answer` / …) for sales outcomes. Different vocabulary in the same product.

`lost_lead_status_value` / `on_hold_lead_status_value` / `lost_reason_deal_property` are HubSpot-specific config. Pipedrive provider ignores them. `lost_reasons` list can still feed the Lost picker; the write target is deal `lost_reason` (string), not a custom property hash, unless a later customer asks to map onto a custom enum (then store that hash in config — do not invent it now).

---

## Notes vs call activity (PAYPER)

Meetings: canonical record = **call activity** with summary/transcript; avoid a duplicate Vocify note.

Docs give two different objects:

1. **CallLog** — phone metadata + HTML `note` + optional recording. Associates person, org, and deal **or** lead.
2. **Note** — HTML on deal/person/org (any combination).
3. **Activity** `type=call` — general calendar activity; CallLog can **convert** an existing `call` activity via `activity_id`.

v1 rules (no guessing):

- **Vocify telephony call** (we have from/to, start, end): `POST /callLogs` with `outcome` derived only from telephony (answered → `connected`; no-answer / busy if our call record already has that meaning; if we do not store a connect result, use `connected` only when the call was answered — if unknown, **do not invent**; omit CallLog and write a Note). Put summary+transcript HTML in CallLog `note`. Associate person/org/deal. Then `POST /callLogs/{id}/recordings` when audio exists (HTML5-supported format we already produce).
- **Do not also create a Note** for that same call when CallLog.note was written (avoids the duplicate the meetings flagged).
- **Voice memo / WhatsApp audio with no phone times**: no CallLog (required fields `to_phone_number`, `start_time`, `end_time` would be fabricated). Write a **Note** attached to all available ids.
- Next steps are Activities, not Notes.

Official: associating an activity with a deal also associates it with the person/org on that deal. Still set person/org explicitly on CallLog when we have them (CallLog fields exist for that).

---

## Telephony (Vocify outbound)

Today `telephony/call_processor.py` writes HubSpot Call engagements and `hubspot_*` columns.

v1 Pipedrive path (behind primary/connection provider check, **not** a protocol):

- Phone match: `persons/search?fields=phone` (same as matching).
- After recording ready: CallLog + recording upload (above).
- Persist CallLog id on `SyncResult` / `crm_updates` / a Pipedrive-specific metadata key. Do **not** stuff it into `hubspot_engagement_id` by default (see column-names rule).
- `attach_hubspot_contact_by_phone` in `telephony/call_processor.py` **always** uses `HubSpotSearchService`. Pipedrive-primary (or Pipedrive-only) companies must not run that function — it would 409/skip or write a HubSpot contact id onto the call. Phase 2 replaces that lookup with `persons/search?fields=phone` when the resolved CRM is Pipedrive, and leaves the HubSpot function for HubSpot connections only.

HubSpot `calling_settings.register_recording_endpoint` has **no** documented Pipedrive equivalent. Vocify does not become a Pipedrive in-app dialer in v1.

---

## Inbound recordings / webhooks — cannot claim

HubSpot: `POST /webhooks/hubspot` on recording URL property → transcribe.

Pipedrive webhooks (official object list): `activity`, `activityType`, `deal`, `note`, `organization`, `person`, `pipeline`, `product`, `stage`, `user`. Actions: `added`, `deleted`, `merged`, `updated`. Creating webhooks via API needs **`admin`**.

CallLogs “are also considered activities”, but there is **no** documented event “recording attached” and **no** documented way to download a CallLog recording for transcription. Files download is documented (`GET /api/v1/files/{id}/download`). That is not the same as CallLog recordings.

**v1: do not subscribe to Pipedrive webhooks. Do not claim inbound Pipedrive-app call transcription.**

If a later phase wants it: prove with a tenant that `added.activity` fires for CallLogs and that audio is retrievable. General Webhooks API needs `admin`. Pipedrive also documents **app-specific Marketplace webhooks** — that page was **not** read for this spec; treat as unknown, not “admin-only.”

---

## Chrome extension — cannot adapt in this spec

Manifest is `https://*.hubspot.com/*`. Parsers, recordings inbox, search, and “view in CRM” are HubSpot URLs.

Pipedrive users will use: dashboard preview, WhatsApp confirm, voice memos. Extension-on-Pipedrive is a **new product surface** (content scripts on `*.pipedrive.com`, new parsers). Out of this adapter spec.

**No-break:** extension must keep using HubSpot routes when the page is HubSpot, even if the company also connected Pipedrive. Never send a HubSpot deal id to Pipedrive search.

---

## Line items

HubSpot: create line items from spoken name/qty/price.

Pipedrive: deal-product **requires** `product_id` from the Products catalog. Creating a Product per memo would pollute the catalog; the docs do not describe an ephemeral line item.

**v1: do not write deal products.** Preview must say they are skipped. If we later add this: `GET /api/v2/products/search?term=` then attach; if no match, fail-loud `PRODUCT_NOT_FOUND` — do not auto-`POST /products` without an explicit product decision.

---

## WhatsApp

Already provider-agnostic (`build_crm_provider`, `approve_memo_core`). Pipedrive works when:

- identity resolve is implemented (this spec),
- search routes exist for retarget,
- preview/sync honor `skip_deal`.

Processor already calls `build_crm_provider`. Phase 1: set `_crm_display_name("pipedrive")` → `"Pipedrive"`. No other WhatsApp CRM writes.

---

## Frontend

- Settings: third card, `PipedriveConnection` + `PipedriveConfiguration` (copy Salesforce layout: pipeline + stages from API, allowlists for deal/person/org, auto-create, auto-accept toggle). Hide HubSpot-only call-outcome mappers (`hs_lead_status`). Show Lost→deal status only.
- `crmApi.searchCrmDeals` / `searchContacts`: branch `pipedrive` → new routes. Today `searchContacts` is HubSpot-only — that is a **current Salesforce bug**; fix by provider switch, do not special-case Pipedrive only.
- Memo detail `labelsFromDealUrl`: add `pipedrive.com` host check next to HubSpot/Salesforce.
- `CRM_PROVIDERS.pipedrive.comingSoon`: remove when the card is live.

---

## Error codes (fail-loud)

| Code | When |
|------|------|
| `UnsupportedCRMProviderError` / 501 | Factory before this work (keep for unknown providers) |
| `PIPEDRIVE_OAUTH_DISABLED` | Env missing |
| `PIPEDRIVE_AUTH_EXPIRED` | Refresh failed (409, same copy style as HubSpot/Salesforce reconnect) |
| `PIPEDRIVE_RATE_LIMITED` | 429 after backoff |
| `CALL_OUTCOME_UNSUPPORTED` | Any `call_outcome` in Phase 1 |
| `NEXT_STEP_ACTIVITY_TYPE_MISSING` | Warning on `tasks_warning` only — not a failed sync |
| `PIPEDRIVE_STAGE_REQUIRED` | Creating a deal without configured pipeline/stage |

---

## What we will not pretend exists

| Claim | Reality |
|-------|---------|
| Pipedrive hs_lead_status | No such person field in the API |
| Channels = calling | Channels is messaging inbox |
| Tasks API = next steps | Unproven; use Activities after type discovery |
| Inbound recording webhook | Not documented for CallLog audio |
| Ad-hoc line items | Deal products need `product_id` |
| Required fields block API writes | Docs say web UI |
| Chrome on Pipedrive | Different origin, no parser |
| Deal UI URL path | Confirm on a live company before shipping links |
| Default activity type keys (`task`, `call`) on every tenant | Docs say “such as”; CallLogs require an activity of type `call` when converting via `activity_id`. Discover types. |

---

## Phasing (one spec, sequential delivery)

Each phase is shippable without breaking HubSpot/Salesforce.

**Phase 0 + 1 — one release**  
OAuth, schema, config, match, identity, preview, sync (org/person/deal/note/activities), Settings card, `crm.ts` provider switch, WhatsApp display name. Search must not fall through to HubSpot. Extension stays HubSpot-page-only. Live unique key: `UNIQUE(company_id, provider)` (`028_companies.sql`), not stale `schema.sql`.

**Phase 2 — phone**  
CallLogs + recording upload from Vocify telephony. `phone-integration` scope.

**Phase 3 — later, new specs only**  
Chrome on pipedrive.com; inbound activity webhooks; deal products; Leads inbox; `admin` webhooks.

Do not start Phase 3 inside this spec.

---

## Testing (design)

- Unit: factory returns Pipedrive provider; unsupported provider still 501.
- Client: 401 → refresh → persist new expiry; 429 → error code.
- Schema mapper: enum options → select; hash keys pass through; `set` clear uses `null`.
- Matching: phone search query uses `fields=phone`; 1-char term not sent unless `exact_match`.
- Sync: skip_deal writes person+note, no deal POST; note body includes all three ids when present; Lost without deal → `CALL_OUTCOME_UNSUPPORTED`; Converted always unsupported.
- CallLog: body includes required `outcome`, `to_phone_number`, `start_time`, `end_time`; voice memo path does not POST `/callLogs`.
- Regression: HubSpot and Salesforce provider tests unchanged.

No live Pipedrive writes in CI. Contract tests against recorded official payloads.

---

## File layout (when implemented)

```
backend/app/services/pipedrive/
  client.py
  oauth.py
  exceptions.py
  validation.py
  schema.py
  search.py
  matching.py
  preview.py
  sync.py
  notes.py
  activities.py
  call_logs.py
backend/app/services/crm_providers/pipedrive_provider.py
backend/app/api/crm_pipedrive.py
src/components/dashboard/pipedrive/PipedriveConnection.tsx
src/components/dashboard/pipedrive/PipedriveConfiguration.tsx
```

`factory.py` gains `if provider == "pipedrive"`. `api/router.py` mounts the new router. No HubSpot file edits except telephony’s provider branch in Phase 2.

---

## Spec self-review (2026-09-17 final)

Closed so an implementer cannot invent:

- Phase 0+1 same ship; no HubSpot search fallthrough.
- No `hubspot_*` writes; `matched_deal_id` is the deal-id home.
- `deal_url` omitted until a live UI path is observed (unknown, not guessed).
- Call outcomes off in Phase 1 (Salesforce + PAYPER).
- Identity = existing `IdentityResolution` / `ContactAnchor`.
- `CRMSchema` literals `deals|contacts|companies`.
- `phone-integration` deferred; token TTL from `expires_in`.
- Activity type missing = warning; line items ignored; no rollback.
- WhatsApp: display name only.

Still unknown (must not be coded as fact): Pipedrive deal UI URL; Projects Tasks API; CallLog recording download; person email/phone JSON keys until first live `personFields`.

---

## Approval

Phase 1 is specified tightly enough to write an implementation plan.

Say go and we write `docs/superpowers/plans/2026-09-16-pipedrive-crm-adapter.md` for Phase 0+1 only.
