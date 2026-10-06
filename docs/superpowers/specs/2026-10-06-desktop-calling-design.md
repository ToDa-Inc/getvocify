# Desktop calling: call the CRM contact on screen from the island

**Date:** 2026-10-06
**Status:** Design locked with Dani (2026-10-06). Ready for the four plans below.
**Repos:** `getvocify` (backend + dashboard), `getvocify-desktop` (Swift Mac app), `getvocify-electron` (Electron app).

**Plans**
- A — CRM calling adapters + backend: `docs/superpowers/plans/2026-10-06-desktop-calling-a-crm-adapters.md`
- B — Dashboard call engine + desktop call controller: `docs/superpowers/plans/2026-10-06-desktop-calling-b-dashboard.md`
- C — Swift Mac app: `docs/superpowers/plans/2026-10-06-desktop-calling-c-swift.md`
- D — Electron app: `docs/superpowers/plans/2026-10-06-desktop-calling-d-electron.md`

A and B start together. C and D build against the bridge contract below (with fixtures) and start together with B. All four ship in the same release.

---

## Scope update (Dani, 2026-10-06): HubSpot only

Pipedrive and Salesforce calling are **out** for now. What changes against the rest of this document:

- **Callable CRM:** HubSpot only. Pipedrive pages keep today's behaviour (the meeting call contact name still works), but they never get a phone glyph.
- **Adapter layer stays, kept small:** `CRMCallingAdapter` + `CrmPageMatcher` registries with HubSpot as the only calling adapter. The protocol has only what is used now (`record_context`, `record_url`); `find_contact_by_phone` and `log_call` are added when a second CRM is built. The Twilio pipeline (`webhooks.py`, `call_processor.py`) is **not** rewired, because HubSpot logging already works there.
- **Dropped from plan A:** Task 1 (neutral columns migration), Task 3 (Pipedrive), Task 4 (Salesforce), Task 5 (pipeline rewiring), plus the `crm-hosts` endpoint and the neutral memo upload in Task 6. Kept: Task 2 (registries + HubSpot + contract test) and the preview `phone` / `contacts_count` from Task 6.
- **Dropped from plan B:** `CrmProvider` connect param, any-CRM contact on meeting memos (Task 5 keeps only the dialer gate removal), the Pipedrive reconnect hint (Task 6 keeps only the CRM-tab row), `crmHosts` push.
- **Dropped from plans C and D:** backend-served host rules. Shells keep their current `isCrmURL` (HubSpot + Pipedrive for the meeting contact); `onScreen` is non-null only for HubSpot because the dashboard filters by provider.

## Goal

A rep opens a contact in HubSpot, Pipedrive or Salesforce. The island shows a phone. One click shows who and from which number, a second click calls through Vocify (Twilio). During the call the island shows live transcript and live help. After the call the island shows the same post-call card as a recorded meeting, and the call is logged in the rep's CRM with its recording. The rep never needs the Chrome extension for calling.

## Locked decisions

| # | Topic | Decision |
|---|---|---|
| 1 | Trigger | A **callable CRM contact on screen** (frontmost browser's active tab), not the mic-based call-ready state. Call-ready means a call is already running. |
| 2 | Telephony | Twilio (`CALLING_PROVIDER=twilio`). One call engine in the dashboard (`src/features/calling/callEngine.ts`), used by the dashboard dock and by both desktop apps. Shells never touch Twilio. Telnyx code moves into the engine unchanged. |
| 3 | Live audio | Twilio `call.getLocalStream()` → channel `rep`, `call.getRemoteStream()` → channel `prospect`, into the same live socket meetings use (`liveTranscriptionWsUrl`, `copilot_channels`). Meetings keep mic + system audio. Reason: we own the call; system audio is excluded for our own process (`excludesCurrentProcessAudio = true`), would open the mic twice and lets other sounds into `prospect`. |
| 4 | Memo source | Twilio's dual-channel recording → existing server pipeline (Deepgram, screening, extraction, CRM log). The desktop **never uploads a draft for a Vocify call**. The post-call card follows `GET /calls/{sid}` → `memoId`. |
| 5 | Island | New modes `dialConfirm` and `dialing`. An answered call reuses `recording` with a call bar: mute, keypad, hang up (red) instead of pause and stop. Post-call reuses `finishing` → `postCall`. |
| 6 | CRM adapters | New `CRMCallingAdapter` protocol + `CrmPageMatcher` registry in `backend/app/services/crm_providers/`. HubSpot, Pipedrive and Salesforce implement both. A contract test runs over every registered provider. This **supersedes decision I** of `2026-09-16-pipedrive-crm-adapter-design.md` for telephony; its Phase 2 CallLog outcome map is adopted unchanged. |
| 7 | Data model | Additive, provider-neutral columns on `outbound_calls` and `memos` (`crm_provider`, `crm_connection_id`, `crm_contact_id`, `crm_deal_id`, `crm_activity_id`). `hubspot_*` columns are written **only** when the provider is HubSpot. |
| 8 | CRM hosts | The backend registry is the only source of CRM host patterns (`GET /api/v1/live-calls/crm-hosts`). The dashboard pushes them to the shell (`shell.setState({crmHosts})`). Shells keep a built-in copy for offline start. A new CRM ships without a desktop release. |
| 9 | Permissions | First-run dialog gets a third, optional row "Read your CRM tab" (Mac only; Windows needs none). Not blocking `desktopPermissionsReady`. |
| 10 | Dialer in desktop | The `!isDesktopHost()` gates go away (`DashboardLayout.tsx:99`, `ask-calls.ts:26`). F16 spec row "Dialer no disponible (… app desktop …)" loses "app desktop". |
| 11 | Parity | Swift and Electron islands render from the same fixture states (`island/fixtures` in Electron, the same JSON loaded by Swift through `VOCIFY_ISLAND_FIXTURE`). Side-by-side screenshots are the acceptance gate for every new state. |
| 12 | Scope of "all CRMs" | HubSpot and Pipedrive: on-screen contact, dial, phone lookup, call log + recording, call history, contact on desktop meeting memos. Salesforce: the same set for calls (Contact, Lead, Opportunity, Account pages). Salesforce memo identity stubs (`resolve_contact_anchor`) stay as they are. |

## Defaults chosen (Dani can overrule; nothing blocks)

- **Salesforce Leads are callable** (logged as a Task with `WhoId` = Lead).
- **Deal / company page with several contacts:** callable only when the CRM gives exactly one (HubSpot unique association, Pipedrive deal person, Salesforce primary contact role). Otherwise the confirm row says "Open the contact to call" and offers no Call.
- **The on-screen contact is the last one read.** Switching to Slack does not clear it; a read that finds no CRM record does. The confirm row always names who will be called.
- **Visibility:** no Pro plan → no glyph. Pro without a verified caller ID → greyed glyph, confirm row "Add a caller ID" → opens `ROUTES.CALLING`. Contact without phone → greyed glyph, "No phone in {CRM}".
- **Keypad in v1** (the extension already has DTMF).

## Architecture

```
Browser tab ──(AppleScript / UI Automation)──► Shell watcher ──crm:screen {urls}──► Dashboard
                                                                                 │ POST /live-calls/preview
                                                                                 ▼
Island ◄──shell.setState({onScreen})──────────────────────────────────── on-screen contact
Island ──command "dial"──► Dashboard DesktopCallProvider ──► callEngine.dial() ──► Twilio
                                   │ on accept: live session from call streams (rep/prospect)
                                   ▼
Island ◄──shell.setState({dial, listening, assist, …})── live transcript + live help
Twilio recording webhook ──► call_processor ──► memo + CRMCallingAdapter.log_call
Dashboard polls GET /calls/{sid} → memoId ──► followPostCall(memoId) ──► island postCall card
```

## Bridge contract (both shells)

Existing transport is unchanged: commands are strings on `shell:command`; state is `shell.setState` merged keys; events are `window.__vocifyEmit(channel, payload)` (Swift) or `vocify:emit` (Electron).

**Shell → dashboard**

| Channel | Payload | When |
|---|---|---|
| `crm:screen` | `{ urls: string[] }` (CRM URLs only, frontmost window first; `[]` = no CRM record) | Only when the list changes |
| `shell:command` | `"dial"` | Confirm row's Call |
| `shell:command` | `"hangup"` | Hang up / cancel while dialing |
| `shell:command` | `"mute"` / `"unmute"` | Call bar |
| `shell:command` | `"digit:<d>"`, `d` ∈ `0-9 * #` | Keypad |
| `shell:command` | `"open-calling"` | "Add caller ID" on the confirm row (dashboard opens `ROUTES.CALLING` and shows its window) |

**Dashboard → shell (`shell.setState` keys)**

```ts
type CrmHostRule = { provider: string; host: string }        // host = anchored regex, portable subset (no lookbehind, no named groups)
type OnScreen = {
  provider: "hubspot" | "pipedrive" | "salesforce" | string;  // registry name
  crmLabel: string;                                            // "HubSpot"
  name: string | null;
  phone: string | null;                                        // E.164, display formatting is the island's
  callerId: string | null;                                     // verified number the call goes out from
  state: "callable" | "no_phone" | "needs_contact" | "no_caller_id";
} | null;
type DialIsland = {
  phase: "connecting" | "ringing" | "active" | "ended";
  name: string | null;
  phone: string;
  answeredAt: number | null;                                   // ms epoch
  muted: boolean;
  outcome: "no_answer" | "busy" | "failed" | "canceled" | null; // set with phase "ended"
  message: string | null;                                      // user-facing error copy, Spanish/English per locale
} | null;
// keys: crmHosts: CrmHostRule[], onScreen: OnScreen, dial: DialIsland
```

While `dial` is non-null and not `ended`, the shell must: suppress mic-activity call offers, refuse Record/toggle, and treat the mic held by WebKit/Chromium as Vocify's own.

**Permissions op:** `permissions.status()` gains `crmTabs: "authorized" | "denied" | "not_asked" | "unavailable"`; `permissions.request("crmTabs")` asks every running supported browser. Windows always returns `"authorized"`.

## Island copy (identical in both shells)

| Where | Text |
|---|---|
| Idle glyph help, callable | `Call {name}` |
| Idle glyph help, greyed | `No phone in {crmLabel}` · `Add a caller ID to call` · `Open the contact to call` |
| Confirm row, callable | title `{name}`, line `{phone} · from {callerId}`, button `Call` |
| Confirm row, no_phone | title `{name}`, line `No phone in {crmLabel}`, no button |
| Confirm row, no_caller_id | title `{name}`, line `Add a caller ID to call`, button `Add caller ID` (`open-calling`) |
| Confirm row, needs_contact | title `{crmLabel} record with several contacts`, line `Open the contact to call`, no button |
| Dialing (connecting / ringing) | `Calling {name}…` (or the phone when no name), button `Cancel` (`hangup`) |
| Call bar | elapsed timer, `Mute` / `Unmute`, `Keypad`, `Hang up` |
| Ended | `No answer` · `Busy` · `Call failed` · `Canceled`, plus `message` when set |

Phones are shown with spaces in groups (`+34 600 111 222`); the formatting lives in each shell's core module (`VocifyCore` / `app/core`).

## Backend contract

`POST /api/v1/live-calls/preview` (body unchanged) returns:

```json
{ "provider": "salesforce", "contact_id": "003…", "contact_name": "Ana Ruiz",
  "phone": "+34600111222", "record": {…}, "needs_contact": false, "contacts_count": 1 }
```

`GET /api/v1/live-calls/crm-hosts` → `{ "rules": [{ "provider": "hubspot", "host": "^app(-[a-z0-9]+)?\\.hubspot\\.com$" }, …] }`.

Twilio connect params from the engine: `To`, `CallerId`, `ContactId`, `DealId`, `CrmProvider` (new). A missing `CrmProvider` (extension, old dashboards) resolves to the company's primary/only connection, as today.

`GET /api/v1/calls/{sid}` adds `crmProvider`. `GET /api/v1/calls/history` filters on `crm_contact_id` / `crm_deal_id`.

## Adding a CRM later (the checklist the contract test enforces)

1. `crm_connections.provider` CHECK value (migration).
2. `services/<crm>/page_matcher.py` implementing `CrmPageMatcher`, registered in `crm_providers/pages.py`, with URL fixtures in `tests/crm_providers/fixtures/page_urls.json`.
3. `services/<crm>/calling_adapter.py` implementing `CRMCallingAdapter`, registered in `crm_providers/calling_registry.py`.
4. `test_calling_contract.py` passes for the new name (it parametrizes over the registries, so step 2/3 without fixtures fails).
5. No shell change: hosts arrive through `crm-hosts`. Add the host to the shells' built-in list in their next release.

## Out of scope

- Chrome extension changes (it keeps its dialer; no Salesforce host permission).
- Inbound calls, Electron call detection on Mac, Telnyx-specific fixes.
- Salesforce memo identity (`resolve_contact_anchor` / `resolve_identity` stubs).
- Building the memo from the live transcript (possible later; decision 4).

## Risks to retire first

1. **Twilio streams inside WKWebView.** `createMediaStreamSource(call.getRemoteStream())` must produce non-silent PCM in the Swift app's WKWebView and in Electron. Plan B Task 1 is this spike; if it fails in WKWebView, Plan B stops and we revisit decision 3 before any island work merges.
2. **AppleScript cost on the main thread** for a 1.5 s watcher. Plan C Task 2 measures it with `Perf.swift`; budget p95 ≤ 10 ms per tick or the read moves off-main to `/usr/bin/osascript`.
3. **Pipedrive `phone-integration` scope** needs re-consent. Until reconnected, Pipedrive calls still dial and produce memos; only the CallLog is skipped and Settings shows "Reconnect Pipedrive to log calls".
