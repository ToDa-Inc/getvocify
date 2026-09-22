import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { visibleBrief } from "./brief.js";

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
});
