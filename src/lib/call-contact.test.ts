import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { islandCallContact, islandRecordContact, latestOnly, type CallPreview } from "./call-contact.ts";

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

describe("islandRecordContact", () => {
  const detected = { hubspotId: "999", name: "Luis" };
  const onScreen = (over: Partial<CallPreview> = {}) =>
    preview({ callee: { contact_id: "123", name: " Ana Pérez ", phone: null }, ...over });

  it("keeps the contact of the detected call, even when the island offers another", () => {
    assert.deepEqual(islandRecordContact(detected, onScreen()), detected);
  });

  it("takes the HubSpot contact the island offers when no call is detected", () => {
    assert.deepEqual(islandRecordContact(null, onScreen()), { hubspotId: "123", name: "Ana Pérez" });
  });

  it("has no name when the offered contact has none", () => {
    assert.deepEqual(islandRecordContact(null, onScreen({ callee: { contact_id: "123", name: "  ", phone: null } })), { hubspotId: "123", name: null });
    assert.deepEqual(islandRecordContact(null, onScreen({ callee: { contact_id: "123", name: null, phone: null } })), { hubspotId: "123", name: null });
  });

  it("has no contact when the offer is not HubSpot, has no single contact, or is gone", () => {
    assert.equal(islandRecordContact(null, onScreen({ provider: "pipedrive" })), null);
    assert.equal(islandRecordContact(null, onScreen({ callee: null, needs_contact: true })), null);
    assert.equal(islandRecordContact(null, preview({ contact_id: null, contact_name: null, needs_contact: true })), null);
    assert.equal(islandRecordContact(null, null), null);
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
