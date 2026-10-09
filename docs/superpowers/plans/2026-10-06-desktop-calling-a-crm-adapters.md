# Desktop calling A: CRM calling adapters + backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every CRM (HubSpot, Pipedrive, Salesforce, and any later one) plugs into Vocify calling through one adapter + one page matcher, so a call to the contact on screen is resolved, logged with its recording, and listed in history the same way for all of them.

**Architecture:** Two small registries in `backend/app/services/crm_providers/`: `pages.py` (URL → CRM record, host rules) and `calling_registry.py` (connection → `CRMCallingAdapter`). Each CRM package implements both. The Twilio pipeline (`webhooks.py`, `call_processor.py`) and `/live-calls` stop branching on provider and call the adapter. Additive provider-neutral columns on `outbound_calls` and `memos`.

**Tech Stack:** Python 3 / FastAPI / Supabase (PostgREST), httpx, pytest.

**Spec:** `docs/superpowers/specs/2026-10-06-desktop-calling-design.md` (decisions 4, 6, 7, 8, 12). Also read `docs/superpowers/specs/2026-09-16-pipedrive-crm-adapter-design.md` "Locked contract" — its CallLog outcome map and "never write Pipedrive ids into `hubspot_*`" rule apply here.

## Global Constraints

- Tests: `cd backend && ~/.venvs/vocify-backend/bin/python -m pytest <path> -q`. Never run against `backend/.env` data: that file is **production**. Migrations are written and reviewed here; Dani applies them.
- Next migration number: `075`. Every migration has a `.down.sql`.
- `hubspot_*` columns are written only when `crm_provider == "hubspot"`. Pipedrive deal ids also go to `memos.matched_deal_id` (existing rule).
- HubSpot behaviour must not change: every existing test in `tests/test_telephony_*.py`, `tests/test_hubspot_call_log.py`, `tests/test_hubspot_phone_search.py`, `tests/live_calls/`, `tests/test_calls_history.py`, `tests/test_desktop_call_contact.py`, `tests/test_upload_transcript.py` stays green unchanged.
- CRM API calls are best-effort in the call pipeline: a CRM failure never fails the memo (existing rule in `log_call_engagement`).
- Host regexes use the portable subset: anchored `^…$`, no lookbehind, no named groups, no inline flags (shells compile them with `NSRegularExpression` and JS `RegExp(…, "i")`).
- Pipedrive and Salesforce request/field names below come from their public API references; confirm each against the live API on first call and, if a name differs, use the live one and note it in the PR (same rule as the Pipedrive design).

## Review Focus

1. **A Pipedrive person id that landed in `hubspot_contact_id` before this change** (existing rows): the backfill must assign `crm_provider` from the company's connections, and history for a Pipedrive contact must still find those calls.
2. **A call whose `CrmProvider` param is missing** (Chrome extension, cached old dashboard): it must resolve to the company's primary/only connection, exactly as today, and log to that CRM.
3. **Two CRMs connected, page from the non-primary one:** preview and the call must use the page's provider connection, not the primary.
4. **A page from a different account of the same CRM** (another HubSpot portal, another Salesforce my-domain): not callable (`record` kept, `contact_id` null), never a cross-account read.
5. **Pipedrive connection without `phone-integration` scope:** the call, memo and history work; only the CallLog is skipped, with one warning log, and the connection reports `capabilities.log_calls = false`.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/migrations/075_crm_neutral_call_ids.sql` (+ `.down.sql`) | Neutral columns + backfill + indexes |
| `backend/app/services/crm_providers/calling.py` | DTOs + `CRMCallingAdapter` protocol |
| `backend/app/services/crm_providers/pages.py` | `CrmPageMatcher` protocol, `PAGE_MATCHERS`, `parse_crm_url`, `record_on_screen`, `host_rules` |
| `backend/app/services/crm_providers/calling_registry.py` | `CALLING_ADAPTERS`, `build_calling_adapter`, `calling_connection` |
| `backend/app/services/{hubspot,pipedrive,salesforce}/page_matcher.py` | One matcher each |
| `backend/app/services/{hubspot,pipedrive,salesforce}/calling_adapter.py` | One adapter each |
| `backend/app/services/pipedrive/call_logs.py` | CallLogs + recording upload, outcome map |
| `backend/app/services/salesforce/calling.py` | SOQL/SOSL reads + call Task |
| `backend/app/services/live_calls/crm_url.py` | Becomes a re-export of `pages.py` (keeps imports working) |
| `backend/app/services/telephony/call_processor.py` | Contact-by-phone + call logging through the adapter |
| `backend/app/api/webhooks.py`, `calls.py`, `live_calls.py`, `memos.py`, `crm.py` | Wire neutral columns, `CrmProvider`, preview phone, crm-hosts, upload provider, capabilities |
| `backend/tests/crm_providers/test_calling_contract.py`, `fixtures/page_urls.json` | Contract over every registered CRM |

---

### Task 1: Neutral call/memo columns

**Files:**
- Create: `backend/migrations/075_crm_neutral_call_ids.sql`, `backend/migrations/075_crm_neutral_call_ids.down.sql`
- Test: `backend/tests/test_migration_075_shape.py`

**Interfaces:**
- Produces columns: `outbound_calls.crm_provider text`, `outbound_calls.crm_connection_id uuid references crm_connections(id) on delete set null`, `outbound_calls.crm_contact_id text`, `outbound_calls.crm_deal_id text`, `outbound_calls.crm_activity_id text`; `memos.crm_provider text`, `memos.crm_contact_id text`. Indexes `outbound_calls(user_id, crm_contact_id)`, `outbound_calls(user_id, crm_deal_id)`, `memos(crm_contact_id)`.

- [ ] **Step 1: Write the failing test** — reads the SQL files as text (same approach as `tests/test_sales_role_repair_migration.py`).

```python
def test_075_adds_neutral_columns_and_backfills():
    sql = MIGRATIONS.joinpath("075_crm_neutral_call_ids.sql").read_text()
    for col in ("crm_provider", "crm_connection_id", "crm_contact_id", "crm_deal_id", "crm_activity_id"):
        assert f"add column if not exists {col}" in sql.lower()
    assert "update outbound_calls" in sql.lower() and "update memos" in sql.lower()
    # Review Focus 1: provider comes from the company's connections, not a blanket 'hubspot'
    assert "primary_crm_connection_id" in sql and "crm_connections" in sql
    down = MIGRATIONS.joinpath("075_crm_neutral_call_ids.down.sql").read_text().lower()
    assert "drop column if exists crm_contact_id" in down
```

- [ ] **Step 2: Run it, expect FAIL** (file missing): `… -m pytest tests/test_migration_075_shape.py -q`
- [ ] **Step 3: Write the migration.** Backfill rule: `crm_contact_id = hubspot_contact_id`, `crm_deal_id = hubspot_deal_id`, `crm_activity_id = hubspot_engagement_id`; `crm_provider` = the provider of the company's `primary_crm_connection_id`, else its only connection, else `'hubspot'`; `crm_connection_id` = that connection. Company comes from `user_profiles.company_id` of the row's `user_id`. Same for `memos` where `hubspot_contact_id is not null`. Wrap in one transaction.
- [ ] **Step 4: Run the test, expect PASS.**
- [ ] **Step 5: Commit** `feat(calls): provider-neutral CRM ids on calls and memos`

### Task 2: Calling contract, registries, HubSpot matcher + adapter

**Files:**
- Create: `crm_providers/calling.py`, `crm_providers/pages.py`, `crm_providers/calling_registry.py`, `hubspot/page_matcher.py`, `hubspot/calling_adapter.py`, `tests/crm_providers/test_calling_contract.py`, `tests/crm_providers/fixtures/page_urls.json`
- Modify: `live_calls/crm_url.py` (re-export only)
- Test: `tests/crm_providers/test_calling_contract.py`, existing `tests/live_calls/test_crm_url.py`

**Interfaces (Produces):**

```python
# crm_providers/calling.py
ObjectType = Literal["contact", "lead", "deal", "company"]

@dataclass(frozen=True)
class CrmRecordRef:
    provider: str            # registry name
    object_type: ObjectType
    record_id: str
    account_id: Optional[str]  # HubSpot portal id, Pipedrive company domain, Salesforce my-domain

@dataclass(frozen=True)
class CrmNonRecordPage:      # list, inbox, sequence
    provider: str

@dataclass(frozen=True)
class CrmContact:
    id: str
    object_type: ObjectType  # "contact" or "lead"
    name: Optional[str]
    phone_e164: Optional[str]
    email: Optional[str]

@dataclass(frozen=True)
class RecordContext:
    record: CrmRecordRef
    contact: Optional[CrmContact]   # the one callable person, or None
    contacts_count: int             # people on the record (1 for a contact page)
    deal_id: Optional[str]          # set when the record is a deal

@dataclass(frozen=True)
class CallLogInput:
    call_sid: str
    contact: Optional[CrmContact]
    deal_id: Optional[str]
    from_number: str
    to_number: str
    started_at: datetime
    duration_seconds: int
    disposition: str            # connected | voicemail | busy | no_answer | failed | canceled
    recording_url: Optional[str]
    recording_bytes: Optional[bytes]   # WAV, for CRMs that store the file (Pipedrive)
    title: str
    body: str
    owner_email: Optional[str]

@dataclass(frozen=True)
class CallLogResult:
    activity_id: str
    url: Optional[str]

@runtime_checkable
class CRMCallingAdapter(Protocol):
    provider: str
    label: str                  # "HubSpot"
    can_log_calls: bool         # False e.g. Pipedrive without phone-integration scope
    async def record_context(self, ref: CrmRecordRef) -> Optional[RecordContext]: ...
    async def find_contact_by_phone(self, phone_e164: str) -> Optional[CrmContact]: ...  # exactly one match, else None
    async def log_call(self, call: CallLogInput) -> Optional[CallLogResult]: ...
    def record_url(self, ref: CrmRecordRef) -> Optional[str]: ...

# crm_providers/pages.py
@runtime_checkable
class CrmPageMatcher(Protocol):
    provider: str
    host: str                   # portable anchored regex on the hostname
    def parse(self, url: str) -> Union[CrmRecordRef, CrmNonRecordPage, None]: ...
    def same_account(self, ref: CrmRecordRef, connection: dict) -> bool: ...
    def valid_record_id(self, object_type: ObjectType, record_id: str) -> bool: ...

PAGE_MATCHERS: tuple[CrmPageMatcher, ...]
def parse_crm_url(url: str) -> Union[CrmRecordRef, CrmNonRecordPage, None]: ...
def record_on_screen(urls: Iterable[str]) -> Optional[CrmRecordRef]: ...   # front-most CRM page wins (existing rule)
def host_rules() -> list[dict[str, str]]: ...                               # [{"provider", "host"}]
def matcher_for(provider: str) -> Optional[CrmPageMatcher]: ...

# crm_providers/calling_registry.py
CALLING_ADAPTERS: dict[str, Callable[[Client, dict], CRMCallingAdapter]]
def build_calling_adapter(supabase: Client, connection: dict) -> CRMCallingAdapter: ...
def calling_connection(supabase: Client, user_id: str, provider: Optional[str]) -> Optional[dict]: ...
# provider None → resolve_sync_connection_for_company (primary or only); provider set → that provider's connection.
```

- [ ] **Step 1: Write the contract test** (parametrized over the registries, so later CRMs are covered automatically).

```python
FIXTURES = json.loads((HERE / "fixtures/page_urls.json").read_text())

@pytest.mark.parametrize("provider", sorted(CALLING_ADAPTERS))
def test_every_calling_adapter_has_a_matcher_and_fixtures(provider):
    assert matcher_for(provider) is not None
    assert provider in FIXTURES and FIXTURES[provider]["records"] and FIXTURES[provider]["not_records"]

@pytest.mark.parametrize("provider", sorted(CALLING_ADAPTERS))
def test_fixture_urls_parse(provider):
    for case in FIXTURES[provider]["records"]:
        ref = parse_crm_url(case["url"])
        assert isinstance(ref, CrmRecordRef)
        assert (ref.provider, ref.object_type, ref.record_id, ref.account_id) == (provider, case["object_type"], case["record_id"], case["account_id"])
    for url in FIXTURES[provider]["not_records"]:
        assert not isinstance(parse_crm_url(url), CrmRecordRef)

@pytest.mark.parametrize("rule", host_rules())
def test_host_rules_are_portable(rule):
    assert rule["host"].startswith("^") and rule["host"].endswith("$")
    assert "(?<" not in rule["host"] and "(?P" not in rule["host"] and "(?i" not in rule["host"]
    re.compile(rule["host"])

def test_registries_agree():
    assert {m.provider for m in PAGE_MATCHERS} == set(CALLING_ADAPTERS)
```

`page_urls.json` HubSpot entries: copy every URL from `tests/live_calls/test_crm_url.py` (record, legacy, list, calling-popup → `not_records`).

- [ ] **Step 2: Run, expect FAIL** (modules missing).
- [ ] **Step 3: Implement** `calling.py`, `pages.py`, `calling_registry.py`; move the HubSpot regexes from `live_calls/crm_url.py` into `hubspot/page_matcher.py` (`host = r"^app(-[a-z0-9]+)?\.hubspot\.com$"`, `same_account` compares `account_id` with `metadata.portal_id`, `valid_record_id` = `^\d{1,32}$`). `crm_url.py` re-exports `parse_crm_url`, `record_on_screen`, and aliases `CrmRecord = CrmRecordRef`, `CrmPage = CrmNonRecordPage` so `state.py` keeps importing it.
  `hubspot/calling_adapter.py` `HubSpotCallingAdapter(supabase, connection)`:
  - `record_context`: contact → `get_contact_context_for_extension`; deal/company → the existing deal/company context functions in `api/crm.py`; map `contactPhone` through `normalize_e164` (`telephony/twiml.py:42`); `contacts_count` = `len(contacts)` (1 for a contact).
  - `find_contact_by_phone`: `HubSpotSearchService.find_contacts_by_phone` + `choose_dialed_contact` (same calls as `attach_hubspot_contact_by_phone`).
  - `log_call`: `build_call_properties` + `log_call_to_hubspot` + `mark_recording_ready`, keeping today's owner, title and disposition logic (move it out of `call_processor.log_call_engagement` / `log_missed_call_activity` without changing it).
  - `record_url`: `hubspot/account_info.py` builders.
  - `can_log_calls = True`.
- [ ] **Step 4: Run** `tests/crm_providers tests/live_calls tests/test_hubspot_call_log.py tests/test_hubspot_phone_search.py -q`, expect PASS.
- [ ] **Step 5: Commit** `feat(crm): calling adapter + page matcher registries, HubSpot first`

### Task 3: Pipedrive matcher + adapter + CallLogs

**Files:**
- Create: `pipedrive/page_matcher.py`, `pipedrive/calling_adapter.py`, `pipedrive/call_logs.py`, `tests/pipedrive/test_calling_adapter.py`
- Modify: `pipedrive/client.py` (add `post_file`), `api/crm_pipedrive.py` (store granted `scope` on callback), `crm_providers/pages.py` / `calling_registry.py` (register), `tests/crm_providers/fixtures/page_urls.json`

**Interfaces:**
- Consumes: Task 2 types and registries.
- Produces: `PipedriveCallingAdapter`; `pipedrive_call_log_outcome(disposition: str) -> Optional[str]`; `PipedriveClient.post_file(path: str, *, field: str, filename: str, content: bytes, content_type: str, version: str = "v1") -> Any`; connection metadata key `scope: str` (space-separated, as Pipedrive returns it).

- [ ] **Step 1: Write the failing tests** (fake `PipedriveClient` recording calls; pattern from `tests/pipedrive/`).

```python
@pytest.mark.parametrize("disposition,outcome", [("connected","connected"),("busy","busy"),("no_answer","no_answer"),("voicemail","left_voicemail"),("failed",None),("canceled",None),("weird",None)])
def test_outcome_map(disposition, outcome):
    assert pipedrive_call_log_outcome(disposition) == outcome

async def test_log_call_posts_call_log_and_recording(fake_client):
    adapter = adapter_with(fake_client, scope="deals:full phone-integration")
    result = await adapter.log_call(call_input(disposition="connected", contact=person("42"), deal_id="7", recording_bytes=b"RIFF"))
    post = fake_client.posts[0]
    assert post.path == "/callLogs" and post.version == "v1"
    assert post.body["person_id"] == 42 and post.body["deal_id"] == 7 and post.body["outcome"] == "connected"
    assert post.body["to_phone_number"] == "+34600111222" and post.body["duration"] == "65"
    assert fake_client.files[0].path == f"/callLogs/{result.activity_id}/recordings"

async def test_failed_call_writes_note_not_call_log(fake_client):
    await adapter_with(fake_client, scope="phone-integration").log_call(call_input(disposition="failed", contact=person("42")))
    assert [p.path for p in fake_client.posts] == ["/notes"]

async def test_missing_scope_skips_logging(fake_client, caplog):
    adapter = adapter_with(fake_client, scope="deals:full")
    assert adapter.can_log_calls is False
    assert await adapter.log_call(call_input()) is None and fake_client.posts == []
    assert "pipedrive_missing_phone_scope" in caplog.text

async def test_find_contact_by_phone_needs_exactly_one(fake_client):
    fake_client.search_results = [person_item("1"), person_item("2")]
    assert await adapter_with(fake_client).find_contact_by_phone("+34600111222") is None
```

Fixtures: Pipedrive `records` = deal/person/organization URLs on `acme.pipedrive.com`; `not_records` = `https://acme.pipedrive.com/pipeline`, `https://api.pipedrive.com/v1/deals/1`, `https://app.pipedrive.com/deal/1`.

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
  - Matcher: `host = r"^(?!(api|oauth|www|developers|app)\.)[a-z0-9-]+\.pipedrive\.com$"` (lookahead is in the portable subset; this is the same exclusion `CrmPages.isCrmURL` applies in Swift today); `same_account` compares with `metadata.company_domain`; ids `^\d{1,32}$`.
  - `record_context`: reuse the existing Pipedrive person / deal / organization context functions in `api/crm_pipedrive.py` (`get_pipedrive_person_context` and the deal/org equivalents, moved to `pipedrive/page_context.py` if they live in the route module).
  - `find_contact_by_phone`: `persons/search` with `fields=phone`, `exact_match=true` (as `pipedrive/identity.py:171`); exactly one → `CrmContact`.
  - `log_call` (`call_logs.py`): outcome via the map; `None` → `POST /v1/notes` on the person/deal with the title and body. Otherwise `POST /v1/callLogs` with `subject`, `duration` (string seconds), `outcome`, `from_phone_number`, `to_phone_number`, `start_time`, `end_time` (UTC `YYYY-MM-DD HH:MM:SS`), `person_id`, `deal_id`, `org_id` when known, `note` = body; then `POST /v1/callLogs/{id}/recordings` with the WAV when `recording_bytes`. `record_url` via `build_pipedrive_record_url`.
  - `can_log_calls = "phone-integration" in metadata.scope.split()`.
  - `crm_pipedrive.py` callback: save `tokens["scope"]` into `metadata.scope`.
- [ ] **Step 4: Run** `tests/pipedrive tests/crm_providers -q`, expect PASS.
- [ ] **Step 5: Commit** `feat(pipedrive): calling adapter with CallLogs and recordings`

**Ops note for Dani (not code):** add the `phone-integration` scope to the Vocify app in Pipedrive Developer Hub; existing connections must reconnect.

### Task 4: Salesforce matcher + adapter

**Files:**
- Create: `salesforce/page_matcher.py`, `salesforce/calling.py`, `salesforce/calling_adapter.py`, `tests/salesforce/__init__.py`, `tests/salesforce/test_calling_adapter.py`
- Modify: registries, `fixtures/page_urls.json`

**Interfaces:**
- Consumes: `SalesforceClient.get/post` (`salesforce/client.py:162-168`), connection `metadata.instance_url`.
- Produces: `SalesforceCallingAdapter`; `salesforce_my_domain(host: str) -> Optional[str]` (first label of `*.my.salesforce.com` / `*.lightning.force.com`).

- [ ] **Step 1: Write the failing tests.**

```python
def test_parse_lightning_urls():
    ref = parse_crm_url("https://acme.lightning.force.com/lightning/r/Contact/0035g00000AbCdEAAZ/view")
    assert (ref.provider, ref.object_type, ref.record_id, ref.account_id) == ("salesforce", "contact", "0035g00000AbCdEAAZ", "acme")
    assert parse_crm_url("https://acme.lightning.force.com/lightning/r/Lead/00Q5g000001abcd/view").object_type == "lead"
    assert parse_crm_url("https://acme.lightning.force.com/lightning/r/Opportunity/0065g000001abcd/view").object_type == "deal"
    assert parse_crm_url("https://acme.lightning.force.com/lightning/r/Account/0015g000001abcd/view").object_type == "company"
    assert isinstance(parse_crm_url("https://acme.lightning.force.com/lightning/o/Contact/list"), CrmNonRecordPage)

def test_same_account_by_my_domain():
    conn = {"metadata": {"instance_url": "https://acme.my.salesforce.com"}}
    assert matcher.same_account(ref(account_id="acme"), conn) and not matcher.same_account(ref(account_id="other"), conn)

async def test_opportunity_context_uses_primary_contact_role(fake_sf):
    fake_sf.query_results["OpportunityContactRole"] = [role("003A", primary=True), role("003B")]
    ctx = await adapter(fake_sf).record_context(ref("deal", "006X"))
    assert ctx.contact.id == "003A" and ctx.contacts_count == 2 and ctx.deal_id == "006X"

async def test_log_call_creates_call_task(fake_sf):
    result = await adapter(fake_sf).log_call(call_input(contact=contact("003A"), deal_id="006X", duration_seconds=65, disposition="connected"))
    body = fake_sf.posts["/services/data/v60.0/sobjects/Task"]
    assert body["TaskSubtype"] == "Call" and body["CallType"] == "Outbound" and body["Status"] == "Completed"
    assert body["WhoId"] == "003A" and body["WhatId"] == "006X" and body["CallDurationInSeconds"] == 65
    assert body["CallObject"] == "CA123"   # Twilio CallSid, idempotency key
    assert result.activity_id == fake_sf.created_id

async def test_find_contact_by_phone_sosl_exactly_one(fake_sf):
    fake_sf.search_results = [sf_contact("003A")]
    assert (await adapter(fake_sf).find_contact_by_phone("+34600111222")).id == "003A"
```

Use the API version constant `SalesforceClient` already uses; the `v60.0` above is a placeholder for that constant in the test, not a new value.

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
  - Matcher: `host = r"^[a-z0-9-]+(\.[a-z0-9-]+)?\.(lightning\.force|my\.salesforce)\.com$"`; record path `^/lightning/r/(Contact|Lead|Opportunity|Account)/([a-zA-Z0-9]{15}|[a-zA-Z0-9]{18})/`; `valid_record_id` = 15 or 18 alphanumerics.
  - `calling.py`: SOQL reads — Contact `Id, Name, Phone, MobilePhone, Email`; Lead same + `Company`; Opportunity → `OpportunityContactRole` `ContactId, Contact.Name, Contact.Phone, Contact.MobilePhone, Contact.Email, IsPrimary` ordered `IsPrimary DESC` limit 5 (callable = the primary one, else the only one); Account → `Contact` where `AccountId` limit 5 (callable only if exactly one). Phone = `MobilePhone or Phone` through `normalize_e164`. SOSL `FIND {digits} IN PHONE FIELDS RETURNING Contact(Id, Name, Phone, MobilePhone, Email), Lead(Id, Name, Phone, MobilePhone, Email)`; exactly one hit → contact.
  - `log_call`: `POST sobjects/Task` with `Subject` = title, `Description` = body + recording URL, `TaskSubtype` `Call`, `CallType` `Outbound`, `CallDurationInSeconds`, `CallDisposition` = disposition, `CallObject` = call_sid, `Status` `Completed`, `ActivityDate` = date, `WhoId`, `WhatId` (deal). `record_url` = `{instance_url}/lightning/r/{Object}/{id}/view`.
  - `can_log_calls = True`.
- [ ] **Step 4: Run** `tests/salesforce tests/crm_providers -q`, expect PASS.
- [ ] **Step 5: Commit** `feat(salesforce): calling adapter, Lightning page matcher, call Tasks`

### Task 5: Twilio pipeline through the adapter

**Files:**
- Modify: `api/webhooks.py:623-698` (voice), `:746-768` (dial-status), `:771-846` (recording); `telephony/call_processor.py:93-176, 431-702`; `api/calls.py:353-380, 403-465`
- Test: `tests/test_telephony_webhook.py`, `tests/test_telephony_call_processor.py`, `tests/test_calls_history.py` (new cases only)

**Interfaces:**
- Consumes: `calling_connection`, `build_calling_adapter`, `CallLogInput`.
- Produces: `attach_contact_by_phone(supabase: Client, call_row: dict) -> Optional[CrmContact]` (replaces `attach_hubspot_contact_by_phone`, which is deleted after its callers move); `log_call_to_crm(supabase: Client, call_sid: str, duration: float, *, disposition: str, recording_bytes: Optional[bytes] = None) -> None` (replaces `log_call_engagement` and the logging half of `log_missed_call_activity`); `/calls/{sid}` and `/calls/history` items gain `crmProvider`.

- [ ] **Step 1: Write the failing tests.**

```python
def test_voice_webhook_stores_neutral_ids_for_pipedrive(client, fake_db, pipedrive_company):
    post_voice(client, To="+34600111222", ContactId="42", DealId="7", CrmProvider="pipedrive")
    row = fake_db.inserted("outbound_calls")
    assert (row["crm_provider"], row["crm_contact_id"], row["crm_deal_id"]) == ("pipedrive", "42", "7")
    assert row["hubspot_contact_id"] is None and row["hubspot_deal_id"] is None

def test_voice_webhook_without_provider_uses_primary(client, fake_db, hubspot_company):
    post_voice(client, To="+34600111222", ContactId="901")
    row = fake_db.inserted("outbound_calls")
    assert row["crm_provider"] == "hubspot" and row["hubspot_contact_id"] == "901" == row["crm_contact_id"]

async def test_connected_call_logs_through_adapter_once(fake_db, fake_adapter):
    await log_call_to_crm(fake_db, "CA1", 65, disposition="connected")
    await log_call_to_crm(fake_db, "CA1", 65, disposition="connected")
    assert len(fake_adapter.logged) == 1 and fake_db.row("outbound_calls", "CA1")["crm_activity_id"] == "act-1"

async def test_contact_found_by_phone_is_written_neutrally(fake_db, fake_adapter):
    fake_adapter.by_phone = crm_contact("42")
    await attach_contact_by_phone(fake_db, call_row(crm_provider="pipedrive", to_number="+34600111222"))
    assert fake_db.row("outbound_calls", "CA1")["crm_contact_id"] == "42"

def test_history_filters_neutral_contact(client, fake_db):
    seed_calls(fake_db, [{"crm_contact_id": "42", "crm_provider": "pipedrive"}, {"crm_contact_id": "9"}])
    assert [c["contactId"] for c in get_history(client, contactId="42")] == ["42"]
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** Voice webhook: read `CrmProvider`; `connection = calling_connection(supabase, user_id, provider or None)`; insert neutral columns + `crm_connection_id`; write `hubspot_*` only for HubSpot. Recording webhook: `attach_contact_by_phone` when `crm_contact_id` is empty; `initiate_vocify_call_memo` writes `memos.crm_provider/crm_contact_id`, `hubspot_*` only for HubSpot, Pipedrive/Salesforce deal → `matched_deal_id`. `process_vocify_call_background` calls `log_call_to_crm(..., disposition=screening_outcome, recording_bytes=audio_bytes)` where it called `log_call_engagement`. Dial-status: `log_call_to_crm(..., disposition=normalize_twilio_dial_status(status))`. `log_call_to_crm` skips when `crm_activity_id` is set or `adapter.can_log_calls` is false; stores `crm_activity_id` (and `hubspot_engagement_id` for HubSpot, which `linking.py` and `mark_recording_ready` read). History and `/calls/{sid}`: filter/return neutral columns.
- [ ] **Step 4: Run** the full constraint list of existing tests plus the new ones, expect PASS.
- [ ] **Step 5: Commit** `feat(calls): Twilio calls resolve and log through the CRM calling adapter`

### Task 6: Live-call preview phone, crm-hosts, neutral memo upload, capabilities

**Files:**
- Modify: `api/live_calls.py:35-101` (preview, `PickContactIn`, delete `_ACCOUNT_KEY` / `_contact_name` / `_connected_account_id` in favour of adapters), `services/live_calls/state.py` (`Provider` → `str`), `api/memos.py:855,974` (upload), `api/crm.py:1271` (`GET /connections`)
- Test: `tests/live_calls/test_live_calls_http.py`, `tests/test_desktop_call_contact.py`, `tests/test_upload_transcript.py` (new cases)

**Interfaces:**
- Produces: preview response `{provider, contact_id, contact_name, phone, record, needs_contact, contacts_count}`; `GET /api/v1/live-calls/crm-hosts` → `{"rules": host_rules()}` (auth required, cache header `max-age=3600`); upload accepts `crm_provider` + `crm_contact_id` form fields (keeps `hubspot_contact_id` for old clients, which means `crm_provider="hubspot"`); each `/crm/connections` item gains `capabilities: {"log_calls": bool}`.

- [ ] **Step 1: Write the failing tests.**

```python
def test_preview_returns_phone_for_salesforce_contact(client, salesforce_company, fake_sf_adapter):
    fake_sf_adapter.context = ctx(contact=crm_contact("003A", phone="+34600111222", name="Ana Ruiz"))
    body = post_preview(client, ["https://acme.lightning.force.com/lightning/r/Contact/003A00000000001/view"])
    assert body["provider"] == "salesforce" and body["phone"] == "+34600111222" and body["contact_name"] == "Ana Ruiz"

def test_preview_other_account_is_not_callable(client, salesforce_company):
    body = post_preview(client, ["https://other.lightning.force.com/lightning/r/Contact/003A00000000001/view"])
    assert body["contact_id"] is None and body["phone"] is None

def test_preview_uses_page_provider_not_primary(client, hubspot_primary_with_pipedrive):
    assert post_preview(client, ["https://acme.pipedrive.com/person/42"])["provider"] == "pipedrive"

def test_deal_with_two_contacts_needs_contact(client, hubspot_company, fake_hs_adapter):
    fake_hs_adapter.context = ctx(contact=None, contacts_count=2)
    body = post_preview(client, ["https://app.hubspot.com/contacts/1/record/0-3/55"])
    assert body["needs_contact"] is True and body["contacts_count"] == 2

def test_crm_hosts_lists_every_registered_crm(client):
    assert {r["provider"] for r in client.get("/api/v1/live-calls/crm-hosts").json()["rules"]} == {"hubspot", "pipedrive", "salesforce"}

def test_upload_with_pipedrive_contact_never_touches_hubspot_column(client, fake_db):
    upload_transcript(client, crm_provider="pipedrive", crm_contact_id="42")
    memo = fake_db.inserted("memos")
    assert memo["crm_contact_id"] == "42" and memo["hubspot_contact_id"] is None
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** Preview: `record_on_screen` → `matcher_for(ref.provider)` → `calling_connection(supabase, user_id, ref.provider)`; not connected or `not same_account` → no contact; else `build_calling_adapter(...).record_context(ref)`; `contact` from the context. `PickContactIn.provider: str` validated against `CALLING_ADAPTERS` and `valid_record_id`. Upload and connections as in Interfaces.
- [ ] **Step 4: Run** `tests/live_calls tests/test_desktop_call_contact.py tests/test_upload_transcript.py -q`, expect PASS.
- [ ] **Step 5: Commit** `feat(live-calls): phone on preview, CRM host rules, neutral contact on desktop memos`
