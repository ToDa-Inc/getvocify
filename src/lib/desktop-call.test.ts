import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { IDLE_CALL, reduceCall, type CallEngineState, type DialTarget } from "./call-engine-state.ts";
import type { CallPreview } from "./call-contact.ts";
import { crmRecordKey, dialIsland, dialTargetFor, onScreenFromPreview, outgoingCallerId, parseCallCommand } from "./desktop-call.ts";

const CONTACT_PAGE: CallPreview = {
  provider: "hubspot",
  contact_id: "901",
  contact_name: "Ana Ruiz",
  needs_contact: false,
  record: { provider: "hubspot", object_type: "contact", record_id: "901", account_id: "147506535" },
  callee: { contact_id: "901", name: "Ana Ruiz", phone: "+34600111222" },
  contacts_count: 1,
};
const DEAL_PAGE: CallPreview = {
  ...CONTACT_PAGE,
  contact_id: null,
  contact_name: null,
  needs_contact: true,
  record: { provider: "hubspot", object_type: "deal", record_id: "55", account_id: "147506535" },
  callee: { contact_id: "77", name: "Luis Gil", phone: "+34600333444" },
};
const ACCESS = { canDial: true, callerId: "+34910000000" };

describe("onScreenFromPreview", () => {
  it("a HubSpot contact with a phone is callable from the verified number", () => {
    assert.deepEqual(onScreenFromPreview(CONTACT_PAGE, ACCESS), {
      provider: "hubspot",
      crmLabel: "HubSpot",
      name: "Ana Ruiz",
      phone: "+34600111222",
      callerId: "+34910000000",
      state: "callable",
    });
  });

  it("a contact without a phone is shown but not callable", () => {
    const preview = { ...CONTACT_PAGE, callee: { contact_id: "901", name: "Ana Ruiz", phone: null } };
    assert.equal(onScreenFromPreview(preview, ACCESS)?.state, "no_phone");
  });

  it("without a verified caller ID the rep is sent to add one", () => {
    assert.equal(onScreenFromPreview(CONTACT_PAGE, { canDial: true, callerId: null })?.state, "no_caller_id");
  });

  it("a deal with several contacts asks the rep to open one", () => {
    const preview = { ...DEAL_PAGE, callee: null, contacts_count: 3 };
    assert.deepEqual(onScreenFromPreview(preview, ACCESS), {
      provider: "hubspot",
      crmLabel: "HubSpot",
      name: null,
      phone: null,
      callerId: "+34910000000",
      state: "needs_contact",
    });
  });

  it("nothing shows without the dialer plan, without a record, or outside HubSpot", () => {
    assert.equal(onScreenFromPreview(CONTACT_PAGE, { canDial: false, callerId: "+34910000000" }), null);
    assert.equal(onScreenFromPreview(null, ACCESS), null);
    assert.equal(onScreenFromPreview({ ...CONTACT_PAGE, record: null, callee: null, contacts_count: 0 }, ACCESS), null);
    assert.equal(onScreenFromPreview({ ...CONTACT_PAGE, provider: "pipedrive" }, ACCESS), null);
    assert.equal(onScreenFromPreview({ ...DEAL_PAGE, callee: null, contacts_count: 0 }, ACCESS), null);
  });
});

describe("dialTargetFor", () => {
  it("calls the contact on screen and files a deal page's call on the deal", () => {
    assert.deepEqual(dialTargetFor(DEAL_PAGE, ACCESS), {
      to: "+34600333444",
      name: "Luis Gil",
      contactId: "77",
      dealId: "55",
      callerId: "+34910000000",
    });
    assert.equal(dialTargetFor(CONTACT_PAGE, ACCESS)?.dealId, null);
  });

  it("is null unless the contact is callable", () => {
    assert.equal(dialTargetFor(CONTACT_PAGE, { canDial: true, callerId: null }), null);
  });
});

const ANA: DialTarget = { to: "+34600111222", name: "Ana Ruiz", contactId: "901", dealId: null, callerId: "+34910000000" };
const step = (s: CallEngineState, ...events: Parameters<typeof reduceCall>[1][]) => events.reduce(reduceCall, s);

describe("dialIsland", () => {
  it("is null with no call", () => {
    assert.equal(dialIsland(IDLE_CALL), null);
  });

  it("shows who is being called while it rings", () => {
    assert.deepEqual(dialIsland(step(IDLE_CALL, { type: "dial", target: ANA }, { type: "ringing" })), {
      phase: "ringing",
      name: "Ana Ruiz",
      phone: "+34600111222",
      answeredAt: null,
      muted: false,
      message: null,
    });
  });

  it("an unanswered call ends with the carrier's reason", () => {
    const s = step(IDLE_CALL, { type: "dial", target: ANA }, { type: "outcome", message: "Busy" }, { type: "ended", at: 2 });
    assert.deepEqual([dialIsland(s)?.phase, dialIsland(s)?.message], ["ended", "Busy"]);
  });

  it("an answered call hands over to the post-call card when it ends", () => {
    const s = step(IDLE_CALL, { type: "dial", target: ANA }, { type: "accepted", at: 1 }, { type: "ended", at: 2 });
    assert.equal(dialIsland(s), null);
  });
});

describe("parseCallCommand", () => {
  it("reads the island's call commands", () => {
    assert.deepEqual(parseCallCommand("dial"), { kind: "dial" });
    assert.deepEqual(parseCallCommand("hangup"), { kind: "hangup" });
    assert.deepEqual(parseCallCommand("mute"), { kind: "mute", muted: true });
    assert.deepEqual(parseCallCommand("unmute"), { kind: "mute", muted: false });
    assert.deepEqual(parseCallCommand("digit:#"), { kind: "digit", digit: "#" });
    assert.deepEqual(parseCallCommand("open-calling"), { kind: "open-calling" });
  });

  it("ignores everything else", () => {
    assert.equal(parseCallCommand("digit:x"), null);
    assert.equal(parseCallCommand("digit:12"), null);
    assert.equal(parseCallCommand("listen"), null);
  });
});

describe("outgoingCallerId", () => {
  it("uses the default verified number, else the first verified one", () => {
    const ids = [
      { phoneNumber: "+34911111111", status: "verified", source: "user" },
      { phoneNumber: "+34922222222", status: "verified", source: "user", isDefault: true },
    ];
    assert.equal(outgoingCallerId(ids), "+34922222222");
    assert.equal(outgoingCallerId([ids[0]]), "+34911111111");
  });

  it("never uses an unverified, blocked or Twilio-owned number", () => {
    assert.equal(
      outgoingCallerId([
        { phoneNumber: "+1", status: "pending", source: "user", isDefault: true },
        { phoneNumber: "+2", status: "verified", source: "twilio" },
        { phoneNumber: "+3", status: "verified", source: "user", callBlocked: true },
      ]),
      null,
    );
    assert.equal(outgoingCallerId(undefined), null);
  });
});

describe("crmRecordKey", () => {
  it("is the same for every view of one record, so the offer does not flicker", () => {
    const base = "https://app-eu1.hubspot.com/contacts/147506535/record/0-1/901";
    assert.equal(crmRecordKey(base), "hubspot:147506535:0-1:901");
    assert.equal(crmRecordKey(`${base}/view/2?eschref=x`), "hubspot:147506535:0-1:901");
    assert.equal(crmRecordKey("https://app.hubspot.com/contacts/147506535/contact/901"), "hubspot:147506535:0-1:901");
  });

  it("tells records apart: another contact, a deal, another portal", () => {
    assert.notEqual(crmRecordKey("https://app.hubspot.com/contacts/1/record/0-1/901"), crmRecordKey("https://app.hubspot.com/contacts/1/record/0-1/902"));
    assert.notEqual(crmRecordKey("https://app.hubspot.com/contacts/1/record/0-1/901"), crmRecordKey("https://app.hubspot.com/contacts/1/record/0-3/901"));
    assert.notEqual(crmRecordKey("https://app.hubspot.com/contacts/1/record/0-1/901"), crmRecordKey("https://app.hubspot.com/contacts/2/record/0-1/901"));
  });

  it("is null for anything that is not a record (lists, other sites)", () => {
    assert.equal(crmRecordKey("https://app.hubspot.com/contacts/1/objects/0-1/views/all/list"), null);
    assert.equal(crmRecordKey("https://mail.google.com/mail/u/0/"), null);
    assert.equal(crmRecordKey(""), null);
  });
});
