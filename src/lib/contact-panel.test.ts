import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  contactPhone,
  conversationLine,
  firstName,
  historyRequest,
  initials,
  panelHeaderSubtitle,
  panelMeetingLine,
  panelPrimary,
  showsHistory,
} from "./contact-panel.ts";

const base = { kind: "call" as const, contactId: "c1", canDial: true, phone: "+34 612 48 90 21", crmHref: "https://crm/c1" };

describe("contact panel primary action", () => {
  it("calls when there is a contact, a dialer and the CRM has not said there is no phone", () => {
    assert.equal(panelPrimary(base), "call");
    assert.equal(panelPrimary({ ...base, phone: undefined }), "call");
  });

  it("falls back to Open in the CRM without a phone, a dialer or a contact", () => {
    assert.equal(panelPrimary({ ...base, phone: null }), "open");
    assert.equal(panelPrimary({ ...base, canDial: false }), "open");
    assert.equal(panelPrimary({ ...base, contactId: null }), "open");
    assert.equal(panelPrimary({ ...base, canPlace: false }), "open");
  });

  it("confirms a confirmation, and offers nothing when it can neither call nor open", () => {
    assert.equal(panelPrimary({ ...base, kind: "confirm" }), "confirm");
    assert.equal(panelPrimary({ ...base, canDial: false, crmHref: null }), null);
  });

  it("sends a ready follow-up and opens the CRM without a verified caller id", () => {
    assert.equal(panelPrimary({ ...base, kind: "followup", followupReady: true }), "send");
    assert.equal(panelPrimary({ ...base, canPlace: false }), "open");
  });
});

describe("contact panel phone", () => {
  const hits = [
    { contact_id: "c9", phone: "+34 600 00 00 09" },
    { contact_id: "c1", phone: "+34 612 48 90 21" },
  ];

  it("shows only the phone of the exact contact the search returned", () => {
    assert.equal(contactPhone(hits, "c1"), "+34 612 48 90 21");
  });

  it("never shows another result's phone", () => {
    assert.equal(contactPhone([{ contact_id: "c9", phone: "+34 600 00 00 09" }], "c1"), undefined);
    assert.equal(contactPhone(undefined, "c1"), undefined);
    assert.equal(contactPhone(hits, null), undefined);
  });

  it("says there is no phone only when the CRM returned the contact without one", () => {
    assert.equal(contactPhone([{ contact_id: "c1", phone: "  " }], "c1"), null);
    assert.equal(contactPhone([{ contact_id: "c1" }], "c1"), null);
  });
});

describe("contact panel history", () => {
  it("reads only HubSpot, which can filter by contact", () => {
    assert.equal(showsHistory("hubspot"), true);
    for (const provider of ["pipedrive", "salesforce", null]) assert.equal(showsHistory(provider), false);
  });

  it("asks for the rep's own last three reached conversations, also for an owner or admin", () => {
    const request = historyRequest("12 34");
    assert.equal(request, "/memos?hubspot_contact_id=12+34&reached_only=true&limit=3");
    assert.equal(request.includes("scope"), false);
  });

  it("names the kind of conversation and its minutes", () => {
    const fmt = { locale: "es-ES", timeZone: "Europe/Madrid" };
    const at = "2026-10-01T10:00:00+02:00";
    assert.deepEqual(conversationLine({ createdAt: at, interactionKind: "call", audioDuration: 840 }, fmt), {
      date: "1 oct",
      kindKey: "panel_kind_call",
      minutes: 14,
    });
    assert.equal(conversationLine({ createdAt: at, interactionKind: "meeting", audioDuration: 0 }, fmt).kindKey, "panel_kind_meeting");
    assert.equal(conversationLine({ createdAt: at, interactionKind: "visit", audioDuration: 0 }, fmt).kindKey, "panel_kind_visit");
    assert.equal(conversationLine({ createdAt: at, interactionKind: "sms", audioDuration: 0 }, fmt).kindKey, "panel_kind_conversation");
    assert.equal(conversationLine({ createdAt: at, interactionKind: null, audioDuration: 0 }, fmt).kindKey, "panel_kind_conversation");
    assert.equal(conversationLine({ createdAt: at, interactionKind: "call", audioDuration: 0 }, fmt).minutes, null);
    assert.equal(conversationLine({ createdAt: at, interactionKind: "call", audioDuration: 20 }, fmt).minutes, null);
  });
});

describe("contact panel header copy", () => {
  const copy = { panel_meeting_today: "Reunión hoy {time}", home_meeting_no_time: "Hoy · sin hora" };

  it("shows job title and company in the header, not the call quote", () => {
    assert.equal(
      panelHeaderSubtitle({ contact_id: "c1", jobtitle: "AE", company_name: "Acme" }, "Acme Corp", null),
      "AE · Acme Corp",
    );
    assert.equal(panelHeaderSubtitle(null, "Acme Corp", "Falta del playbook: pricing"), "Falta del playbook: pricing");
    assert.equal(panelHeaderSubtitle(null, null, null), null);
  });

  it("formats the meeting line without duplicating «Hoy» when there is no time", () => {
    assert.equal(panelMeetingLine(null, copy), "Hoy · sin hora");
    assert.equal(panelMeetingLine("11:30", copy), "Reunión hoy 11:30");
  });
});

describe("contact panel names", () => {
  it("calls the contact by first name and shows two initials", () => {
    assert.equal(firstName("  Marina   Ortiz "), "Marina");
    assert.equal(firstName(null), null);
    assert.equal(initials("Marina Ortiz"), "MO");
    assert.equal(initials("marina"), "M");
    assert.equal(initials("Ana María de la Fuente"), "AF");
    assert.equal(initials(""), "");
  });
});
