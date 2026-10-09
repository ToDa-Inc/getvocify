import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { CALL_STATES, dialerDock, type CallState } from "./dial-target.ts";

const dialerDockSource = readFileSync(
  fileURLToPath(new URL("../components/dashboard/calling/DialerDock.tsx", import.meta.url)),
  "utf8",
);

const IN_FLIGHT: CallState[] = [
  CALL_STATES.CONNECTING,
  CALL_STATES.RINGING,
  CALL_STATES.ACTIVE,
  CALL_STATES.ENDING,
];

const mounted = (open: boolean, state: CallState) => open || dialerDock(open, state).liveTab;

describe("dialer dock", () => {
  it("renders one DashboardDialer inside a panel that is never rendered conditionally", () => {
    const mounts = dialerDockSource.match(/<DashboardDialer/g) ?? [];
    assert.equal(mounts.length, 1, "expected exactly one DashboardDialer mount");
    assert.match(
      dialerDockSource,
      /return\s*\(\s*<DockPanel\b/,
      "the dock panel must be the one unconditional root of the returned tree",
    );
    const start = dialerDockSource.search(/return\s*\(\s*<DockPanel/);
    const mountAt = dialerDockSource.slice(start).search(/\{dialerBody\}|<DashboardDialer/);
    assert.ok(start >= 0 && mountAt > 0, "expected the dialer to be mounted inside the returned tree");
    const pathToDialer = dialerDockSource.slice(start, start + mountAt);
    assert.doesNotMatch(
      pathToDialer,
      /(dock\.|\bopen\b|live\.state)[^;{}]*?(\?|&&)\s*\(?\s*</,
      "open or the live state may toggle classes only, never mount what wraps the dialer",
    );
    const nulls = dialerDockSource.match(/return null/g) ?? [];
    assert.equal(nulls.length, 1);
    assert.match(dialerDockSource, /if \(!mounted\) return null;/);
    assert.match(dialerDockSource, /const mounted = open \|\| dock\.liveTab;/);
  });

  it("stays mounted mid-call whether the panel is open or closed", () => {
    for (const state of IN_FLIGHT) {
      for (const open of [true, false]) {
        assert.equal(mounted(open, state), true, `${state} open=${open}`);
      }
    }
  });

  it("is not mounted when idle and closed, and mounted when opened", () => {
    assert.equal(mounted(false, CALL_STATES.IDLE), false);
    assert.equal(mounted(true, CALL_STATES.IDLE), true);
  });
});
