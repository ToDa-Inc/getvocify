import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { islandCallContact, latestOnly, type CallPreview } from "./call-contact.ts";

const preview = (over: Partial<CallPreview> = {}): CallPreview => ({
  provider: "hubspot",
  contact_id: "879829962968",
  contact_name: "zadarma test",
  needs_contact: false,
  ...over,
});

describe("islandCallContact", () => {
  it("names the contact on screen", () => {
    assert.deepEqual(islandCallContact(preview()), { name: "zadarma test" });
    assert.deepEqual(islandCallContact(preview({ contact_name: "  Ana Pérez " })), { name: "Ana Pérez" });
  });

  it("keeps the app name when the page is not a contact or the name is unknown", () => {
    assert.equal(islandCallContact(preview({ contact_id: null, contact_name: null, needs_contact: true })), null);
    assert.equal(islandCallContact(preview({ contact_name: null })), null);
    assert.equal(islandCallContact(preview({ contact_name: "   " })), null);
    assert.equal(islandCallContact(null), null);
  });
});

describe("latestOnly", () => {
  it("accepts only the newest ticket", () => {
    const calls = latestOnly();
    const first = calls.next();
    const second = calls.next();
    assert.equal(calls.isLatest(first), false);
    assert.equal(calls.isLatest(second), true);
  });
});
