import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { meetingProposalView, renderMeetingProposal } from "./meeting-proposal.js";
import { renderToString } from "./html.js";

const agreed = {
  agreement: "agreed",
  starts_at: "2026-09-29T15:00:00+00:00",
  timezone: "Europe/Madrid",
  needs_review: false,
  decision: "pending",
  crm_status: "not_requested",
};

describe("meeting proposal review", () => {
  it("checks next steps without inventing a date while extraction is pending", () => {
    const view = meetingProposalView(null, { extractionPending: true });
    const markup = renderToString(renderMeetingProposal(view));
    assert.equal(view.title, "Comprobando próximos pasos");
    assert.equal(view.startsAt, null);
    assert.equal(markup.includes("2026"), false);
    assert.equal(markup.includes("Guardar reunión"), false);
  });

  it("hides the block during a live call and offers no save without an agreement", () => {
    assert.equal(meetingProposalView(agreed, { surface: "live" }).visible, false);
    const tentative = meetingProposalView({ ...agreed, agreement: "unknown", starts_at: null }, { surface: "review" });
    const markup = renderToString(renderMeetingProposal(tentative));
    assert.equal(tentative.save, false);
    assert.equal(markup.includes("Guardar reunión"), false);
    assert.equal(markup.includes("Omitir"), true);
  });

  it("does not call an uncertain CRM write saved", () => {
    const view = meetingProposalView({ ...agreed, decision: "accept", crm_status: "uncertain" }, { surface: "review" });
    const markup = renderToString(renderMeetingProposal(view));
    assert.equal(view.title, "No se ha guardado en el CRM");
    assert.equal(markup.includes("Guardada en el CRM"), false);
    assert.equal(markup.includes("Reconciliar"), true);
    assert.equal(view.startsAt, agreed.starts_at);
  });
});
