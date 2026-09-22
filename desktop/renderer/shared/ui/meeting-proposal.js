// Review-only meeting proposal. A live call does not show it, and an uncertain CRM write is not "saved".
import { html } from "./html.js";
import { strings } from "./i18n.js";

function meetingPhrases(lang) {
  const t = strings(lang);
  return {
    save: t.meetingSave,
    omit: t.meetingOmit,
    reconcile: t.meetingReconcile,
  };
}

export function meetingProposalView(proposal, { surface = "review", extractionPending = false, lang } = {}) {
  const t = strings(lang);
  const phrases = meetingPhrases(lang);
  if (surface === "live") return { visible: false };
  if (extractionPending || proposal?.extraction === "pending") {
    return { visible: true, title: t.meetingChecking, startsAt: null, save: false, omit: false, phrases };
  }
  if (!proposal) return { visible: false };
  if (proposal.decision === "omitted" || proposal.decision === "omit") {
    return { visible: true, title: t.meetingOmitted, startsAt: proposal.starts_at ?? null, save: false, omit: false, phrases };
  }
  if (
    (proposal.decision === "accepted" || proposal.decision === "accept" || proposal.decision === "corrected") &&
    proposal.crm_status === "not_requested"
  ) {
    return {
      visible: true,
      title: t.meetingDetected,
      startsAt: proposal.starts_at ?? null,
      timezone: proposal.timezone ?? null,
      save: false,
      omit: false,
      phrases,
    };
  }
  if (proposal.crm_status === "uncertain" || proposal.crm_status === "failed") {
    return {
      visible: true,
      title: t.meetingNotSaved,
      startsAt: proposal.starts_at ?? null,
      timezone: proposal.timezone ?? null,
      save: false,
      omit: true,
      reconcile: proposal.crm_status === "uncertain",
      phrases,
    };
  }
  if (proposal.crm_status === "succeeded") {
    return {
      visible: true,
      title: t.meetingSaved,
      startsAt: proposal.starts_at ?? null,
      timezone: proposal.timezone ?? null,
      save: false,
      omit: false,
      phrases,
    };
  }
  const agreed = proposal.agreement === "agreed";
  return {
    visible: true,
    title: proposal.needs_review || !agreed ? t.meetingPending : t.meetingDetected,
    startsAt: agreed ? proposal.starts_at ?? null : null,
    timezone: proposal.timezone ?? null,
    save: agreed && !proposal.needs_review && Boolean(proposal.starts_at),
    omit: true,
    phrases,
  };
}

export function renderMeetingProposal(view) {
  if (!view.visible) return html``;
  const { save: saveLabel, omit: omitLabel, reconcile: reconcileLabel } = view.phrases;
  return html`<section class="v-meeting-proposal">
  <p>${view.title}</p>
  ${view.startsAt ? html`<p>${view.startsAt}${view.timezone ? html` · ${view.timezone}` : ""}</p>` : ""}
  ${view.save ? html`<button type="button" data-action="accept">${saveLabel}</button>` : ""}
  ${view.omit ? html`<button type="button" data-action="omit">${omitLabel}</button>` : ""}
  ${view.reconcile ? html`<button type="button" data-action="reconcile">${reconcileLabel}</button>` : ""}
</section>`;
}
