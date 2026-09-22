// Review-only meeting proposal. A live call does not show it, and an uncertain CRM write is not "saved".
import { html } from "./html.js";

export function meetingProposalView(proposal, { surface = "review", extractionPending = false } = {}) {
  if (surface === "live") return { visible: false };
  if (extractionPending || proposal?.extraction === "pending") {
    return { visible: true, title: "Comprobando próximos pasos", startsAt: null, save: false, omit: false };
  }
  if (!proposal) return { visible: false };
  if (proposal.decision === "omitted" || proposal.decision === "omit") {
    return { visible: true, title: "Reunión omitida", startsAt: proposal.starts_at ?? null, save: false, omit: false };
  }
  if (
    (proposal.decision === "accepted" || proposal.decision === "accept" || proposal.decision === "corrected") &&
    proposal.crm_status === "not_requested"
  ) {
    return {
      visible: true,
      title: "Reunión detectada",
      startsAt: proposal.starts_at ?? null,
      timezone: proposal.timezone ?? null,
      save: false,
      omit: false,
    };
  }
  if (proposal.crm_status === "uncertain" || proposal.crm_status === "failed") {
    return {
      visible: true,
      title: "No se ha guardado en el CRM",
      startsAt: proposal.starts_at ?? null,
      timezone: proposal.timezone ?? null,
      save: false,
      omit: true,
      reconcile: proposal.crm_status === "uncertain",
    };
  }
  if (proposal.crm_status === "succeeded") {
    return {
      visible: true,
      title: "Guardada en el CRM",
      startsAt: proposal.starts_at ?? null,
      timezone: proposal.timezone ?? null,
      save: false,
      omit: false,
    };
  }
  const agreed = proposal.agreement === "agreed";
  return {
    visible: true,
    title: proposal.needs_review || !agreed ? "Pendiente de revisar" : "Reunión detectada",
    startsAt: agreed ? proposal.starts_at ?? null : null,
    timezone: proposal.timezone ?? null,
    save: agreed && !proposal.needs_review && Boolean(proposal.starts_at),
    omit: true,
  };
}

export function renderMeetingProposal(view) {
  if (!view.visible) return html``;
  return html`<section class="v-meeting-proposal">
  <p>${view.title}</p>
  ${view.startsAt ? html`<p>${view.startsAt}${view.timezone ? html` · ${view.timezone}` : ""}</p>` : ""}
  ${view.save ? html`<button type="button" data-action="accept">Guardar reunión</button>` : ""}
  ${view.omit ? html`<button type="button" data-action="omit">Omitir</button>` : ""}
  ${view.reconcile ? html`<button type="button" data-action="reconcile">Reconciliar</button>` : ""}
</section>`;
}
