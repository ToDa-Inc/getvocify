import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { CALL_STATES, dialerChrome, floatingDialerChrome, type CallState } from "./dial-target.ts";

const floatingDialerSource = readFileSync(
  fileURLToPath(new URL("../components/dashboard/calling/FloatingDialer.tsx", import.meta.url)),
  "utf8",
);

const IN_FLIGHT: CallState[] = [
  CALL_STATES.CONNECTING,
  CALL_STATES.RINGING,
  CALL_STATES.ACTIVE,
  CALL_STATES.ENDING,
];

const mounted = (placement: "floating" | "panel", open: boolean, state: CallState) => {
  const chrome = dialerChrome(placement, open, state);
  return open || chrome.fab || chrome.panelBar;
};

describe("dialer placement", () => {
  it("renders one DashboardDialer inside a container that is never rendered conditionally", () => {
    const mounts = floatingDialerSource.match(/<DashboardDialer/g) ?? [];
    assert.equal(mounts.length, 1, "expected exactly one DashboardDialer mount");
    assert.match(
      floatingDialerSource,
      /return\s*\(\s*<>\s*<div\b/,
      "the dialer container must be the first, unconditional child of the fragment",
    );
    const start = floatingDialerSource.search(/return\s*\(\s*<>/);
    const mountAt = floatingDialerSource.slice(start).search(/\{dialerBody\}|<DashboardDialer/);
    assert.ok(start >= 0 && mountAt > 0, "expected the dialer to be mounted inside the returned tree");
    const pathToDialer = floatingDialerSource.slice(start, start + mountAt);
    assert.doesNotMatch(
      pathToDialer,
      /(chrome\.|\bopen\b|placement|live\.state)[^;{}]*?(\?|&&)\s*\(?\s*</,
      "sheet, panelBar, open or placement may toggle classes only, never mount what wraps the dialer",
    );
    const nulls = floatingDialerSource.match(/return null/g) ?? [];
    assert.equal(nulls.length, 1);
    assert.match(floatingDialerSource, /if \(!mounted\) return null;/);
    assert.match(floatingDialerSource, /const mounted = open \|\| chrome\.fab \|\| chrome\.panelBar;/);
  });

  it("Cambio de ruta: stays mounted mid-call when placement flips either way, open or minimised", () => {
    for (const state of IN_FLIGHT) {
      for (const open of [true, false]) {
        assert.equal(mounted("panel", open, state), true, `panel ${state} open=${open}`);
        assert.equal(mounted("floating", open, state), true, `floating ${state} open=${open}`);
      }
    }
  });

  it("with the flag off (floating) mounts exactly as before T5", () => {
    for (const state of [CALL_STATES.IDLE, ...IN_FLIGHT]) {
      for (const open of [true, false]) {
        const before = floatingDialerChrome(open, state);
        const now = dialerChrome("floating", open, state);
        assert.equal(now.sheet, before.sheet);
        assert.equal(now.fab, before.fab);
        assert.equal(now.panelBar, false);
        assert.equal(mounted("floating", open, state), open || before.fab);
      }
    }
  });
});
