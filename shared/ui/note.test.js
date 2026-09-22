import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { noteSaveBody } from "./note.js";

describe("review note", () => {
  it("does not save a blank note and keeps a real offset", () => {
    assert.equal(noteSaveBody("   ", 10), null);
    assert.deepEqual(noteSaveBody("Lo dijo con ironía", 134000.4), {
      text: "Lo dijo con ironía",
      offset_ms: 134000,
    });
    assert.deepEqual(noteSaveBody("sin tiempo", -3), { text: "sin tiempo", offset_ms: 0 });
  });
});
