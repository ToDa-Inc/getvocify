import { html } from "../html.js";

/** Pure overlay checklist block; returns null when nothing should show. */
export function overlayChecklistMarkup(
  checklist,
  { kind, doneLabel = "", progressLabel } = {},
) {
  if (kind !== "meeting") return null;
  if (!checklist || typeof checklist !== "object") return null;
  const applicable = Number(checklist.applicable);
  if (!Number.isFinite(applicable) || applicable <= 0) return null;

  const observedRaw = Number(checklist.observed);
  const observed = Number.isFinite(observedRaw) ? observedRaw : 0;
  const steps = Array.isArray(checklist.steps) ? checklist.steps : [];
  const progress =
    typeof progressLabel === "function"
      ? progressLabel(observed, applicable)
      : `${observed} / ${applicable}`;
  const done = String(doneLabel ?? "");

  const stepRows = steps
    .map((step) => {
      const label = String(step?.label ?? "").trim();
      if (!label) return null;
      if (step?.status === "met") {
        return html`<p class="line overlay-checklist-step"><span>${label}</span> <span class="muted">${done}</span></p>`;
      }
      return html`<p class="line overlay-checklist-step">${label}</p>`;
    })
    .filter(Boolean);

  return html`<div class="overlay-checklist">
    <p class="caps overlay-checklist-summary">${progress}</p>
    ${stepRows}
  </div>`;
}
