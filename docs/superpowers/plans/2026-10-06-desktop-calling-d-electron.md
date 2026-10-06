# Desktop calling D: Electron app (watcher + island) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Electron island (Windows first, Mac too) does exactly what the Swift island does for calling, and looks the same state by state.

**Architecture:** Same split as the Swift plan. Pure rules in `app/core` (ported 1:1 from Swift plan C Task 1, same checks). A watcher in `app/main` reads the frontmost browser: a **long-lived** PowerShell UI Automation process on Windows (one process, line commands), `osascript` on Mac. The island gains `dialConfirm` / `dialing` modes and the in-call bar. Parity is proven with the same nine fixtures as Swift, screenshotted by `test:island`, paired with the Swift PNGs.

**Tech Stack:** Electron 33.4, React 19, TypeScript, esbuild, node:test, PowerShell 5.1 UI Automation (Windows), `osascript` (Mac).

**Repo:** `/Users/danizal/getvocify-electron`, branch off `feat/electron`. Paths below are relative to `app/`.

**Spec:** `/Users/danizal/getvocify/docs/superpowers/specs/2026-10-06-desktop-calling-design.md` (bridge contract, island copy, decisions 1, 5, 8, 9, 11). Swift reference: `docs/superpowers/plans/2026-10-06-desktop-calling-c-swift.md` (same fixtures, same wording, same behaviour lines).

## Global Constraints

- Tests: `npm run test:logic` (core + controller), `npm run test:island` (fixtures → `test/out/*.png`, `sheet.png`, `report.json`), `npm run typecheck`.
- Tokens only from `island/src/island.css` (`--beige`, `--danger`, `--text`, `--secondary`, `--ease`); sizes only from `island/src/geometry.ts`. New icons are hand-drawn SVGs in `island/src/icons.tsx` matching the SF Symbols used by Swift (`phone.fill`, `phone.down.fill`, `mic.fill`, `mic.slash.fill`, `circle.grid.3x3.fill`): 16 px box, filled, `currentColor`.
- Copy is exactly the spec's "Island copy" table, via `core/islandWording.ts`.
- Only CRM URLs leave the machine; the Windows script keeps skipping `Document` controls (no page content is read).
- Never spawn more than one PowerShell process for page reading; a tick that finds the previous read still running is skipped.

## Review Focus

1. **PowerShell reader dies** (killed, crash, antivirus): the watcher restarts it once per minute at most, and the island simply shows no phone meanwhile.
2. **Two monitors, browser frontmost on the second:** the frontmost-window check uses the foreground window, not the island's display.
3. **Edge with a localized UI (Spanish address bar name):** the UIA address bar is still found (the existing script finds it by position, not by name — keep that).
4. **The rep clicks Call twice quickly:** one `dial` command, one call.
5. **`MicWatcher` on Windows while the Vocify call runs:** Vocify's own process stays skipped (`process.execPath`) and no call offer appears; add a check that the dial suppression also holds if the mic registry entry belongs to an Electron helper process.

---

## File Structure

| File | Responsibility |
|---|---|
| `core/crmHostRules.ts`, `core/crmScreen.ts`, `core/callIsland.ts` | Ports of Swift `CrmHostRules`, `CrmScreen`, `CallIsland` |
| `core/crmPages.ts` | `isCrmURL(url, rules = builtIn)` |
| `core/islandWording.ts` | Call copy |
| `core/core.test.ts` | Same checks as Swift Task 1 |
| `main/src/windows/page-reader-process.ts` | Long-lived PowerShell: `front` and `read` commands |
| `main/src/windows/browser-pages.ts` | Script gains the loop + foreground query |
| `main/src/mac/browser-pages.ts` | `osascript` reads of the frontmost supported browser |
| `main/src/crm-screen-watcher.ts` | 1.5 s tick while a browser is frontmost, emit on change |
| `main/src/bridge.ts`, `main/src/app.ts`, `main/src/dashboard-preload.ts` | `crm:screen` event, `crm.pages` wired, `crmTabs` permission |
| `main/src/controller.ts`, `main/test/controller.test.ts` | Modes, commands, suppression, timeouts |
| `island/src/types.ts`, `Island.tsx`, `icons.tsx`, `geometry.ts`, `helpers.ts`, `island.css` | UI |
| `island/fixtures/index.mjs`, `test/parity-sheet.mjs` | Nine fixtures; Swift/Electron pairing sheet |

---

### Task 1: Core rules (port)

**Files:** Create `core/crmHostRules.ts`, `core/crmScreen.ts`, `core/callIsland.ts`; modify `core/crmPages.ts:30`, `core/islandWording.ts`, `core/core.test.ts`.

**Interfaces (Produces):** the TypeScript twins of Swift plan C Task 1 — `CrmHostRule`, `BUILT_IN_HOST_RULES`, `decodeHostRules(raw: unknown): CrmHostRule[] | null`, `providerForURL(url: string, rules: CrmHostRule[]): string | null`, `class CrmScreenChange { next(urls: string[]): string[] | null }`, `aggregateCrmTabs(perBrowser: string[]): "authorized" | "denied" | "not_asked" | "unavailable"`, `OnScreenCall` / `DialIslandState` types + `decodeOnScreen` / `decodeDial`, `groupPhone(e164: string): string`, `callWording.{glyphHelp, confirm, dialing, ended}`. Regexes compiled with `new RegExp(host, "i")`.

- [ ] **Step 1: Write the failing tests** — the same thirteen assertions as Swift plan C Task 1 Step 1, in `node:test` form, for example:

```ts
it("matches the same hosts as the Mac app", () => {
  assert.equal(providerForURL("https://acme.lightning.force.com/lightning/r/Contact/003A/view", BUILT_IN_HOST_RULES), "salesforce");
  assert.equal(providerForURL("https://api.pipedrive.com/v1/deals", BUILT_IN_HOST_RULES), null);
});
it("words the confirm row", () => {
  assert.deepEqual(callWording.confirm(ana), { title: "Ana Ruiz", line: "+34 600 111 222 · from +34 910 000 000", button: "Call" });
});
```

- [ ] **Step 2: Run** `npm run test:logic`, expect FAIL.  - [ ] **Step 3: Implement.**  - [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `feat(core): CRM host rules and call wording, same as the Mac app`

### Task 2: Page readers + watcher + bridge wiring

**Files:** Create `main/src/windows/page-reader-process.ts`, `main/src/mac/browser-pages.ts`, `main/src/crm-screen-watcher.ts`, `main/test/crm-screen-watcher.test.ts`; modify `main/src/windows/browser-pages.ts`, `main/src/bridge.ts:61-195` (pass `readCrmPages`, `crm:open-automation-settings`, `crmTabs` in permissions), `main/src/permissions.ts:47-54`, `main/src/dashboard-preload.ts` (`crm.onScreen`, `crm.pages`, `crm.openAutomationSettings`), `main/src/app.ts:143, 182-199, 344-366`.

**Interfaces:**
- Produces:
  - `createPageReaderProcess(spawn: SpawnFn): { front(): Promise<string | null>; read(): Promise<BrowserPage[]>; dispose(): void }` — one `powershell.exe -NoProfile -NonInteractive -EncodedCommand` child; commands are lines on stdin (`front`, `read`), each answer ends with a line `<<END>>`; `front` returns the foreground window's process name (`GetForegroundWindow` + `GetWindowThreadProcessId` via `Add-Type` user32).
  - `readMacFrontmost(exec: ExecFn): Promise<{ urls: string[]; access: "authorized" | "denied" | "not_asked" }>` — frontmost app via `osascript -e 'id of application (path to frontmost application as text)'`, then that browser's `core/crmPages.ts` script; exit message containing `-1743` → `denied`.
  - `createCrmScreenWatcher(deps: { front(): Promise<string | null>; read(): Promise<string[]>; emit(urls: string[]): void; rules(): CrmHostRule[]; clock: Clock }): { start(): void; stop(): void }` — 1.5 s tick; reads only when `front()` is a supported browser; skips a tick while a read is in flight; emits via `CrmScreenChange`.

- [ ] **Step 1: Write the failing watcher tests** (fake clock, fake `front`/`read`):

```ts
it("reads only while a browser is frontmost and emits on change", async () => {
  front.value = "slack"; await clock.tick(1500); assert.equal(reads, 0);
  front.value = "chrome"; read.value = [HUBSPOT_CONTACT]; await clock.tick(1500);
  assert.deepEqual(emitted, [[HUBSPOT_CONTACT]]);
  await clock.tick(1500); assert.equal(emitted.length, 1);
});
it("skips a tick while the previous read is still running", async () => {
  read.delayMs = 4000; front.value = "msedge";
  await clock.tick(1500); await clock.tick(1500);
  assert.equal(reads, 1);
});
it("does not emit [] when a non-browser app comes to the front", async () => {
  front.value = "chrome"; read.value = [HUBSPOT_CONTACT]; await clock.tick(1500);
  front.value = "explorer"; await clock.tick(1500);
  assert.deepEqual(emitted, [[HUBSPOT_CONTACT]]);
});
```

- [ ] **Step 2: Run** `npm run test:logic`, expect FAIL.
- [ ] **Step 3: Implement** readers, watcher and wiring. The watcher starts after sign-in (same place `MicWatcher` is wired, `app.ts:392-414`) and emits on `vocify:emit` channel `crm:screen`. Rules come from the last `shell.setState({crmHosts})`, else `BUILT_IN_HOST_RULES`. Windows `crmTabs` is always `"authorized"`; Mac Electron reports the last `readMacFrontmost` access (`not_asked` before the first read). `permissions.request("crmTabs")` on Mac runs one `readMacFrontmost` per running supported browser (that is what makes macOS ask).
- [ ] **Step 4: Run** tests (PASS). Then `npm run test:windows` on a Windows machine with Chrome and Edge open on a HubSpot contact: the dashboard receives `crm:screen` (Reticle `reticle_assert` on `onScreen.name`, `verified: "yes"`); Task Manager shows exactly one `powershell.exe` child of Vocify.
- [ ] **Step 5: Commit** `feat(desktop): watch the CRM contact on screen on Windows and Mac`

### Task 3: Island call states

**Files:** Modify `island/src/types.ts:5-13, 102-140`, `island/src/Island.tsx` (`RightEar` 187, `LeftEar` 152, `Body` 237, new `DialConfirmMenu`, `DialingMenu`, call bar inside `OpenIsland` 316), `island/src/icons.tsx`, `island/src/geometry.ts`, `island/src/helpers.ts` (`helpText`), `main/src/controller.ts` (`applyShellState` 137-203, `act` 227-255, `record` 385, `callChanged` 523-552), `main/test/controller.test.ts`, `island/fixtures/index.mjs`; create `test/parity-sheet.mjs`.

**Interfaces:**
- Produces: mode kinds `"dialConfirm"`, `"dialing"`; `IslandState.onScreen: OnScreenCall | null`, `IslandState.dial: DialIslandState | null`, `IslandState.keypadOpen: boolean`; `IslandAction` adds `{type:"openDialConfirm"} | {type:"dial"} | {type:"hangup"} | {type:"mute", muted: boolean} | {type:"digit", digit: string} | {type:"keypad", open: boolean} | {type:"openCalling"}`; controller emits the spec commands for each.

- [ ] **Step 1: Write the failing controller tests:**

```ts
it("Call sends one dial and falls back to idle after 8 s without dial state", () => {
  c.applyShellState({ onScreen: ANA });
  c.act({ type: "openDialConfirm" }); c.act({ type: "dial" }); c.act({ type: "dial" });
  assert.deepEqual(commands, ["dial"]); assert.equal(c.state.mode.kind, "dialing");
  clock.tick(8000); assert.equal(c.state.mode.kind, "idle");
});
it("suppresses call offers, Record and toggle while a Vocify call is up", () => {
  c.applyShellState({ dial: { ...RINGING } });
  c.callChanged({ appId: "zoom", name: "Zoom" }); c.act({ type: "record" }); c.shortcutPressed();
  assert.notEqual(c.state.mode.kind, "call"); assert.deepEqual(commands, []);
});
it("dial null returns dialing to idle", () => {
  c.applyShellState({ dial: { ...ENDED_NO_ANSWER } }); c.applyShellState({ dial: null });
  assert.equal(c.state.mode.kind, "idle");
});
it("keypad digits become digit commands", () => {
  c.applyShellState({ dial: ACTIVE }); c.act({ type: "digit", digit: "5" });
  assert.deepEqual(commands, ["digit:5"]);
});
```

- [ ] **Step 2: Run** `npm run test:logic`, expect FAIL.
- [ ] **Step 3: Implement** the same behaviour lines as Swift plan C Task 4 (idle glyph in the right ear, confirm row at 380 wide, dialing ears and body, call bar replacing Pause/Stop in recording, ended outcome, suppression), and add the nine fixtures with the **same names and values** as the Swift table, plus interactions: `confirm-callable` click `Call` → expect `[{type:"dial"}]`; `in-call` click mute → `[{type:"mute", muted:true}]`; `dialing-ringing` click `Cancel` → `[{type:"hangup"}]`.
- [ ] **Step 4: Run** `npm run test:logic` and `npm run test:island` (PASS: sizes, no overflow, interactions). Then `node test/parity-sheet.mjs <path to Swift PNGs from plan C Task 4>` → `test/out/parity.png` with each fixture Swift | Electron side by side. **Acceptance:** Dani approves `parity.png`; differences are listed in the PR and fixed before merge (spacing, icon weight, colour, copy).
- [ ] **Step 5: Live check** on Windows: one real call through the dashboard (plan B Task 4 flows 2–3) watching idle → confirm → dialing → in-call → finishing → post-call.
- [ ] **Step 6: Commit** `feat(desktop): call from the island on Windows and Mac`
