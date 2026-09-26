import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  BRIEF_LOADING,
  BRIEF_MAX_LINES,
  visibleBrief,
  briefForContact,
  briefOnContact,
  briefRequest,
  briefRows,
  contactBriefDisplayLines,
  panelBrief,
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
    assert.deepEqual(
      contactBriefDisplayLines({
        objectType: "contact",
        contactId: "42",
        captureActive: false,
        cache: { contactId: "42", brief: { lines: [] } },
        flightContactId: null,
      }),
      ["Nada pendiente en esta ficha."],
    );
  });

  it("drops a stale response after the user changed contact", () => {
    assert.equal(shouldApplyBriefResponse("9", "42"), false);
    assert.equal(shouldApplyBriefResponse("9", "9"), true);
  });
});

describe("contact panel brief", () => {
  const NOTICE = "No se pudo cargar todo.";
  const fromA = { contactId: "A", brief: { status: "ready", text: null, lines: [{ type: "last", text: "De A" }] } };
  const texts = (view) => view.rows.map((row) => row.text);

  it("never paints the previous contact's brief while switching cards fast", () => {
    const empty = { notice: null, rows: [], label: null };
    assert.deepEqual(panelBrief({ contactId: "B", cache: fromA, flightContactId: "B" }), { state: "loading", ...empty });
    assert.deepEqual(panelBrief({ contactId: "C", cache: fromA, flightContactId: "C" }), { state: "loading", ...empty });
    assert.deepEqual(
      panelBrief({ contactId: "C", cache: fromA, flightContactId: null, failedContactId: "C" }),
      { state: "failed", ...empty },
    );
    assert.deepEqual(panelBrief({ contactId: "D", cache: fromA, flightContactId: null }), { state: "none", ...empty });
    assert.deepEqual(panelBrief({ contactId: null, cache: fromA, flightContactId: null }), { state: "none", ...empty });
    assert.deepEqual(texts(panelBrief({ contactId: "A", cache: fromA, flightContactId: "A" })), ["De A"]);
  });

  it("keeps a failed read apart from another contact's failure", () => {
    assert.equal(panelBrief({ contactId: "B", cache: null, flightContactId: null, failedContactId: "A" }).state, "none");
  });

  it("keeps three facts at most, with the partial notice apart", () => {
    const facts = [1, 2, 3, 4].map((n) => ({ type: "last", text: `Hecho ${n}` }));
    const partial = briefRows({ status: "partial", text: NOTICE, notice: NOTICE, lines: facts });
    assert.equal(BRIEF_MAX_LINES, 3);
    assert.equal(partial.notice, NOTICE);
    assert.deepEqual(texts(partial), ["Hecho 1", "Hecho 2", "Hecho 3"]);

    const unavailable = briefRows({ status: "unavailable", text: NOTICE, notice: NOTICE, lines: [] });
    assert.deepEqual({ notice: unavailable.notice, rows: unavailable.rows }, { notice: NOTICE, rows: [] });

    const ready = briefRows({ status: "ready", text: null, notice: null, lines: facts });
    assert.equal(ready.notice, null);
    assert.equal(ready.rows.length, 3);
  });

  it("says there is no conversation yet, with a CRM task under it", () => {
    const view = briefRows({
      status: "no_conversation",
      text: "Sin conversación todavía.",
      notice: null,
      lines: [{ type: "crm", text: "Llamar el jueves" }],
    });
    assert.deepEqual(texts(view), ["Sin conversación todavía.", "Llamar el jueves"]);
    assert.equal(view.notice, null);
  });

  it("paints the label as a chip and marks the team's playbook line", () => {
    const view = briefRows({
      status: "ready",
      text: null,
      lines: [
        { type: "hook", text: "11 sep: «se nos quedan leads sin llamar los viernes»" },
        { type: "why", text: "Pidió que la llamaras hoy." },
        { type: "say", text: "Precio: compáralo con un comercial más.", source: "playbook" },
        { type: "extra", text: "", source: "playbook" },
      ],
      label: "Pitch hecho · falta cualificar",
    });
    assert.deepEqual(view.rows.map((row) => row.playbook), [false, false, true]);
    assert.equal(view.label, "Pitch hecho · falta cualificar");
    assert.equal(briefRows({ status: "ready", lines: [], label: "   " }).label, null);
    assert.equal(briefRows({ status: "ready", lines: [] }).label, null);
  });
});
