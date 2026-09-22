import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { meetingProposalView, renderMeetingProposal } from "./meeting-proposal.js";
import { strings } from "./i18n.js";
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
  it("localizes titles by lang", () => {
    const es = meetingProposalView(null, { extractionPending: true, lang: "es" });
    const en = meetingProposalView(null, { extractionPending: true, lang: "en" });
    assert.equal(es.title, strings("es").meetingChecking);
    assert.equal(en.title, strings("en").meetingChecking);
    assert.notEqual(es.title, en.title);
  });

  it("checks next steps without inventing a date while extraction is pending", () => {
    const t = strings("es");
    const view = meetingProposalView(null, { extractionPending: true, lang: "es" });
    const markup = renderToString(renderMeetingProposal(view));
    assert.equal(view.title, t.meetingChecking);
    assert.equal(view.startsAt, null);
    assert.equal(markup.includes("2026"), false);
    assert.equal(markup.includes(t.meetingSave), false);
  });

  it("hides the block during a live call and offers no save without an agreement", () => {
    assert.equal(meetingProposalView(agreed, { surface: "live", lang: "es" }).visible, false);
    const t = strings("es");
    const tentative = meetingProposalView(
      { ...agreed, agreement: "unknown", starts_at: null },
      { surface: "review", lang: "es" },
    );
    const markup = renderToString(renderMeetingProposal(tentative));
    assert.equal(tentative.save, false);
    assert.equal(markup.includes(t.meetingSave), false);
    assert.equal(markup.includes(t.meetingOmit), true);
  });

  it("does not call an uncertain CRM write saved", () => {
    const t = strings("es");
    const view = meetingProposalView(
      { ...agreed, decision: "accept", crm_status: "uncertain" },
      { surface: "review", lang: "es" },
    );
    const markup = renderToString(renderMeetingProposal(view));
    assert.equal(view.title, t.meetingNotSaved);
    assert.equal(markup.includes(t.meetingSaved), false);
    assert.equal(markup.includes(t.meetingReconcile), true);
    assert.equal(view.startsAt, agreed.starts_at);
  });
});
