# Desktop calling B: dashboard call engine + desktop call controller Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The dashboard (inside either desktop app) dials the contact the island shows, streams the call's two sides into live transcript and live help, and hands the island the server-built memo after hang-up.

**Architecture:** The Twilio/Telnyx logic leaves `DashboardDialer.tsx` for a singleton `callEngine` with a pure, node-tested reducer. `DesktopCallProvider` (desktop host only) turns shell commands into engine calls and engine state into `shell.setState({dial})`, resolves the on-screen contact into `onScreen`, and asks `DesktopMeetingProvider` for a live session fed by the call's streams. The dock and the island share the same engine, so a call started anywhere shows on the island.

**Tech Stack:** React 19 + TypeScript, `@twilio/voice-sdk` 2.18.3, `@telnyx/webrtc` 2.27.10, node:test with `--experimental-strip-types`.

**Spec:** `docs/superpowers/specs/2026-10-06-desktop-calling-design.md` (decisions 2, 3, 4, 5, 9, 10; bridge contract; backend contract). Backend fields come from plan A Task 5–6; until they land, the preview `phone` is `null` and every on-screen contact is `no_phone`.

## Global Constraints

- Pure logic lives in `src/lib/*.ts` with no `@/` imports and is tested with `node --experimental-strip-types --test src/lib/<file>.test.ts`. Run the whole set with `make test-js`.
- `npm run lint` and `npm run lint:ui` pass. UI copy follows `vocify-ux-coherence` (load that skill before any visible change); no hardcoded colours.
- Verify every user-visible change with Reticle (`/reticle`, `reticle_act_and_wait` with an `until`) before calling a task done (`CLAUDE.md`).
- Shell commands are plain strings on `shell:command` exactly as in the spec's bridge contract: `dial`, `hangup`, `mute`, `unmute`, `digit:<d>`, `open-calling`.
- Production calls go through Twilio. Do not change the Telnyx behaviour; move it as-is.
- Never upload a draft (`memosApi.uploadTranscriptAndExtract`) for a Vocify call.

## Review Focus

1. **The rep presses Record (or the shortcut `toggle`) during a Vocify call:** ignored; no second session, no draft.
2. **The rep switches CRM tab while the call runs:** the island keeps the dialled contact; `onScreen` changes but `dial.name` does not.
3. **Call not answered (no answer / busy / failed):** no live session starts, no post-call card, the island shows the outcome for 4 s then returns to idle.
4. **Live socket drops mid-call:** the call continues; reconnect uses the existing 5-try backoff; hang-up still follows the server memo.
5. **Recording webhook is late or never comes:** the post-call card waits with the existing `afterCallPoll` limits and then gives up exactly like a meeting upload that never finished (`POST_CALL_GIVE_UP_MS`).

---

## File Structure

| File | Responsibility |
|---|---|
| `src/lib/call-engine-state.ts` (+ test) | `CallEngineState`, events, `reduceCall` |
| `src/features/calling/callEngine.ts` | Singleton wiring Twilio/Telnyx to the reducer; streams |
| `src/components/dashboard/calling/DashboardDialer.tsx` | UI only, reads/drives `callEngine` |
| `src/lib/on-screen-call.ts` (+ test) | Preview + calling config → `OnScreen` |
| `src/lib/dial-island.ts` (+ test) | Engine state → `DialIsland`; command parsing |
| `src/lib/copilot-channel-stt.ts` | `hookStreamPcm` (generalises `hookMicPcm`) |
| `src/features/desktop/DesktopCallProvider.tsx` | Commands, `onScreen`, `dial`, `crmHosts`, post-call follow |
| `src/features/desktop/DesktopMeetingProvider.tsx` | `startCallSession` / `endCallSession`; Record blocked during calls; neutral contact on meeting drafts |
| `src/lib/desktop-host.ts` | Bridge types: `crm.onScreen`, permission `crmTabs` |
| `src/lib/desktop-permissions.ts`, `DesktopPermissionsPanel.tsx` | Optional CRM-tab row |
| `src/components/dashboard/DashboardLayout.tsx`, `src/lib/ask-calls.ts`, `docs/features/F16-espacio-comercial/spec.md` | Dialer allowed in the desktop host |
| Settings CRM card (Pipedrive) | "Reconnect Pipedrive to log calls" when `capabilities.log_calls` is false |

---

### Task 1: Spike — Twilio streams produce PCM in both webviews (gate for everything after Task 2)

**Files:** scratch branch `spike/desktop-call-streams`, not merged.

- [ ] **Step 1:** On the scratch branch, temporarily drop `!isDesktopHost()` from `DashboardLayout.tsx:99` and, in `DashboardDialer.tsx` after `accept`, feed `call.getLocalStream()` and `call.getRemoteStream()` into an `AnalyserNode` each and `console.log` their RMS once per second.
- [ ] **Step 2:** Run the dashboard (`npm run dev`), open it in the Swift app with `VOCIFY_WEB_ORIGIN=http://localhost:8080 Vocify.app/Contents/MacOS/Vocify`, call your own mobile from a verified caller ID, speak on each side.
- [ ] **Step 3:** Repeat in the Electron app (`cd ~/getvocify-electron/app && VOCIFY_WEB_ORIGIN=http://localhost:8080 npm start`).
- [ ] **Step 4: Pass criterion:** in both apps, local RMS rises only while you speak into the Mac, remote RMS only while you speak into the phone, and call audio stays audible. Record the result (pass/fail per app, macOS version) in the PR description of Task 2. **If WKWebView fails, stop and report to Dani before Task 4** (spec "Risks to retire first" #1).

### Task 2: Call engine out of DashboardDialer

**Files:**
- Create: `src/lib/call-engine-state.ts`, `src/lib/call-engine-state.test.ts`, `src/features/calling/callEngine.ts`
- Modify: `src/components/dashboard/calling/DashboardDialer.tsx` (logic at 164-609 moves out; UI stays)

**Interfaces (Produces):**

```ts
// src/lib/call-engine-state.ts
export type CallPhase = "idle" | "connecting" | "ringing" | "active" | "ended";
export type CallOutcome = "no_answer" | "busy" | "failed" | "canceled";
export type DialTarget = {
  to: string;                // E.164
  name: string | null;
  crmProvider: string | null;
  contactId: string | null;
  dealId: string | null;
  callerId: string;          // verified number
};
export type CallEngineState = {
  phase: CallPhase;
  target: DialTarget | null;
  callSid: string | null;
  answeredAt: number | null;
  muted: boolean;
  outcome: CallOutcome | null;
  message: string | null;
};
export type CallEngineEvent =
  | { type: "dial"; target: DialTarget }
  | { type: "ringing"; callSid: string }
  | { type: "accepted"; at: number }
  | { type: "muted"; muted: boolean }
  | { type: "disposition"; outcome: CallOutcome }
  | { type: "ended"; message?: string | null }
  | { type: "reset" };
export const IDLE_CALL: CallEngineState;
export function reduceCall(state: CallEngineState, event: CallEngineEvent): CallEngineState;

// src/features/calling/callEngine.ts
export const callEngine: {
  getState(): CallEngineState;
  subscribe(listener: (s: CallEngineState) => void): () => void;
  dial(target: DialTarget): Promise<void>;     // no-op unless phase is idle or ended
  hangup(): void;
  setMuted(muted: boolean): void;
  sendDigits(digits: string): void;           // validated /^[0-9*#]+$/, active only
  streams(): { local: MediaStream; remote: MediaStream } | null;  // non-null only while active
  reset(): void;                              // ended → idle
};
```

- [ ] **Step 1: Write the failing reducer tests.**

```ts
it("dial → ringing → accepted → ended keeps the target and answer time", () => {
  let s = reduceCall(IDLE_CALL, { type: "dial", target: T });
  assert.equal(s.phase, "connecting");
  s = reduceCall(s, { type: "ringing", callSid: "CA1" });
  s = reduceCall(s, { type: "accepted", at: 1000 });
  assert.deepEqual([s.phase, s.callSid, s.answeredAt], ["active", "CA1", 1000]);
  s = reduceCall(s, { type: "ended" });
  assert.deepEqual([s.phase, s.outcome, s.target], ["ended", null, T]);
});
it("an unanswered call ends with its carrier outcome", () => {
  let s = reduceCall(reduceCall(IDLE_CALL, { type: "dial", target: T }), { type: "ringing", callSid: "CA1" });
  s = reduceCall(reduceCall(s, { type: "disposition", outcome: "busy" }), { type: "ended" });
  assert.deepEqual([s.phase, s.outcome, s.answeredAt], ["ended", "busy", null]);
});
it("ignores a second dial while a call is up", () => {
  const live = reduceCall(IDLE_CALL, { type: "dial", target: T });
  assert.equal(reduceCall(live, { type: "dial", target: { ...T, to: "+1" } }).target, T);
});
it("mute only applies while active", () => {
  assert.equal(reduceCall(IDLE_CALL, { type: "muted", muted: true }).muted, false);
});
it("a disposition after answer does not override a connected call", () => {
  let s = reduceCall(reduceCall(reduceCall(IDLE_CALL, { type: "dial", target: T }), { type: "ringing", callSid: "CA1" }), { type: "accepted", at: 1 });
  assert.equal(reduceCall(s, { type: "disposition", outcome: "no_answer" }).outcome, null);
});
```

- [ ] **Step 2: Run** `node --experimental-strip-types --test src/lib/call-engine-state.test.ts`, expect FAIL.
- [ ] **Step 3: Implement** the reducer, then `callEngine.ts` by moving `ensureDevice`, `startTwilioCall`, the Telnyx path, `hangup`, `toggleMute`, carrier-disposition polling and ring timeout out of `DashboardDialer.tsx`. Changes while moving: Twilio `connect` params add `DealId` and `CrmProvider`; handle `device.on("tokenWillExpire")` by re-minting via `callsApi.createToken` + `device.updateToken` (as `chrome-extension/offscreen.js:386`); add `sendDigits` (`call.sendDigits`). The Device lives in the singleton (no longer destroyed when the dock closes; destroyed on sign-out). `DashboardDialer` subscribes with `useSyncExternalStore(callEngine.subscribe, callEngine.getState)`; search, focus and the in-call UI are unchanged.
- [ ] **Step 4: Run** the reducer tests (PASS), `npm run lint`, then Reticle: in the browser dashboard, dial from the dock with `reticle_act_and_wait({ ref: <Llamar>, action: "click", until: <dialer phase ringing in dialer-reticle-store> })`, hang up, `until` phase idle. Expect `verified: "yes"`.
- [ ] **Step 5: Commit** `refactor(calling): one call engine for the dock and the desktop island`

### Task 3: On-screen contact and island dial state (pure)

**Files:**
- Create: `src/lib/on-screen-call.ts`, `src/lib/on-screen-call.test.ts`, `src/lib/dial-island.ts`, `src/lib/dial-island.test.ts`
- Modify: `src/lib/call-contact.ts` (`CallPreview` gains `phone: string | null`, `contacts_count: number`; `provider: string | null`)

**Interfaces (Produces):**

```ts
// on-screen-call.ts — OnScreen exactly as in the spec bridge contract
export type CallingAccess = { canDial: boolean; callerId: string | null; crmLabels: Record<string, string> };
export function onScreenFromPreview(preview: CallPreview | null, access: CallingAccess): OnScreen;  // null when !canDial or no record
export function dialTargetFromOnScreen(onScreen: OnScreen, preview: CallPreview): DialTarget | null; // null unless state "callable"

// dial-island.ts — DialIsland exactly as in the spec bridge contract
export function dialIsland(state: CallEngineState): DialIsland;   // null when phase idle
export type CallCommand = { kind: "dial" } | { kind: "hangup" } | { kind: "mute"; muted: boolean } | { kind: "digit"; digit: string } | { kind: "open-calling" };
export function parseCallCommand(raw: string): CallCommand | null;
export const ENDED_HOLD_MS = 4000;
```

- [ ] **Step 1: Write the failing tests.**

```ts
it("callable when the contact has a phone and a caller id exists", () => {
  assert.deepEqual(onScreenFromPreview(pv({ phone: "+34600111222" }), access()), { provider: "hubspot", crmLabel: "HubSpot", name: "Ana Ruiz", phone: "+34600111222", callerId: "+34910000000", state: "callable" });
});
it("no phone → no_phone; no caller id → no_caller_id; several contacts → needs_contact", () => {
  assert.equal(onScreenFromPreview(pv({ phone: null }), access())?.state, "no_phone");
  assert.equal(onScreenFromPreview(pv({ phone: "+34600111222" }), access({ callerId: null }))?.state, "no_caller_id");
  assert.equal(onScreenFromPreview(pv({ contact_id: null, needs_contact: true, contacts_count: 2 }), access())?.state, "needs_contact");
});
it("hidden without the dialer plan or without a record", () => {
  assert.equal(onScreenFromPreview(pv({ phone: "+34600111222" }), access({ canDial: false })), null);
  assert.equal(onScreenFromPreview(null, access()), null);
});
it("parses island commands", () => {
  assert.deepEqual(parseCallCommand("digit:#"), { kind: "digit", digit: "#" });
  assert.deepEqual(parseCallCommand("unmute"), { kind: "mute", muted: false });
  assert.deepEqual(parseCallCommand("open-calling"), { kind: "open-calling" });
  assert.equal(parseCallCommand("digit:x"), null);
  assert.equal(parseCallCommand("listen"), null);
});
it("maps engine state to the island", () => {
  assert.equal(dialIsland(IDLE_CALL), null);
  assert.deepEqual(dialIsland(ended("no_answer")), { phase: "ended", name: "Ana Ruiz", phone: "+34600111222", answeredAt: null, muted: false, outcome: "no_answer", message: null });
});
```

- [ ] **Step 2: Run, expect FAIL.**  - [ ] **Step 3: Implement.**  - [ ] **Step 4: Run, expect PASS** (also `src/lib/call-contact.test.ts` unchanged and green).
- [ ] **Step 5: Commit** `feat(desktop): on-screen contact and island dial state`

### Task 4: DesktopCallProvider + call-fed live session

**Files:**
- Create: `src/features/desktop/DesktopCallProvider.tsx`
- Modify: `src/lib/desktop-host.ts` (types), `src/lib/copilot-channel-stt.ts` (`hookStreamPcm`), `src/features/desktop/DesktopMeetingProvider.tsx`, `src/components/dashboard/DashboardLayout.tsx` (mount inside `DesktopMeetingProvider`, desktop host only)

**Interfaces:**
- Consumes: `callEngine`, `onScreenFromPreview`, `dialTargetFromOnScreen`, `dialIsland`, `parseCallCommand`, `ENDED_HOLD_MS`, `afterCallPoll` (`src/lib/after-call.ts:48`), `GET /live-calls/crm-hosts`, `POST /live-calls/preview`, `useCallingConfig` (`src/features/calls/useCallingConfig.ts`).
- Produces on `DesktopMeetingContext`: `startCallSession(args: { callSid: string; streams: { local: MediaStream; remote: MediaStream }; contact: { provider: string; id: string; name: string | null } | null }): Promise<void>` and `endCallSession(callSid: string, contactName: string | null): Promise<void>`. Bridge types: `crm.onScreen?(listener: (p: { urls: string[] }) => void): () => void`; `DesktopPermissionSnapshot.crmTabs?: DesktopPermissionStatus`. `hookStreamPcm(ctx: AudioContext, stream: MediaStream, onPcm: (pcm: ArrayBuffer) => void): () => void` (`hookMicPcm` becomes an alias).

- [ ] **Step 1: Write the behaviour down as Reticle flows first** (they are the test for this task; save each with `intent`):
  1. "Contact on screen shows a callable phone": emit `crm:screen` with a HubSpot contact URL through `window.__vocifyEmit` → `until` store `onScreen.state === "callable"`.
  2. "Island Call dials and goes live on answer": emit `shell:command` `dial` → `until` network `POST /calls/token` and store `dial.phase === "ringing"`; on answer `until` `listening === true` and a WebSocket to `/transcription/live`.
  3. "Hang-up hands the island the server memo": emit `hangup` → `until` request `GET /calls/CA…` then store `postCall.memoId` equals that call's `memoId`.
  4. "Record is refused during a call": emit `listen` while `dial.phase === "active"` → `until` no new `POST /transcription/ticket` and `listening` unchanged (use `reticle_assert`).
- [ ] **Step 2: Implement `DesktopCallProvider`.**
  - On mount (desktop host, signed in): fetch `crm-hosts`, `shell.setState({ crmHosts: rules })`.
  - `crm.onScreen` → latest-only `POST /live-calls/preview` → `shell.setState({ onScreen })`; keep the preview for `dialTargetFromOnScreen`.
  - `shell.onCommand`: `parseCallCommand`; `dial` → `callEngine.dial(target)` (no target → ignore); `hangup` / `mute` / `digit` → engine; `open-calling` → `navigate(ROUTES.CALLING)` + `shell.command("show")`.
  - `callEngine.subscribe`: `shell.setState({ dial: dialIsland(s) })`; on transition to `active` → `navigate(ROUTES.RECORD)` then `startCallSession({ callSid, streams: callEngine.streams(), contact })`; on `ended` after an answer → `endCallSession(callSid, name)`; on `ended` → after `ENDED_HOLD_MS` `callEngine.reset()`.
- [ ] **Step 3: Implement the session in `DesktopMeetingProvider`.** `startCallSession` follows the web path of `start()` (751-944) with these differences: no mic `getUserMedia`, no `systemAudio.start`, no permission check for system audio; `hookStreamPcm(ctx, local, send("rep"))` + `hookStreamPcm(ctx, remote, send("prospect"))`; draft meta source `"vocify_call"`; `shell.setState({ listening: true, … })` + `showOverlay` as `start()` does. `endCallSession`: `shell.setState({ listening: false, finish: { step: "stopping" } })`, `hideOverlay`, `releaseAudio`, `drainSocket`, **no `sendDraft`**; then poll `callsApi.getCall(callSid)` with `afterCallPoll` until `memoId`, then `followPostCall(memoId, contactName)`; poll gives up → `finish: { step: "failed", message }` with the meeting copy. The `listen` / `toggle` handlers return early when `callEngine.getState().phase` is not `idle`.
- [ ] **Step 4: Drive the four flows** in the Swift app pointed at `VOCIFY_WEB_ORIGIN=http://localhost:8080` (island side from plan C can be stubbed by emitting events via Reticle). Expect `verified: "yes"` for each.
- [ ] **Step 5: Commit** `feat(desktop): dial from the island with live transcript from the call itself`

### Task 5: Dialer allowed in the desktop host; neutral contact on meeting memos

**Files:**
- Modify: `src/components/dashboard/DashboardLayout.tsx:99`, `src/lib/ask-calls.ts:25-28` (+ its test if any), `docs/features/F16-espacio-comercial/spec.md:116`, `src/features/desktop/DesktopMeetingProvider.tsx:1037-1065, 325-342` (contact for any provider), `src/features/memos/api.ts` (`uploadTranscriptAndExtract` sends `crm_provider` + `crm_contact_id`)

- [ ] **Step 1: Write the failing test** in `src/lib/ask-calls.test.ts`:

```ts
it("the dialer is available in the desktop host", () => {
  assert.equal(dialerAvailable({ desktop: true, company: proCompany }), true);
});
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** Remove the desktop condition (keep `paywalled` and `companyCanUseDialer`). F16 row becomes "Dialer no disponible (plan, sin número verificado)". `onCallPages` keeps `callContactRef = { provider, id, name }` for every provider (not only HubSpot); `sendDraft` sends `crmProvider` + `crmContactId` (and `hubspotContactId` only for HubSpot, for old backends).
- [ ] **Step 4: Run** the test (PASS); Reticle: record a short desktop meeting with a Pipedrive person on screen → `until` the upload request carries `crm_provider=pipedrive`. Expect `verified: "yes"`.
- [ ] **Step 5: Commit** `feat(desktop): Vocify dialer in the desktop app; any CRM contact on meeting memos`

### Task 6: CRM-tab permission row + Pipedrive reconnect hint

**Files:**
- Modify: `src/lib/desktop-permissions.ts` (+ test), `src/features/desktop/DesktopPermissionsPanel.tsx:89-110`, `src/features/desktop/useDesktopPermissions.ts`, the Pipedrive connection card in Settings (`SettingsPage.tsx:127-130` area)

**Interfaces:**
- Produces: `DESKTOP_PERMISSION.crmTabs = "crmTabs"`; `permissionCopy("crmTabs")` → title "Read your CRM tab", body "So Vocify can call the contact you have open."; `desktopPermissionsReady` unchanged (mic + system audio only); the row renders only when the snapshot has a `crmTabs` field.

- [ ] **Step 1: Write the failing tests.**

```ts
it("the CRM tab permission never blocks setup", () => {
  assert.equal(desktopPermissionsReady({ microphone: "authorized", systemAudio: "authorized", crmTabs: "denied" }), true);
});
it("has its own copy and action", () => {
  assert.equal(permissionCopy("crmTabs").title, "Read your CRM tab");
  assert.equal(permissionAction("not_asked"), "request");
  assert.equal(permissionAction("denied"), "open_settings");
});
```

- [ ] **Step 2: Run, expect FAIL.**  - [ ] **Step 3: Implement** (row calls `permissions.request("crmTabs")`; `open_settings` → `crm.openAutomationSettings()`). Pipedrive card: when `capabilities.log_calls === false`, show "Reconnect Pipedrive to log calls" with the existing reconnect action.
- [ ] **Step 4: Run** tests (PASS); Reticle on the first-run dialog in the Swift app: click the row → `until` `permissions:request` op with `crmTabs`. Expect `verified: "yes"`.
- [ ] **Step 5: Commit** `feat(desktop): optional CRM tab permission at first run`
