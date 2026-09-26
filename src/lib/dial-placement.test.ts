import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const floatingDialerSource = readFileSync(
  fileURLToPath(new URL("../components/dashboard/calling/FloatingDialer.tsx", import.meta.url)),
  "utf8",
);

describe("dialer placement", () => {
  it("keeps a single DashboardDialer instance when placement changes", () => {
    assert.match(floatingDialerSource, /placement/);
    assert.doesNotMatch(
      floatingDialerSource,
      /placement\s*===\s*["']panel["'][\s\S]*<DashboardDialer[\s\S]*return null/,
    );
    assert.doesNotMatch(
      floatingDialerSource,
      /placement\s*===\s*["']floating["'][\s\S]*<DashboardDialer[\s\S]*return null/,
    );
    const mounts = floatingDialerSource.match(/<DashboardDialer/g) ?? [];
    assert.equal(mounts.length, 1, "expected exactly one DashboardDialer mount");
  });
});
