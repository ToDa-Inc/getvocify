import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { detectedCallContact, islandCallContact, islandRecordContact, latestOnly, lookupTarget, onScreenRecord, type CallPreview } from "./call-contact.ts";

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

  it("takes the Pipedrive person the island offers", () => {
    assert.deepEqual(islandRecordContact(null, onScreen({ provider: "pipedrive" })), { hubspotId: "123", name: "Ana Pérez" });
  });

  it("has no contact when the offer is not a CRM the island calls, has no single contact, or is gone", () => {
    assert.equal(islandRecordContact(null, onScreen({ provider: null })), null);
    assert.equal(islandRecordContact(null, onScreen({ callee: null, needs_contact: true })), null);
    assert.equal(islandRecordContact(null, preview({ contact_id: null, contact_name: null, needs_contact: true })), null);
    assert.equal(islandRecordContact(null, null), null);
  });
});

describe("detectedCallContact", () => {
  it("is the HubSpot contact or the Pipedrive person of the page the call was detected on", () => {
    assert.deepEqual(detectedCallContact(preview({ provider: "hubspot", contact_id: "9", contact_name: " Ana " })), { hubspotId: "9", name: "Ana" });
    assert.deepEqual(detectedCallContact(preview({ provider: "pipedrive", contact_id: "9", contact_name: null })), { hubspotId: "9", name: null });
  });

  it("on a deal page, is the person the deal is called at (Pipedrive works by deal)", () => {
    const deal = preview({ provider: "pipedrive", contact_id: null, contact_name: null, callee: { contact_id: "20", name: " Marta ", phone: "+34600" } });
    assert.deepEqual(detectedCallContact(deal), { hubspotId: "20", name: "Marta" });
  });

  it("is nobody without a contact or a CRM", () => {
    assert.equal(detectedCallContact(preview({ contact_id: null, contact_name: null, needs_contact: true })), null);
    assert.equal(detectedCallContact(preview({ provider: null })), null);
  });
});

describe("onScreenRecord", () => {
  const page = (object_type: "contact" | "company" | "deal" | "lead", record_id = "58589", provider = "pipedrive") =>
    preview({ provider: "pipedrive", record: { provider, object_type, record_id, account_id: "movertis" } });
  it("is the deal or the company open on screen", () => {
    assert.deepEqual(onScreenRecord(page("deal")), { dealId: "58589" });
    assert.deepEqual(onScreenRecord(page("company", "66")), { companyId: "66" });
  });
  it("is nothing for a person, a lead, another CRM or no page", () => {
    assert.equal(onScreenRecord(page("contact")), undefined);
    assert.equal(onScreenRecord(page("lead", "0f8e-uuid")), undefined);
    assert.equal(onScreenRecord(page("deal", "58589", "salesforce")), undefined);
    assert.equal(onScreenRecord(null), undefined);
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

describe("lookupTarget", () => {
  it("an answer asked during an offer is the offer's while no recording started", () => {
    assert.equal(lookupTarget({ seq: 4, draftId: null }, { seq: 4, draftId: null }), "offer");
  });
  it("Record pressed before the answer came: the recording started right after takes it", () => {
    assert.equal(lookupTarget({ seq: 4, draftId: null }, { seq: 5, draftId: "b" }), "draft");
  });
  it("asked for a recording, it goes to that recording while it is still there", () => {
    assert.equal(lookupTarget({ seq: 5, draftId: "b" }, { seq: 5, draftId: "b" }), "draft");
    assert.equal(lookupTarget({ seq: 5, draftId: "b" }, { seq: 6, draftId: "b" }), "draft");
  });
  it("the call it was for is over: the answer reaches no other call (Pilar Torrija's deal on Marc Ferre's call)", () => {
    // Asked for recording b, which ended; a next recording c has started.
    assert.equal(lookupTarget({ seq: 5, draftId: "b" }, { seq: 6, draftId: null }), "drop");
    assert.equal(lookupTarget({ seq: 5, draftId: "b" }, { seq: 7, draftId: "c" }), "drop");
    // Asked during an offer; that call was recorded and ended, and nothing runs now.
    assert.equal(lookupTarget({ seq: 4, draftId: null }, { seq: 6, draftId: null }), "drop");
    // Asked during an offer; a recording started and ended, and another one runs now.
    assert.equal(lookupTarget({ seq: 4, draftId: null }, { seq: 7, draftId: "c" }), "drop");
  });
});
