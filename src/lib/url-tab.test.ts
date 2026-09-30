import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { parseTab } from "./url-tab.ts";

describe("parseTab", () => {
  const allowed = ["summary", "people"] as const;

  it("returns an allowed value as is", () => {
    assert.equal(parseTab("people", allowed, "summary"), "people");
  });

  it("falls back when the value is missing", () => {
    assert.equal(parseTab(null, allowed, "summary"), "summary");
    assert.equal(parseTab("", allowed, "summary"), "summary");
  });

  it("falls back on an unknown or disallowed value", () => {
    assert.equal(parseTab("playbook", allowed, "summary"), "summary");
    assert.equal(parseTab("People", allowed, "summary"), "summary");
  });
});
