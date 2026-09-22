import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  BRIEF_LOADING,
  visibleBrief,
  briefForContact,
  briefOnContact,
  briefRequest,
  contactBriefDisplayLines,
  shouldApplyBriefResponse,
} from "./brief.js";

describe("pre-call brief", () => {
  it("shows the never-spoken sentence without a fake last call", () => {
    const lines = visibleBrief({ status: "no_conversation", text: "Sin conversación todavía.", lines: [] });
    assert.deepEqual(lines, ["Sin conversación todavía."]);
  });

  it("shows a crm task under a contact with no conversation", () => {
    const lines = visibleBrief({
      status: "no_conversation",
      text: "Sin conversación todavía.",
      lines: [{ type: "crm", text: "Llamar el jueves" }],
    });
    assert.deepEqual(lines, ["Sin conversación todavía.", "Llamar el jueves"]);
  });

  it("does not add blank rows when nothing was left", () => {
    const lines = visibleBrief({
      status: "nothing_pending",
      text: "Última vez: 2026-09-02. No quedó nada pendiente.",
      lines: [],
    });
    assert.equal(lines.length, 1);
  });

  it("hides the brief during a capture and does not reuse another contact", () => {
    const cached = { contactId: "42", brief: { text: "Sin conversación todavía.", lines: [] } };
    assert.equal(briefForContact("9", cached), null);
    const brief = briefForContact("42", cached);
    assert.deepEqual(briefOnContact({ objectType: "contact", captureActive: false, brief }), ["Sin conversación todavía."]);
    assert.deepEqual(briefOnContact({ objectType: "contact", captureActive: true, brief }), []);
    assert.equal(briefRequest("42", "crm-A"), "/briefs?contact_id=42&connection_id=crm-A");
  });

  it("shows one loading line instead of the previous contact", () => {
    const cached = { contactId: "42", brief: { text: "Sin conversación todavía.", lines: [] } };
    assert.deepEqual(
      contactBriefDisplayLines({
        objectType: "contact",
        contactId: "9",
        captureActive: false,
        cache: cached,
        flightContactId: "9",
      }),
      [BRIEF_LOADING],
    );
    assert.deepEqual(
      contactBriefDisplayLines({
        objectType: "contact",
        contactId: "9",
        captureActive: false,
        cache: cached,
        flightContactId: null,
      }),
      [],
    );
  });

  it("drops a stale response after the user changed contact", () => {
    assert.equal(shouldApplyBriefResponse("9", "42"), false);
    assert.equal(shouldApplyBriefResponse("9", "9"), true);
  });
});
