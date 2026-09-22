import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

describe("overlay renderer", () => {
  it("does not open its own /copilot/suggest stream", () => {
    const src = readFileSync(join(root, "renderer/overlay.js"), "utf8");
    assert.equal(src.includes("streamCopilotSuggest"), false);
    assert.equal(src.includes("/copilot/suggest"), false);
    assert.equal(src.includes("fetchCopilotSuggest"), false);
  });
});
