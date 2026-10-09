# Desktop calling C: Swift Mac app (watcher + island) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Mac island notices the CRM contact in the frontmost browser, offers a phone, confirms who and from which number, sends `dial`, and shows dialing, the in-call bar and the outcome, all driven by the dashboard's `onScreen` / `dial` state.

**Architecture:** Pure rules (host matching, change detection, phone grouping, wording, permission aggregation) go in `VocifyCore` with `VocifyCoreChecks`. A `CrmScreenWatcher` in `VocifyCompanion` reads only the frontmost supported browser on activation and every 1.5 s while it stays frontmost, and emits `crm:screen` when the CRM URL list changes. The island gains `dialConfirm` and `dialing` modes and a call bar inside `recording`.

**Tech Stack:** Swift 5.9+, SwiftUI, AppKit, macOS 14+, Swift Package (`apps/macos/Package.swift`).

**Repo:** `/Users/danizal/getvocify-desktop`, branch off `integrate/island`. All paths below are relative to `apps/macos/`.

**Spec:** `/Users/danizal/getvocify/docs/superpowers/specs/2026-10-06-desktop-calling-design.md` (bridge contract, island copy, decisions 1, 5, 8, 9, 11; risk #2). Dashboard side is plan B.

## Global Constraints

- Logic checks: `cd apps/macos && swift run VocifyCoreChecks` (prints failures, exits non-zero). App build: `CODESIGN_IDENTITY="Vocify Dev" ./scripts/dev-desktop.sh` from the repo root.
- Only CRM URLs leave the Mac (existing rule). Unknown hosts never reach `crm:screen`.
- Every new island state uses `IslandStyle` tokens and existing controls (`PrimaryActionButton`, `CircleButton`, `IconButton`, `StopButton`, `SmallAction`); new icons are SF Symbols: `phone.fill`, `phone.down.fill`, `mic.fill`, `mic.slash.fill`, `circle.grid.3x3.fill`.
- Copy is exactly the spec's "Island copy" table.
- Mode changes only through `transition(to:expanded:)` (`MeetingPill.swift:1370`).
- Main-thread budget for one watcher tick: p95 ≤ 10 ms (spec risk #2).

## Review Focus

1. **Rep denies Automation for Chrome:** the watcher never prompts (reads use `ask: false`), never retries in a loop, and the first-run row shows `denied` with "Open Settings".
2. **Browser quits or crashes while frontmost:** the watcher stops its timer on the next activation change and emits nothing stale.
3. **A real Zoom/FaceTime call starts while a Vocify call is active:** no call offer appears and the Vocify call's island state wins; after the Vocify call ends, detection resumes.
4. **Notch-less Mac / external display only:** the phone glyph sits in the right ear in both layouts (`frame(for:)` at 1359) and the confirm row fits 380 pt.
5. **`dial` state never arrives after the rep clicks Call** (dashboard closed or signed out): the island returns to idle after 8 s, as `record()` does.

---

## File Structure

| File | Responsibility |
|---|---|
| `Sources/VocifyCore/CrmPages.swift` | `isCrmURL` uses `CrmHostRules` |
| `Sources/VocifyCore/CrmHostRules.swift` | Decode `[{provider, host}]`, built-in defaults, match |
| `Sources/VocifyCore/CrmScreen.swift` | `CrmScreenChange` (emit-on-change), `CrmTabsAccess.aggregate` |
| `Sources/VocifyCore/CallIsland.swift` | `OnScreenCall`, `DialIslandState` decoding, `PhoneFormat.grouped`, `CallWording` |
| `Sources/VocifyCoreChecks/main.swift` | Checks for the above |
| `Sources/VocifyCompanion/CrmScreenWatcher.swift` | Frontmost observer + 1.5 s tick + emit |
| `Sources/VocifyCompanion/CrmPageReader.swift` | `readFrontmost(ask:)`, compiled-script cache, `access(ask:)` per browser |
| `Sources/VocifyCompanion/DesktopBridge.swift`, `bridge.js` | `crm:screen` channel, `crm.onScreen`, `crmTabs` permission |
| `Sources/VocifyCompanion/MeetingPill.swift` | Modes, ears, menus, call bar, suppression, debug fixtures |
| `Sources/VocifyCompanion/IslandFixtures.swift` | `#if DEBUG` named states for `VOCIFY_ISLAND_FIXTURE` |

---

### Task 1: Core rules

**Files:** Create `CrmHostRules.swift`, `CrmScreen.swift`, `CallIsland.swift` in `Sources/VocifyCore/`; modify `CrmPages.swift:48-62`, `Sources/VocifyCoreChecks/main.swift`.

**Interfaces (Produces):**

```swift
public struct CrmHostRule: Equatable, Sendable, Decodable { public let provider: String; public let host: String }
public enum CrmHostRules {
    public static let builtIn: [CrmHostRule]            // hubspot, pipedrive, salesforce — same regexes as backend plan A
    public static func decode(_ raw: Any?) -> [CrmHostRule]?   // from shell:state "crmHosts"; nil when malformed
    public static func provider(forURL url: String, rules: [CrmHostRule]) -> String?   // https only, host matched case-insensitively
}
// CrmPages.isCrmURL(_ url: String, rules: [CrmHostRule] = CrmHostRules.builtIn) -> Bool

public struct CrmScreenChange {
    public init()
    public mutating func next(_ urls: [String]) -> [String]?   // the list to emit, or nil when unchanged
}
public enum CrmTabsAccess {
    public static func aggregate(_ perBrowser: [String]) -> String   // "authorized" | "denied" | "not_asked" | "unavailable"
}

public struct OnScreenCall: Equatable { public let provider, crmLabel: String; public let name, phone, callerId: String?; public let state: State
    public enum State: String { case callable, noPhone = "no_phone", needsContact = "needs_contact", noCallerId = "no_caller_id" }
    public static func decode(_ raw: Any?) -> OnScreenCall? }
public struct DialIslandState: Equatable { public let phase: Phase; public let name: String?; public let phone: String
    public let answeredAt: Date?; public let muted: Bool; public let outcome: String?; public let message: String?
    public enum Phase: String { case connecting, ringing, active, ended }
    public static func decode(_ raw: Any?) -> DialIslandState? }
public enum PhoneFormat { public static func grouped(_ e164: String) -> String }      // "+34600111222" → "+34 600 111 222"
public enum CallWording {
    public static func glyphHelp(_ s: OnScreenCall) -> String
    public static func confirm(_ s: OnScreenCall) -> (title: String, line: String, button: String?)
    public static func dialing(_ d: DialIslandState) -> String
    public static func ended(_ d: DialIslandState) -> String
}
```

- [ ] **Step 1: Write the failing checks** in `VocifyCoreChecks/main.swift`:

```swift
check(CrmHostRules.provider(forURL: "https://acme.lightning.force.com/lightning/r/Contact/003A/view", rules: CrmHostRules.builtIn) == "salesforce", "salesforce host")
check(CrmHostRules.provider(forURL: "https://api.pipedrive.com/v1/deals", rules: CrmHostRules.builtIn) == nil, "pipedrive api excluded")
check(CrmHostRules.provider(forURL: "http://app.hubspot.com/contacts/1", rules: CrmHostRules.builtIn) == nil, "https only")
check(CrmPages.isCrmURL("https://app-eu1.hubspot.com/contacts/1/record/0-1/2"), "hubspot regional still a CRM page")
check(CrmHostRules.decode([["provider": "x"]]) == nil, "malformed rules rejected")
var change = CrmScreenChange()
check(change.next(["a"]) == ["a"] && change.next(["a"]) == nil && change.next([]) == [], "emit on change only")
check(CrmTabsAccess.aggregate(["denied", "authorized"]) == "authorized", "one granted browser is enough")
check(CrmTabsAccess.aggregate([]) == "unavailable", "no browser running")
check(CrmTabsAccess.aggregate(["not_asked", "denied"]) == "denied", "denied beats not asked")
check(PhoneFormat.grouped("+34600111222") == "+34 600 111 222", "grouped phone")
let ana = OnScreenCall.decode(["provider": "hubspot", "crmLabel": "HubSpot", "name": "Ana Ruiz", "phone": "+34600111222", "callerId": "+34910000000", "state": "callable"])!
check(CallWording.confirm(ana) == ("Ana Ruiz", "+34 600 111 222 · from +34 910 000 000", "Call"), "confirm copy")
check(CallWording.glyphHelp(OnScreenCall.decode(["provider": "pipedrive", "crmLabel": "Pipedrive", "name": "Ana", "state": "no_phone"])!) == "No phone in Pipedrive", "greyed help")
check(CallWording.ended(DialIslandState.decode(["phase": "ended", "phone": "+34600111222", "muted": false, "outcome": "no_answer"])!) == "No answer", "ended copy")
```

- [ ] **Step 2: Run** `swift run VocifyCoreChecks`, expect build FAIL (types missing).
- [ ] **Step 3: Implement.** `builtIn` regexes are copied from backend plan A (`hubspot`, `pipedrive`, `salesforce` matchers); `provider(forURL:)` compiles each with `NSRegularExpression(pattern:options: [.caseInsensitive])` once (static cache keyed by pattern). `CrmPages.isCrmURL` delegates; the existing behaviour checks keep passing.
- [ ] **Step 4: Run, expect PASS** (all old and new checks).
- [ ] **Step 5: Commit** `feat(core): CRM host rules, screen change, call island wording`

### Task 2: CRM screen watcher

**Files:** Create `Sources/VocifyCompanion/CrmScreenWatcher.swift`; modify `CrmPageReader.swift`, `DesktopBridge.swift` (emit + `crmHosts` from shell state), `bridge.js` (listener `crm:screen`, `crm.onScreen: on('crm:screen')`), `VocifyCompanionApp.swift` (start the watcher after sign-in).

**Interfaces:**
- Consumes: `CrmHostRules`, `CrmScreenChange`, `CrmPages.browser(bundleID:)`.
- Produces: `CrmPageReader.readFrontmost(ask: Bool) -> [String]?` (nil when the frontmost app is not a supported browser or access is not granted); `CrmPageReader.access(ask: Bool) -> [String]` (per running supported browser); `DesktopBridge.emitCrmScreen(urls: [String])` → `window.__vocifyEmit("crm:screen", {urls})`; `final class CrmScreenWatcher { init(bridge: DesktopBridge); func start(); func stop() }`.

- [ ] **Step 1:** Add a `Perf.swift` case only if it can run headless; otherwise measurement is Step 4 (AppleScript needs consent, so it cannot run in `VocifyCoreChecks`).
- [ ] **Step 2: Implement the reader.** `readFrontmost`: `NSWorkspace.shared.frontmostApplication?.bundleIdentifier` → supported browser → `AEDeterminePermissionToAutomateTarget(ask:)` → run its script through a per-bundle cached, compiled `NSAppleScript` → `CrmPages.crmURLs(fromScriptOutput:)` filtered with the current rules (from `shellState["crmHosts"]` via `CrmHostRules.decode`, else `builtIn`).
- [ ] **Step 3: Implement the watcher.** Observe `NSWorkspace.didActivateApplicationNotification`; when the activated app is a supported browser, read once and start a 1.5 s `Timer` (tolerance 0.3 s); stop the timer when another app activates. Each read → `change.next(urls)` → `bridge.emitCrmScreen` when non-nil. Reads use `ask: false` only. A non-browser app becoming frontmost does **not** emit `[]` (spec default "last one read").
- [ ] **Step 4: Measure** in a debug build: wrap each tick in `ContinuousClock` timing, log p50/p95 over 200 ticks with Chrome + Safari + Arc open and Automation granted. **Pass: p95 ≤ 10 ms.** Otherwise run the script via `Process` `/usr/bin/osascript -e` on a background queue and hop back to main only to emit; re-measure. Put the numbers in the commit body.
- [ ] **Step 5: Verify end to end** with the dashboard from plan B running at `VOCIFY_WEB_ORIGIN=http://localhost:8080`: open a HubSpot contact in Chrome → Reticle `reticle_wait_for` / `reticle_assert` that the store's `onScreen.name` equals the contact. Expect `verified: "yes"`.
- [ ] **Step 6: Commit** `feat(mac): watch the CRM contact on screen`

### Task 3: CRM-tab permission

**Files:** Modify `DesktopBridge.swift:100-109, 242-254`; `CrmPageReader.swift`.

**Interfaces:** `permissionSnapshot()` gains `"crmTabs": CrmTabsAccess.aggregate(CrmPageReader.access(ask: false))`; `permissions:request` with `type == "crmTabs"` → `CrmPageReader.access(ask: true)` (each running supported browser shows its macOS prompt once), then posts `permissions:changed`.

- [ ] **Step 1:** Add a check for the op routing if `DesktopBridge` routing is testable from `VocifyCoreChecks`; it is not today (executable target), so the test is Step 3.
- [ ] **Step 2: Implement.**
- [ ] **Step 3: Verify:** reset consent (`tccutil reset AppleEvents com.vocify.app`), open Chrome, open the first-run dialog (plan B Task 6) → click the CRM row → macOS prompt appears for Chrome → allow → Reticle `reticle_assert` the dashboard's permissions snapshot `crmTabs === "authorized"`. Deny path: `crmTabs === "denied"` and the row offers Open Settings. Both `verified: "yes"`.
- [ ] **Step 4: Commit** `feat(mac): CRM tab access in first-run permissions`

### Task 4: Island call states

**Files:** Modify `Sources/VocifyCompanion/MeetingPill.swift` (Mode 52-79, `apply` 533-625, `earWidth`/`size` 677-704, body switch 1461-1482, `helpText` 1520, `leftEar`/`rightEar` 1539-1640, `toggle` 846, `shortcutPressed` 988, `record` 1015, `callChanged` 1273-1297, new menus next to `CallMenu` 1654); `MicActivityMonitor.swift` (no API change; set `ignoresWebKit`). Create `Sources/VocifyCompanion/IslandFixtures.swift`.

**Interfaces:**
- Consumes: shell-state keys `onScreen`, `dial` (decoded with Task 1 types); commands from the bridge contract.
- Produces: `Mode.dialConfirm`, `Mode.dialing`; `MeetingPillState.onScreen: OnScreenCall?`, `.dial: DialIslandState?`; `MeetingPillController.openDialConfirm()`, `.dial()`, `.hangUp()`, `.setMuted(_:)`, `.sendDigit(_:)`, `.openCallingSettings()` (each emits its command).

Behaviour (each line is checked in Step 3):
- **Idle, `onScreen` set:** right ear shows `phone.fill` (beige when `callable`, `IslandStyle.secondary` at 0.5 otherwise); clicking the ear calls `openDialConfirm()` → `.dialConfirm` expanded, width 380.
- **`.dialConfirm`:** `CallWording.confirm`: title (12.5 medium), line (11.5 secondary), `PrimaryActionButton` with the button text when present. `Call` → `dial()` → `.dialing` with an 8 s timeout back to `.idle`. `Add caller ID` → `openCallingSettings()` then collapse.
- **`dial` with phase `connecting`/`ringing`/unanswered `ended`:** `.dialing`; ears: left `phone.fill`, right a 22 pt `StopButton`-red `phone.down.fill` (`hangUp()`); open body: `CallWording.dialing` and `Cancel`; on `ended`: `CallWording.ended` + `message`.
- **`dial.phase == active`:** the dashboard's `overlay:show` puts the island in `.recording` as today; when `dial` is non-null the controls row (2660) replaces Pause/Stop with: elapsed from `answeredAt`, `CircleButton` mute toggle (`mic.fill` / `mic.slash.fill`), `CircleButton` keypad (`circle.grid.3x3.fill`) opening a 3×4 grid of `SmallAction` digits (`sendDigit`), and a `StopButton` labelled `Hang up`. Live transcript and help render as in recording.
- **`dial` becomes null:** `.dialing` → `.idle`; `.recording` follows the existing hide → finishing → postCall path.
- **While `dial` is non-null and not `ended`:** `calls.ignoresWebKit = true`; `callChanged` returns early; `record()`, `toggle`, `shortcutPressed` do nothing.

- [ ] **Step 1: Write the fixtures** in `IslandFixtures.swift` (`#if DEBUG`), one per scenario, applied at launch when `VOCIFY_ISLAND_FIXTURE=<name>`; the same names and values exist in plan D:

| Name | Mode | State |
|---|---|---|
| `idle-callable` | idle | onScreen HubSpot · Ana Ruiz · +34600111222 · callerId +34910000000 · callable |
| `idle-no-phone` | idle | same, phone nil, `no_phone` |
| `confirm-callable` | dialConfirm | as `idle-callable` |
| `confirm-no-caller-id` | dialConfirm | callerId nil, `no_caller_id` |
| `confirm-needs-contact` | dialConfirm | name nil, `needs_contact`, crmLabel Salesforce |
| `dialing-ringing` | dialing | dial ringing, name Ana Ruiz |
| `in-call` | recording | dial active, answeredAt now − 65 s, muted false, two transcript turns, one help card |
| `in-call-muted-keypad` | recording | muted true, keypad open |
| `dial-ended-no-answer` | dialing | dial ended, outcome no_answer |

- [ ] **Step 2: Implement** the modes, ears, menus, call bar and suppression above.
- [ ] **Step 3: Verify.** For each fixture: launch with `VOCIFY_ISLAND_FIXTURE=<name>`, capture with `screencapture -o -l <window id> test/out/swift/<name>.png`, and check the behaviour line for it; then one live call through the dashboard (plan B Task 4 flows 2–3) watching the island go idle → confirm → dialing → in-call → finishing → post-call. Save the nine PNGs in the PR for the side-by-side with plan D.
- [ ] **Step 4: Commit** `feat(mac): call from the island`
